"""G6: SAGA-style compensating transactions / rollback on multi-step failure.

When a step fails mid-run, every previously completed step's side effect must be
undone in reverse order so a partial run does not leave dangling state. Tests
cover both the linear execution path and the graph (branching) path, plus the
unit-level compensation hooks on the base and API-call executors.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.workflow_engine as we_module
from app.schemas.workflow import WorkflowCreate, WorkflowRunCreate
from app.services.step_executors import BaseExecutor, APICallExecutor
from app.services.workflow_engine import WorkflowEngine


def _bind_engine(db_engine, monkeypatch):
    """Make a WorkflowEngine's background tasks use the test db_engine.

    ``_execute_workflow`` runs in a background task and reads the module-level
    ``async_session_factory``; without re-binding it to the test engine, that
    factory is bound to the import-time event loop and later tests hit
    "Future attached to a different loop". Mirrors the ``engine`` fixture in
    test_engine_behavior.py.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(we_module, "async_session_factory", factory)
    return WorkflowEngine()


@pytest.fixture
async def session(db_engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    async with async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s


async def wait_run(session, run_id, timeout=10.0):
    import asyncio

    from app.models.schemas import WorkflowRun

    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.05)
        run = await session.get(WorkflowRun, run_id)
        if run is not None:
            await session.refresh(run)
            if run.status in ("completed", "failed", "waiting"):
                return run
    raise AssertionError(f"run {run_id} did not finish in time")


import httpx


def _json_response(payload):
    """A real httpx.Response so response.headers/.json()/.text behave correctly."""
    return httpx.Response(
        status_code=200,
        headers={"content-type": "application/json"},
        json=payload,
    )


# --------------------------------------------------------------------------- #
# Unit-level compensation hooks
# --------------------------------------------------------------------------- #
class TestStepCompensationHooks:
    async def test_base_executor_compensate_is_noop(self):
        """A base executor with no compensate block is a safe no-op."""
        result = await BaseExecutor().compensate(
            input_data={}, step_definition={}, output_data=None, db=None
        )
        assert result == {"compensated": False, "note": "no-op"}

    async def test_api_call_executor_compensate_no_block(self):
        """An API call with no compensate block reports nothing was done."""
        ex = APICallExecutor()
        result = await ex.compensate(
            input_data={},
            step_definition={"method": "POST", "url": "http://api.example.com/x"},
            output_data=None,
            db=None,
        )
        assert result == {"compensated": False, "note": "no compensate block declared"}

    async def test_api_call_executor_compensate_issues_request(self):
        """A compensate block issues the configured request (e.g. a DELETE)."""
        calls = []

        def _side_effect(method, url, **kw):
            calls.append({"method": method, "url": str(url)})
            return _json_response({"ok": True})

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(side_effect=_side_effect)

        with patch("app.services.step_executors.httpx.AsyncClient", return_value=mock_client), \
             patch.object(APICallExecutor, "_is_safe_url", return_value=True):
            ex = APICallExecutor()
            result = await ex.compensate(
                input_data={},
                step_definition={
                    "method": "POST",
                    "url": "http://api.example.com/resource",
                    "compensate": {"method": "DELETE", "url": "http://api.example.com/resource"},
                },
                output_data={"status_code": 200},
                db=None,
            )

        assert result["compensated"] is True
        assert calls == [{"method": "DELETE", "url": "http://api.example.com/resource"}]


# --------------------------------------------------------------------------- #
# Linear-path compensation
# --------------------------------------------------------------------------- #
class _FakeCompExecutor(BaseExecutor):
    """Records execute/compensate calls; fails when the step definition says so."""

    def __init__(self):
        self.executed = []
        self.compensated = []

    async def execute(self, input_data, step_definition, db=None):
        name = step_definition.get("name", "step")
        self.executed.append(name)
        if step_definition.get("fail"):
            raise ValueError(f"{name} blew up")
        return {"step": name}

    async def compensate(self, input_data, step_definition, output_data, db=None):
        name = step_definition.get("name", "step")
        self.compensated.append(name)
        return {"compensated": True, "step": name}


