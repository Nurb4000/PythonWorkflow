"""M6: conditional failure handling and try/catch boundaries.

Covers both routing mechanisms:

* ``on_failure_target_step_id`` on an ordinary step (linear and graph mode)
* the ``try_catch`` container executor (nested try/catch steps + compensation)

Run with: pytest backend/tests/test_try_catch.py -q
"""
import asyncio
import time
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.schemas import StepInstance, Workflow, WorkflowRun
from app.schemas.workflow import WorkflowCreate, WorkflowRunCreate
from app.services import workflow_engine as we_module
from app.services.step_executors import BaseExecutor, TryCatchExecutor
from app.services.workflow_engine import WorkflowEngine, workflow_engine as engine_singleton


@pytest_asyncio.fixture
async def session(db_engine):
    async with async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def engine(db_engine, monkeypatch):
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(we_module, "async_session_factory", factory)
    return WorkflowEngine()


async def create_workflow(engine, session, steps, config=None):
    wf = await engine.create_workflow(
        session, WorkflowCreate(name="M6", steps=steps, config=config or {})
    )
    await session.refresh(wf, attribute_names=["steps"])
    return wf


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


async def instances_for(session, run_id):
    rows = (await session.execute(
        select(StepInstance).where(StepInstance.workflow_run_id == run_id)
    )).scalars().all()
    return {i.step_id: i for i in rows}


class _FailingCode:
    """Custom-code definition that always raises after retries are exhausted."""

    DEFINITION = {"code": "raise ValueError('boom')"}
    ERROR = "Custom code execution failed: boom"


class TestTryCatchExecutorUnit:
    @pytest.mark.asyncio
    async def test_catches_failure_and_injects_error_context(self):
        ex = TryCatchExecutor()
        result = await ex.execute(
            {"value": 1},
            {
                "try_steps": [
                    {"step_type": "custom_code", "definition": _FailingCode.DEFINITION},
                ],
                "catch_steps": [
                    {"step_type": "custom_code", "definition": {
                        "code": (
                            "output['message'] = input_data['error'] + ':' + input_data['error_type']; "
                            "output['failed_type'] = input_data.get('_failed_step_type')"
                        ),
                    }},
                ],
            },
        )
        assert result["caught"] is True
        assert result["error"] == _FailingCode.ERROR
        assert result["error_type"] == "ValueError"
        assert result["try_results"][0]["output"] == {}
        assert result["try_results"][0]["error"] == _FailingCode.ERROR
        catch_output = result["catch_results"][0]["output"]
        assert catch_output["message"] == f"{_FailingCode.ERROR}:ValueError"
        assert catch_output["failed_type"] == "custom_code"

    @pytest.mark.asyncio
    async def test_no_failure_runs_only_try_steps(self):
        ex = TryCatchExecutor()
        result = await ex.execute(
            {"x": 1},
            {
                "try_steps": [
                    {"step_type": "calculation", "definition": {"expression": "data['x'] + 1"}},
                ],
                "catch_steps": [
                    {"step_type": "custom_code", "definition": {"code": "output['bad'] = True"}},
                ],
            },
        )
        assert result["caught"] is False
        assert result["error"] is None
        assert result["try_results"][0]["output"]["result"] == 2
        assert result["catch_results"] == []

    @pytest.mark.asyncio
    async def test_error_filter_false_reraises_original_error(self):
        ex = TryCatchExecutor()
        with pytest.raises(ValueError, match="boom"):
            await ex.execute(
                {},
                {
                    "try_steps": [
                        {"step_type": "custom_code", "definition": _FailingCode.DEFINITION},
                    ],
                    "catch_steps": [],
                    "error_filter": "data['error_type'] == 'RuntimeError'",
                },
            )

    @pytest.mark.asyncio
    async def test_compensates_completed_try_steps_in_reverse_order(self, monkeypatch):
        calls = []

        class RecordingExecutor(BaseExecutor):
            def __init__(self, name, fail=False):
                self.name = name
                self.fail = fail

            async def execute(self, input_data, step_definition, db=None):
                calls.append(("execute", self.name))
                if self.fail:
                    raise RuntimeError("boom")
                return {"marker": self.name}

            async def compensate(self, input_data, step_definition, output_data, db=None):
                calls.append(("compensate", self.name))
                return {"undone": self.name}

        monkeypatch.setitem(engine_singleton.step_executors, "m6_first", RecordingExecutor("first"))
        monkeypatch.setitem(engine_singleton.step_executors, "m6_second", RecordingExecutor("second"))
        monkeypatch.setitem(
            engine_singleton.step_executors, "m6_third", RecordingExecutor("third", fail=True)
        )

        result = await TryCatchExecutor().execute(
            {},
            {
                "try_steps": [
                    {"step_type": "m6_first", "definition": {}},
                    {"step_type": "m6_second", "definition": {}},
                    {"step_type": "m6_third", "definition": {}},
                ],
                "catch_steps": [
                    {"step_type": "custom_code", "definition": {"code": "output['caught'] = True"}},
                ],
            },
        )
        assert result["caught"] is True
        assert calls == [
            ("execute", "first"),
            ("execute", "second"),
            ("execute", "third"),
            ("compensate", "second"),
            ("compensate", "first"),
        ]
        assert [c["detail"]["undone"] for c in result["compensations"]] == ["second", "first"]

    @pytest.mark.asyncio
    async def test_compensation_can_be_disabled(self, monkeypatch):
        calls = []

        class RecordingExecutor(BaseExecutor):
            async def execute(self, input_data, step_definition, db=None):
                return {"ok": True}

            async def compensate(self, input_data, step_definition, output_data, db=None):
                calls.append("compensate")
                return {}

        class FailingExecutor(BaseExecutor):
            async def execute(self, input_data, step_definition, db=None):
                raise RuntimeError("boom")

        monkeypatch.setitem(engine_singleton.step_executors, "m6_nc_ok", RecordingExecutor())
        monkeypatch.setitem(engine_singleton.step_executors, "m6_nc_fail", FailingExecutor())

        result = await TryCatchExecutor().execute(
            {},
            {
                "try_steps": [
                    {"step_type": "m6_nc_ok", "definition": {}},
                    {"step_type": "m6_nc_fail", "definition": {}},
                ],
                "catch_steps": [],
                "compensate_try_steps": False,
            },
        )
        assert result["compensations"] == []
        assert calls == []

    @pytest.mark.asyncio
    async def test_invalid_nested_step_fails_closed(self):
        with pytest.raises(ValueError, match="non-empty 'try_steps'"):
            await TryCatchExecutor().execute({}, {"try_steps": []})
        with pytest.raises(ValueError, match="step_type"):
            await TryCatchExecutor().execute(
                {}, {"try_steps": [{"definition": {}}], "catch_steps": []}
            )


