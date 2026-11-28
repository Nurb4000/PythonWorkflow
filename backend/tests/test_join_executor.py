"""M9: workflow-level join / fan-in output aggregation.

Covers both layers:

* unit behavior of ``JoinExecutor`` (aliasing, flattening, missing-source policy,
  fail-closed validation, deep merge, metadata isolation);
* engine integration: two parallel branches converge on a join node which reads
  both branch outputs from the run's StepInstances and exposes one aggregate to
  downstream steps (and on the run itself).

Run with: pytest backend/tests/test_join_executor.py -q
"""
import asyncio
import json
import time

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.auth import User
from app.models.schemas import StepInstance, Workflow, WorkflowRun, WorkflowStep
from app.schemas.workflow import WorkflowCreate, WorkflowRunCreate
from app.services import workflow_engine as we_module
from app.services.step_executors import JoinExecutor
from app.services.workflow_engine import WorkflowEngine
from app.services.workflow_export_service import WorkflowExportService
from app.services.workflow_import_service import WorkflowImportService


@pytest_asyncio.fixture
async def session(db_engine):
    async with async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def engine(db_engine, monkeypatch):
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(we_module, "async_session_factory", factory)
    return WorkflowEngine()


async def wait_run(session, run_id, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        await asyncio.sleep(0.05)
        run = await session.get(WorkflowRun, run_id)
        if run:
            await session.refresh(run)
            if run.status in ("completed", "failed", "waiting"):
                return run
    raise AssertionError("run did not finish in time")


class TestJoinExecutorUnit:
    @pytest.mark.asyncio
    async def test_key_sources_are_aliased_and_engine_meta_is_excluded(self):
        result = await JoinExecutor().execute(
            {
                "_workflow_run_id": 7,
                "_workflow_step_id": 9,
                "raw": {"rows": [1, 2]},
                "note": "hello",
            },
            {
                "sources": [
                    {"key": "raw", "as": "validation"},
                    {"key": "note", "as": "annotation"},
                ],
                "output_key": "bundle",
            },
        )
        assert "joined" not in result  # custom output_key replaces the default
        assert result["bundle"] == {
            "validation": {"rows": [1, 2]},
            "annotation": "hello",
        }
        assert result["source_count"] == 2
        assert result["missing_sources"] == []
        assert [s["key"] for s in result["sources"]] == ["raw", "note"]

    @pytest.mark.asyncio
    async def test_no_sources_collects_all_non_meta_input(self):
        result = await JoinExecutor().execute(
            {"_workflow_run_id": 1, "_workflow_step_id": 2, "a": 1, "b": 2},
            {},
        )
        assert result["joined"] == {"a": 1, "b": 2}
        assert result["source_count"] == 0

    @pytest.mark.asyncio
    async def test_include_input_keeps_flat_values_without_meta(self):
        result = await JoinExecutor().execute(
            {"_workflow_run_id": 1, "tenant": 4, "picked": "x"},
            {"sources": [{"key": "picked", "as": "chosen"}], "include_input": True},
        )
        assert result["joined"] == {"tenant": 4, "picked": "x", "chosen": "x"}

    @pytest.mark.asyncio
    async def test_same_alias_deep_merges_dict_sources(self):
        result = await JoinExecutor().execute(
            {"left": {"rows": [1], "meta": {"a": 1}}, "right": {"rows": [2], "meta": {"b": 2}}},
            {
                "sources": [
                    {"key": "left", "as": "branch"},
                    {"key": "right", "as": "branch"},
                ]
            },
        )
        assert result["joined"]["branch"] == {
            "rows": [2],
            "meta": {"a": 1, "b": 2},
        }
        assert result["source_count"] == 2

    @pytest.mark.asyncio
    async def test_missing_source_fails_closed_by_default_and_can_be_skipped(self):
        definition = {"sources": [{"key": "present"}, {"key": "absent"}]}
        with pytest.raises(ValueError, match="no completed output"):
            await JoinExecutor().execute({"present": 1}, definition)

        result = await JoinExecutor().execute({"present": 1}, {**definition, "missing": "skip"})
        assert result["joined"] == {"present": 1}
        assert result["missing_sources"] == ["absent"]
        assert result["source_count"] == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "definition, message",
        [
            ({"sources": "nope"}, "must be a list"),
            ({"sources": [{}]}, "needs a 'step_id' or 'key'"),
            ({"sources": [{"key": "x", "as": ""}]}, "invalid alias"),
            ({"output_key": ""}, "output_key"),
            ({"missing": "ignore"}, "must be 'error' or 'skip'"),
            ({"sources": [{"step_id": "abc"}]}, "invalid step_id"),
        ],
    )
    async def test_invalid_definitions_fail_closed(self, definition, message):
        with pytest.raises(ValueError, match=message):
            await JoinExecutor().execute({"x": 1}, definition)

    @pytest.mark.asyncio
    async def test_step_id_sources_require_a_db_session_and_run_id(self):
        with pytest.raises(ValueError, match="require a database session"):
            await JoinExecutor().execute({}, {"sources": [{"step_id": 5}]})
        with pytest.raises(ValueError, match="workflow run id"):
            await JoinExecutor().execute(
                {}, {"sources": [{"step_id": 5}]}, db=object()
            )


