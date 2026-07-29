"""
Tests for the workflow engine and AI service
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, async_session_factory
from app.services.workflow_engine import WorkflowEngine
from app.services.ai_service import AIService
from app.schemas.workflow import WorkflowCreate, WorkflowRunCreate


@pytest.fixture
async def db_session():
    """Create a test database session"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()
    
    await engine.dispose()


@pytest.fixture
def workflow_engine():
    """Create workflow engine instance"""
    return WorkflowEngine()


@pytest.fixture
def ai_service():
    """Create AI service instance"""
    return AIService()


class TestWorkflowEngine:
    """Test workflow engine functionality"""
    
    @pytest.mark.asyncio
    async def test_create_workflow(self, db_session, workflow_engine):
        """Test creating a workflow"""
        workflow_data = WorkflowCreate(
            name="Test Workflow",
            description="A test workflow",
            steps=[
                {
                    "step_type": "api_call",
                    "definition": {"method": "GET", "url": "https://api.example.com/data"}
                },
                {
                    "step_type": "email",
                    "definition": {"to": "test@example.com", "subject": "Test"}
                }
            ]
        )
        
        workflow = await workflow_engine.create_workflow(db_session, workflow_data)
        
        assert workflow.id is not None
        assert workflow.name == "Test Workflow"
        assert len(workflow.steps) == 2
    
    @pytest.mark.asyncio
    async def test_update_workflow(self, db_session, workflow_engine):
        """Test updating a workflow"""
        from app.schemas.workflow import WorkflowUpdate
        
        # Create workflow
        workflow_data = WorkflowCreate(name="Original", description="Desc")
        workflow = await workflow_engine.create_workflow(db_session, workflow_data)
        
        # Update workflow
        update_data = WorkflowUpdate(name="Updated", description="New desc")
        updated = await workflow_engine.update_workflow(db_session, workflow.id, update_data)
        
        assert updated.name == "Updated"
        assert updated.version == 2
    
    @pytest.mark.asyncio
    async def test_delete_workflow(self, db_session, workflow_engine):
        """Test deleting a workflow"""
        workflow_data = WorkflowCreate(name="To Delete", description="Will be deleted")
        workflow = await workflow_engine.create_workflow(db_session, workflow_data)
        
        result = await workflow_engine.delete_workflow(db_session, workflow.id)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_trigger_workflow(self, db_session, workflow_engine):
        """Test triggering a workflow run"""
        # Create workflow with steps
        workflow_data = WorkflowCreate(
            name="Trigger Test",
            steps=[
                {
                    "step_type": "delay",
                    "definition": {"seconds": 1}
                }
            ]
        )
        workflow = await workflow_engine.create_workflow(db_session, workflow_data)
        
        # Trigger run
        run_data = WorkflowRunCreate(triggered_by="test")
        run = await workflow_engine.trigger_workflow(db_session, workflow.id, run_data)
        
        assert run.id is not None
        assert run.status == "pending"


class TestAIService:
    """Test AI service functionality"""
    
    def test_validate_step(self, ai_service):
        """Test step validation"""
        # Valid step
        valid_step = {
            "step_type": "api_call",
            "definition": {"method": "GET", "url": "https://example.com"}
        }
        ai_service._validate_step(valid_step)  # Should not raise
        
        # Invalid step type
        invalid_step = {
            "step_type": "invalid_type",
            "definition": {}
        }
        with pytest.raises(ValueError, match="Invalid step type"):
            ai_service._validate_step(invalid_step)
    
    def test_validate_form_schema(self, ai_service):
        """Test form schema validation"""
        # Valid schema
        valid_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "title": "Name"},
                "email": {"type": "string", "title": "Email"}
            }
        }
        ai_service._validate_form_schema(valid_schema)  # Should not raise
        
        # Invalid schema
        invalid_schema = {"type": "array"}
        with pytest.raises(ValueError, match="must have type 'object'"):
            ai_service._validate_form_schema(invalid_schema)


class TestStepExecutors:
    """Test step executors"""
    
    @pytest.mark.asyncio
    async def test_delay_executor(self):
        """Test delay executor"""
        from app.services.step_executors import DelayExecutor
        
        executor = DelayExecutor()
        result = await executor.execute({}, {"seconds": 0})
        
        assert result["delayed_by"] == 0
        assert "executed_at" in result
    
    @pytest.mark.asyncio
    async def test_condition_executor(self):
        """Test condition executor"""
        from app.services.step_executors import ConditionExecutor
        
        executor = ConditionExecutor()
        
        # True condition
        result = await executor.execute({"value": 10}, {"expression": "data['value'] > 5"})
        assert result["condition_met"] is True
        
        # False condition
        result = await executor.execute({"value": 3}, {"expression": "data['value'] > 5"})
        assert result["condition_met"] is False