class TestFailureRouting:
    def _failure_target_step_id(self, step, error, filter_expr=None, step_id=1):
        return WorkflowEngine()._failure_target_step_id(
            SimpleNamespace(
                step_type="custom_code",
                definition={
                    "on_failure_target_step_id": 7,
                    "on_failure_filter": filter_expr,
                },
            ),
            error,
            str(error),
            SimpleNamespace(step_id=step_id),
        )

    def test_filter_selects_by_error_type(self):
        assert self._failure_target_step_id(
            None, ValueError("boom"), "data['error_type'] == 'ValueError'"
        ) == 7
        assert self._failure_target_step_id(
            None, ValueError("boom"), "data['error_type'] == 'RuntimeError'"
        ) is None

    def test_invalid_filter_and_self_target_fail_closed(self):
        assert self._failure_target_step_id(None, ValueError("boom"), "data['nope'") is None
        assert self._failure_target_step_id(
            None, ValueError("boom"), step_id=7
        ) is None

    @pytest.mark.asyncio
    async def test_linear_failure_routes_to_handler_and_skips_middle_step(self, engine, session):
        wf = await create_workflow(
            engine, session,
            [
                {"step_type": "custom_code", "definition": dict(_FailingCode.DEFINITION)},
                {"step_type": "calculation", "definition": {"expression": "1 + 1"}},
                {"step_type": "custom_code", "definition": {
                    "code": "output['handled'] = input_data['error'] + ':' + str(input_data['_failed_step_id'])",
                }},
            ],
            config={"start_step_ids": None},
        )
        failed, skipped, handler = sorted(wf.steps, key=lambda s: s.position)
        failed.definition = {**failed.definition, "on_failure_target_step_id": handler.id}
        await session.commit()

        run = await engine.trigger_workflow(session, wf.id, WorkflowRunCreate())
        run = await wait_run(session, run.id)

        assert run.status == "completed", run.error_message
        by_step = await instances_for(session, run.id)
        assert by_step[failed.id].status == "failed"
        assert by_step[skipped.id].status == "skipped"
        assert by_step[failed.id].custom_data["route_taken"] == [handler.id]
        assert by_step[failed.id].custom_data["error_handled"] is True
        assert by_step[skipped.id].custom_data["route_taken"] == [handler.id]
        assert by_step[handler.id].status == "completed"
        assert by_step[handler.id].output_data["handled"] == f"{_FailingCode.ERROR}:{failed.id}"
        assert run.input_data["_last_error"] == _FailingCode.ERROR
        assert run.input_data["_failed_step_id"] == failed.id

    @pytest.mark.asyncio
    async def test_graph_failure_routes_via_failure_edge(self, engine, session):
        wf = await create_workflow(
            engine, session,
            [
                {"step_type": "custom_code", "definition": dict(_FailingCode.DEFINITION)},
                {"step_type": "calculation", "definition": {"expression": "1 + 1"}},
                {"step_type": "custom_code", "definition": {
                    "code": "output['handled'] = input_data['_last_error']",
                }},
            ],
            config={"start_step_ids": None},
        )
        failed, orphan, handler = sorted(wf.steps, key=lambda s: s.position)
        failed.definition = {**failed.definition, "on_failure_target_step_id": handler.id}
        wf.config = {"start_step_ids": [failed.id]}
        await session.commit()

        run = await engine.trigger_workflow(session, wf.id, WorkflowRunCreate())
        run = await wait_run(session, run.id)

        assert run.status == "completed", run.error_message
        by_step = await instances_for(session, run.id)
        assert by_step[failed.id].status == "failed"
        assert by_step[failed.id].custom_data["route_taken"] == [handler.id]
        assert by_step[orphan.id].status == "skipped"
        assert by_step[handler.id].status == "completed"
        assert by_step[handler.id].output_data["handled"] == _FailingCode.ERROR

    @pytest.mark.asyncio
    async def test_inspector_exposes_failure_routing(self, engine, session):
        wf = await create_workflow(
            engine, session,
            [
                {"step_type": "custom_code", "definition": dict(_FailingCode.DEFINITION)},
                {"step_type": "custom_code", "definition": {
                    "code": "output['handled'] = input_data['_last_error']",
                }},
            ],
        )
        failed, handler = sorted(wf.steps, key=lambda s: s.position)
        failed.definition = {
            **failed.definition,
            "on_failure_target_step_id": handler.id,
            "on_failure_filter": "data['error_type'] == 'ValueError'",
        }
        await session.commit()

        run = await engine.trigger_workflow(session, wf.id, WorkflowRunCreate())
        run = await wait_run(session, run.id)
        assert run.status == "completed", run.error_message
        await asyncio.sleep(0.2)

        from app.api.workflow_runs import get_run_inspector

        payload = await get_run_inspector(
            run.id, SimpleNamespace(role="admin", username="tester"), session
        )
        graph_step = next(s for s in payload["graph"]["steps"] if s["id"] == failed.id)
        assert graph_step["on_failure_target_step_id"] == handler.id
        assert graph_step["on_failure_filter"] == "data['error_type'] == 'ValueError'"
        failed_instance = next(i for i in payload["steps"] if i.step_id == failed.id)
        assert failed_instance.custom_data["error_handled"] is True
        assert failed_instance.custom_data["on_failure_target_step_id"] == handler.id

    @pytest.mark.asyncio
    async def test_try_catch_step_inside_workflow_continues_run(self, engine, session):
        wf = await create_workflow(
            engine, session,
            [
                {"step_type": "try_catch", "definition": {
                    "try_steps": [
                        {"step_type": "custom_code", "definition": _FailingCode.DEFINITION},
                    ],
                    "catch_steps": [
                        {"step_type": "custom_code", "definition": {
                            "code": "output['caught_error'] = input_data['error']",
                        }},
                    ],
                }},
                {"step_type": "custom_code", "definition": {
                    "code": (
                        "output['result'] = 1 if input_data.get('caught') "
                        "and input_data.get('error') == 'Custom code execution failed: boom' else 0"
                    ),
                }},
            ],
            config={"start_step_ids": None},
        )
        await session.commit()

        run = await engine.trigger_workflow(session, wf.id, WorkflowRunCreate())
        run = await wait_run(session, run.id)

        assert run.status == "completed", run.error_message
        by_step = await instances_for(session, run.id)
        assert len(by_step) == 2
        assert all(i.status == "completed" for i in by_step.values())
        downstream = next(i for i in by_step.values() if i.output_data.get("result") is not None)
        assert downstream.output_data["result"] == 1