class TestLinearCompensation:
    @pytest.fixture(autouse=True)
    def _register(self, db_engine, monkeypatch):
        self.engine = _bind_engine(db_engine, monkeypatch)
        self.fake = _FakeCompExecutor()
        monkeypatch.setattr(self.engine, "step_executors", {"comp": self.fake})

    async def test_failed_step_compensates_prior_steps_in_reverse_order(self, session):
        wf = await self.engine.create_workflow(
            session,
            WorkflowCreate(name="linear-comp", steps=[
                {"step_type": "comp", "definition": {"name": "A"}},
                {"step_type": "comp", "definition": {"name": "B"}},
                {"step_type": "comp", "definition": {"name": "C"}},
                {"step_type": "comp", "definition": {"name": "D", "fail": True}},
            ], config={}),
        )
        run = await self.engine.trigger_workflow(session, wf.id, WorkflowRunCreate())
        run = await wait_run(session, run.id)

        # The failing step failed; the run is not successful.
        assert run.status == "failed"

        # All four steps executed (A, B, C succeeded; D failed).
        assert self.fake.executed == ["A", "B", "C", "D"]

        # Prior completed steps were compensated in REVERSE order: C, B, A.
        assert self.fake.compensated == ["C", "B", "A"]

        # Audit trail on the run records each compensation (reverse order C, B, A).
        audit = run.custom_data.get("compensations") if run.custom_data else None
        assert audit is not None
        assert len(audit) == 3
        assert all(e["status"] == "compensated" for e in audit)
        assert [e["step_type"] for e in audit] == ["comp", "comp", "comp"]


# --------------------------------------------------------------------------- #
# Graph-path compensation
# --------------------------------------------------------------------------- #
class TestGraphCompensation:
    @pytest.fixture(autouse=True)
    def _register(self, db_engine, monkeypatch):
        self.engine = _bind_engine(db_engine, monkeypatch)
        self.fake = _FakeCompExecutor()
        monkeypatch.setattr(self.engine, "step_executors", {"comp": self.fake})

    async def test_graph_branch_failure_compensates_completed_steps(self, session):
        # A -> B (fails) ; A -> C (skipped). B's failure must compensate A.
        wf = await self.engine.create_workflow(
            session,
            WorkflowCreate(name="graph-comp", steps=[
                {"step_type": "comp", "definition": {"name": "A"}},
                {
                    "step_type": "comp",
                    "definition": {"name": "B", "fail": True},
                    "next_step_id": "c",
                },
                {"step_type": "comp", "definition": {"name": "C"}, "id": "c"},
            ], config={}),
        )
        run = await self.engine.trigger_workflow(session, wf.id, WorkflowRunCreate())
        run = await wait_run(session, run.id)

        assert run.status == "failed"
        # A executed and was compensated; B executed (and failed); C never ran.
        assert "A" in self.fake.executed
        assert "B" in self.fake.executed
        assert "C" not in self.fake.executed
        assert self.fake.compensated == ["A"]

        audit = run.custom_data.get("compensations") if run.custom_data else None
        assert audit and len(audit) == 1 and audit[0]["status"] == "compensated"


# --------------------------------------------------------------------------- #
# API-call compensation on a real executor
# --------------------------------------------------------------------------- #
class TestAPICallCompensation:
    async def test_api_call_compensated_on_subsequent_failure(self, session, db_engine, monkeypatch):
        calls = []

        def _side_effect(method, url, **kw):
            calls.append({"method": method, "url": str(url)})
            return _json_response({"ok": True})

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(side_effect=_side_effect)

        monkeypatch.setattr(
            "app.services.step_executors.httpx.AsyncClient", lambda *a, **k: mock_client
        )
        monkeypatch.setattr(
            APICallExecutor, "_is_safe_url", lambda self, url, allow_loopback=False: True
        )

        class _Failing(BaseExecutor):
            async def execute(self, input_data, step_definition, db=None):
                raise ValueError("downstream failed")

        engine = _bind_engine(db_engine, monkeypatch)
        real = dict(engine.step_executors)
        real["fail"] = _Failing()
        monkeypatch.setattr(engine, "step_executors", real)

        wf = await engine.create_workflow(
            session,
            WorkflowCreate(name="api-comp", steps=[
                {
                    "step_type": "api_call",
                    "definition": {
                        "method": "POST",
                        "url": "http://api.example.com/resource",
                        "compensate": {"method": "DELETE", "url": "http://api.example.com/resource"},
                    },
                },
                {"step_type": "fail", "definition": {}},
            ], config={}),
        )
        run = await engine.trigger_workflow(session, wf.id, WorkflowRunCreate())
        run = await wait_run(session, run.id)

        assert run.status == "failed"
        # A POST was made to create the resource and a compensating DELETE followed.
        methods = [c["method"] for c in calls]
        assert "POST" in methods
        assert "DELETE" in methods
        assert calls[-1] == {"method": "DELETE", "url": "http://api.example.com/resource"}
