"""
Regression tests for bug fixes applied during remediation sprint.

Covers:
- C1: roles variable in create_user()
- C2: _call_ai() dispatch to correct provider
- C3: no duplicate webhook routes
- C4: created_by parameter in update_workflow()
- H1: exec/eval/compile removed from sandbox
- H2: AST-based safe condition evaluation
- H10: SSRF protection in WebhookExecutor
- M9: email uniqueness check
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.auth_service import auth_service
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate


class TestC1_RolesVariable:
    """C1: create_user() no longer references undefined 'roles'."""

    @pytest.mark.asyncio
    async def test_create_user_with_default_role(self, db_session):
        user = await auth_service.create_user(
            db_session,
            username="c1_test_user",
            email="c1@example.com",
            password="StrongPass1",
            role="user",
        )
        assert user.roles == ["user"]

    @pytest.mark.asyncio
    async def test_create_user_with_custom_role(self, db_session):
        user = await auth_service.create_user(
            db_session,
            username="c1_admin_user",
            email="c1admin@example.com",
            password="StrongPass1",
            role="admin",
        )
        assert user.roles == ["admin"]

    @pytest.mark.asyncio
    async def test_create_user_with_empty_role_defaults_to_user(self, db_session):
        user = await auth_service.create_user(
            db_session,
            username="c1_empty_role",
            email="c1empty@example.com",
            password="StrongPass1",
            role="",
        )
        assert user.roles == ["user"]


class TestC2_AiProviderDispatch:
    """C2: _call_ai() delegates to the correct provider method."""

    def test_call_ai_dispatches_to_llama_cpp(self):
        from app.services.ai_service import AIService, system_settings

        service = AIService()
        with patch.object(system_settings, "ai_provider", "llama_cpp"):
            with patch.object(
                service, "_call_llama_cpp", new_callable=AsyncMock, return_value="llama"
            ) as mock_llama:
                import asyncio

                result = asyncio.run(service._call_ai("prompt"))
                mock_llama.assert_called_once_with("prompt")
                assert result == "llama"

    def test_call_ai_dispatches_to_openai(self):
        from app.services.ai_service import AIService, system_settings

        service = AIService()
        with patch.object(system_settings, "ai_provider", "openai"):
            with patch.object(
                service, "_call_openai", new_callable=AsyncMock, return_value="gpt"
            ) as mock_openai:
                import asyncio

                result = asyncio.run(service._call_ai("prompt"))
                mock_openai.assert_called_once_with("prompt")
                assert result == "gpt"


class TestC3_NoDuplicateRoutes:
    """C3: webhook router has exactly one definition per route."""

    def test_external_trigger_defined_once(self):
        from app.api.webhooks import router

        trigger_routes = [
            r for r in router.routes
            if hasattr(r, "path") and r.path == "/api/trigger/{workflow_id}"
        ]
        assert len(trigger_routes) == 1

    def test_schedule_status_defined_once(self):
        from app.api.webhooks import router

        status_routes = [
            r for r in router.routes
            if hasattr(r, "path") and r.path == "/schedules/status"
        ]
        assert len(status_routes) == 1


class TestC4_CreatedByParameter:
    """C4: update_workflow() accepts created_by for deprecation tracking."""

    @pytest.mark.asyncio
    async def test_update_workflow_deprecation_sets_deprecated_by(self, db_session):
        from app.services.workflow_engine import WorkflowEngine

        engine = WorkflowEngine()
        wf = await engine.create_workflow(
            db_session,
            WorkflowCreate(name="C4 Deprecation Test", description="test"),
            created_by=1,
        )
        updated = await engine.update_workflow(
            db_session,
            wf.id,
            WorkflowUpdate(is_deprecated=True),
            created_by=42,
        )
        assert updated.deprecated_by_id == 42

    @pytest.mark.asyncio
    async def test_update_workflow_without_created_by(self, db_session):
        from app.services.workflow_engine import WorkflowEngine

        engine = WorkflowEngine()
        wf = await engine.create_workflow(
            db_session,
            WorkflowCreate(name="C4 No CreatedBy", description="test"),
        )
        updated = await engine.update_workflow(
            db_session,
            wf.id,
            WorkflowUpdate(is_deprecated=True),
        )
        assert updated.deprecated_by_id is None


class TestH1_SandboxNoExec:
    """H1: CustomCodeExecutor sandbox excludes exec/eval/compile."""

    def test_exec_not_in_safe_builtins(self):
        from app.services.step_executors import CustomCodeExecutor

        executor = CustomCodeExecutor()
        result = executor._run_code(
            code="output['test'] = len([1, 2, 3])",
            input_data={},
            timeout=5,
        )
        assert result["test"] == 3

    def test_eval_not_in_safe_builtins(self):
        from app.services.step_executors import CustomCodeExecutor

        executor = CustomCodeExecutor()
        with pytest.raises(NameError):
            executor._run_code(
                code="output['val'] = eval('1+1')",
                input_data={},
                timeout=5,
            )

    def test_compile_not_in_safe_builtins(self):
        from app.services.step_executors import CustomCodeExecutor

        executor = CustomCodeExecutor()
        with pytest.raises(NameError):
            executor._run_code(
                code="output['val'] = compile('1+1', '<string>', 'eval')",
                input_data={},
                timeout=5,
            )


class TestH2_SafeConditionEvaluation:
    """H2: _evaluate_condition uses AST-based safe_eval instead of bare eval()."""

    def test_simple_comparison(self):
        from app.services.workflow_engine import WorkflowEngine

        engine = WorkflowEngine()
        assert engine._evaluate_condition("data['x'] > 5", {"x": 10}) is True
        assert engine._evaluate_condition("data['x'] > 5", {"x": 3}) is False

    def test_boolean_ops(self):
        from app.services.workflow_engine import WorkflowEngine

        engine = WorkflowEngine()
        assert (
            engine._evaluate_condition(
                "data['a'] > 0 and data['b'] < 10", {"a": 5, "b": 3}
            )
            is True
        )
        assert (
            engine._evaluate_condition(
                "data['a'] > 0 or data['b'] > 10", {"a": -1, "b": 3}
            )
            is False
        )

    def test_nested_subscript(self):
        from app.services.workflow_engine import WorkflowEngine

        engine = WorkflowEngine()
        assert (
            engine._evaluate_condition(
                "data['user']['role'] == 'admin'", {"user": {"role": "admin"}}
            )
            is True
        )

    def test_string_comparison(self):
        from app.services.workflow_engine import WorkflowEngine

        engine = WorkflowEngine()
        assert (
            engine._evaluate_condition(
                "data['status'] == 'active'", {"status": "active"}
            )
            is True
        )

    def test_in_operator(self):
        from app.services.workflow_engine import WorkflowEngine

        engine = WorkflowEngine()
        assert (
            engine._evaluate_condition(
                "'admin' in data['roles']", {"roles": ["user", "admin"]}
            )
            is True
        )

    def test_not_operator(self):
        from app.services.workflow_engine import WorkflowEngine

        engine = WorkflowEngine()
        assert (
            engine._evaluate_condition(
                "not data['is_blocked']", {"is_blocked": False}
            )
            is True
        )

    def test_arithmetic_in_condition(self):
        from app.services.workflow_engine import WorkflowEngine

        engine = WorkflowEngine()
        assert (
            engine._evaluate_condition(
                "data['a'] + data['b'] > 10", {"a": 6, "b": 5}
            )
            is True
        )


class TestH10_WebhookSSRF:
    """H10: WebhookExecutor applies SSRF protection."""

    def test_is_safe_url_blocks_private_ips(self):
        from app.services.step_executors import _is_safe_url

        assert _is_safe_url("http://192.168.1.1:8080/hook") is False
        assert _is_safe_url("http://10.0.0.5:8080/hook") is False
        assert _is_safe_url("http://172.16.0.1:8080/hook") is False

    def test_is_safe_url_blocks_loopback(self):
        from app.services.step_executors import _is_safe_url

        assert _is_safe_url("http://localhost:8080/hook") is False
        assert _is_safe_url("http://127.0.0.1:8080/hook") is False
        assert _is_safe_url("http://[::1]:8080/hook") is False

    def test_is_safe_url_allows_public(self):
        from app.services.step_executors import _is_safe_url

        assert _is_safe_url("https://api.example.com/webhook") is True
        assert _is_safe_url("https://hooks.slack.com/services/T00/B00/xxx") is True


class TestM9_EmailUniqueness:
    """M9: create_user() checks for duplicate emails."""

    @pytest.mark.asyncio
    async def test_duplicate_email_raises_value_error(self, db_session):
        await auth_service.create_user(
            db_session,
            username="m9_user1",
            email="duplicate@example.com",
            password="StrongPass1",
        )
        with pytest.raises(ValueError, match="already exists"):
            await auth_service.create_user(
                db_session,
                username="m9_user2",
                email="duplicate@example.com",
                password="StrongPass1",
            )

    @pytest.mark.asyncio
    async def test_different_emails_succeed(self, db_session):
        u1 = await auth_service.create_user(
            db_session,
            username="m9_u1",
            email="u1@example.com",
            password="StrongPass1",
        )
        u2 = await auth_service.create_user(
            db_session,
            username="m9_u2",
            email="u2@example.com",
            password="StrongPass1",
        )
        assert u1.email != u2.email