class TestJoinEngineIntegration:
    @pytest.mark.asyncio
    async def test_parallel_branches_are_collected_by_join(self, engine, session):
        wf = await engine.create_workflow(
            session,
            WorkflowCreate(
                name="M9 fan-in",
                steps=[
                    {"step_type": "custom_code", "definition": {
                        "code": "output['rows'] = [1, 2]; output['label'] = 'left'",
                    }},
                    {"step_type": "custom_code", "definition": {
                        "code": "output['rows'] = [3]; output['label'] = 'right'",
                    }},
                    {"step_type": "join", "definition": {"output_key": "joined"}},
                ],
            ),
        )
        await session.refresh(wf, attribute_names=["steps"])
        left, right, join = sorted(wf.steps, key=lambda s: s.position)
        left.definition = {**left.definition, "next_step_ids": [join.id]}
        right.definition = {**right.definition, "next_step_ids": [join.id]}
        join.definition = {
            **join.definition,
            "sources": [
                {"step_id": left.id, "as": "validation"},
                {"step_id": right.id, "as": "enrichment"},
            ],
        }
        wf.config = {"start_step_ids": [left.id, right.id]}
        await session.commit()

        run = await engine.trigger_workflow(session, wf.id, WorkflowRunCreate())
        run = await wait_run(session, run.id)
        assert run.status == "completed", run.error_message
        await asyncio.sleep(0.3)

        instances = (await session.execute(
            select(StepInstance).where(StepInstance.workflow_run_id == run.id)
        )).scalars().all()
        by_step = {i.step_id: i for i in instances}
        assert by_step[join.id].status == "completed"
        joined = by_step[join.id].output_data["joined"]
        assert joined["validation"]["rows"] == [1, 2]
        assert joined["enrichment"]["rows"] == [3]
        assert joined["validation"]["label"] == "left"
        assert joined["enrichment"]["label"] == "right"
        assert run.input_data["joined"] == joined

    @pytest.mark.asyncio
    async def test_key_source_reads_accumulated_run_input(self, engine, session):
        wf = await engine.create_workflow(
            session,
            WorkflowCreate(
                name="M9 key source",
                steps=[
                    {"step_type": "custom_code", "definition": {
                        "code": "output['flat_value'] = {'v': 7}",
                    }},
                    {"step_type": "join", "definition": {
                        "sources": [{"key": "flat_value", "as": "from_branch"}],
                    }},
                ],
            ),
        )
        await session.refresh(wf, attribute_names=["steps"])
        producer, join = sorted(wf.steps, key=lambda s: s.position)
        producer.definition = {**producer.definition, "next_step_ids": [join.id]}
        wf.config = {"start_step_ids": [producer.id]}
        await session.commit()

        run = await engine.trigger_workflow(session, wf.id, WorkflowRunCreate())
        run = await wait_run(session, run.id)
        assert run.status == "completed", run.error_message
        await asyncio.sleep(0.3)

        instances = (await session.execute(
            select(StepInstance).where(StepInstance.workflow_run_id == run.id)
        )).scalars().all()
        join_instance = next(i for i in instances if i.step_id == join.id)
        assert join_instance.output_data["joined"] == {"from_branch": {"v": 7}}


class TestJoinPortability:
    def test_export_remaps_join_source_step_ids(self):
        id_map = {
            "step": {12: "step-12"},
            "form": {}, "group": {}, "user": {},
        }
        definition = WorkflowExportService()._remap_definition(
            {
                "next_step_ids": [12],
                "sources": [{"step_id": 12, "as": "upstream"}, {"key": "manual"}],
            },
            id_map,
        )
        assert definition["next_step_ids"] == ["step-12"]
        assert definition["sources"] == [
            {"step_id": "step-12", "as": "upstream"},
            {"key": "manual"},
        ]

    @pytest.mark.asyncio
    async def test_import_remaps_join_source_refs_to_new_steps(self, db_session):
        user = User(
            id=91, username="m9-importer", email="m9@test.local",
            password_hash="x", role="admin",
        )
        db_session.add(user)
        await db_session.flush()

        package = {
            "workflow": {
                "name": "M9 imported",
                "config": {"start_step_ids": ["step-1"]},
            },
            "steps": [
                {"refId": "step-1", "type": "delay", "position": 0, "definition": {"seconds": 0}},
                {
                    "refId": "step-2", "type": "join", "position": 1,
                    "definition": {"sources": [{"step_id": "step-1", "as": "upstream"}]},
                },
            ],
        }
        result = await WorkflowImportService().import_workflow(
            db_session, json.dumps(package), "m9.json", user.id, {"on_conflict": "copy"}
        )
        assert result.errors == [], result.errors

        wf = (await db_session.execute(
            select(Workflow).where(Workflow.name == "M9 imported")
        )).scalar_one()
        steps = (await db_session.execute(
            select(WorkflowStep)
            .where(WorkflowStep.workflow_id == wf.id)
            .order_by(WorkflowStep.position)
        )).scalars().all()
        assert wf.config["start_step_ids"] == [steps[0].id]
        assert steps[1].definition["sources"][0]["step_id"] == steps[0].id
