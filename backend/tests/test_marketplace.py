"""
Tests for marketplace models, service, and API endpoints.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.marketplace import MarketplaceItem, SavedNodeTemplate
from app.models.auth import User
from app.services.marketplace_service import marketplace_service


@pytest.fixture
async def db_session():
    """In-memory SQLite session with all tables created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()

    await engine.dispose()


@pytest.fixture
def mock_user():
    """Mock authenticated user."""
    user = MagicMock(spec=User)
    user.id = 1
    user.username = "testdev"
    user.role = "developer"
    user.email = "dev@example.com"
    return user


@pytest.fixture
def mock_admin():
    """Mock admin user."""
    user = MagicMock(spec=User)
    user.id = 2
    user.username = "adminuser"
    user.role = "admin"
    user.email = "admin@example.com"
    return user


# ── Model round-trip tests ────────────────────────────────────────────

class TestMarketplaceItemModel:
    @pytest.mark.asyncio
    async def test_create_and_retrieve(self, db_session):
        item = MarketplaceItem(
            item_type="workflow",
            name="Test Workflow Package",
            description="A test package",
            category="Data / ETL",
            author_id=1,
            content='<WorkflowPackage version="1.0"></WorkflowPackage>',
            content_format="xml",
            status="published",
        )
        item.tags_list = ["etl", "data"]

        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        assert item.id is not None
        assert item.item_type == "workflow"
        assert item.name == "Test Workflow Package"
        assert item.tags_list == ["etl", "data"]
        assert item.downloads_count == 0

    @pytest.mark.asyncio
    async def test_tags_serialization(self, db_session):
        item = MarketplaceItem(
            item_type="node",
            name="API Node",
            author_id=1,
            content=json.dumps({"step_type": "api_call", "definition": {"method": "GET", "url": "https://example.com"}}),
            content_format="json",
            node_type="api_call",
        )
        item.tags_list = ["api", "http"]
        db_session.add(item)
        await db_session.commit()

        from sqlalchemy import select
        result = await db_session.execute(select(MarketplaceItem).where(MarketplaceItem.id == item.id))
        loaded = result.scalar_one()
        assert loaded.tags_list == ["api", "http"]
        assert loaded.tags == '["api", "http"]'


class TestSavedNodeTemplateModel:
    @pytest.mark.asyncio
    async def test_create_and_retrieve(self, db_session):
        node = SavedNodeTemplate(
            user_id=1,
            step_type="email",
            title="Send Notification",
            description="Sends an email notification",
            condition_expr="",
            is_enabled=True,
            max_retries=2,
            retry_delay_seconds=30,
        )
        node.definition_dict = {"to": "user@example.com", "subject": "Hello"}

        db_session.add(node)
        await db_session.commit()
        await db_session.refresh(node)

        assert node.id is not None
        assert node.step_type == "email"
        assert node.definition_dict == {"to": "user@example.com", "subject": "Hello"}
        assert node.max_retries == 2


# ── Service CRUD tests ────────────────────────────────────────────────

class TestMarketplaceService:
    @pytest.mark.asyncio
    async def test_create_workflow_item(self, db_session):
        item = await marketplace_service.create_item(
            db_session,
            item_type="workflow",
            name="My Workflow",
            description="Does things",
            category="Integrations",
            tags=["integration", "api"],
            author_id=1,
            content=json.dumps({"workflow": {"name": "My Workflow"}, "steps": []}),
            content_format="json",
        )
        assert item.id is not None
        assert item.item_type == "workflow"
        assert item.name == "My Workflow"
        assert item.tags_list == ["integration", "api"]

    @pytest.mark.asyncio
    async def test_create_node_item(self, db_session):
        node_content = json.dumps({
            "step_type": "api_call",
            "title": "Fetch Data",
            "definition": {"method": "GET", "url": "https://api.example.com/data"},
        })
        item = await marketplace_service.create_item(
            db_session,
            item_type="node",
            name="Fetch Data Node",
            description="GET request node",
            category="Integrations",
            tags=["api"],
            author_id=1,
            content=node_content,
            content_format="json",
            node_type="api_call",
        )
        assert item.item_type == "node"
        assert item.node_type == "api_call"

    @pytest.mark.asyncio
    async def test_create_invalid_item_type(self, db_session):
        with pytest.raises(ValueError, match="item_type must be"):
            await marketplace_service.create_item(
                db_session,
                item_type="invalid",
                name="X",
                description="",
                category="General",
                tags=[],
                author_id=1,
                content="{}",
                content_format="json",
            )

    @pytest.mark.asyncio
    async def test_create_invalid_content_format(self, db_session):
        with pytest.raises(ValueError, match="content_format must be"):
            await marketplace_service.create_item(
                db_session,
                item_type="workflow",
                name="X",
                description="",
                category="General",
                tags=[],
                author_id=1,
                content="{}",
                content_format="yaml",
            )

    @pytest.mark.asyncio
    async def test_create_invalid_category(self, db_session):
        with pytest.raises(ValueError, match="category must be one of"):
            await marketplace_service.create_item(
                db_session,
                item_type="workflow",
                name="X",
                description="",
                category="Nonexistent Category",
                tags=[],
                author_id=1,
                content="{}",
                content_format="json",
            )

    @pytest.mark.asyncio
    async def test_node_validation_missing_step_type(self, db_session):
        with pytest.raises(ValueError, match="must include 'step_type'"):
            await marketplace_service.create_item(
                db_session,
                item_type="node",
                name="Bad Node",
                description="",
                category="General",
                tags=[],
                author_id=1,
                content=json.dumps({"definition": {}}),
                content_format="json",
            )

    @pytest.mark.asyncio
    async def test_node_validation_invalid_step_type(self, db_session):
        with pytest.raises(ValueError, match="Invalid step_type"):
            await marketplace_service.create_item(
                db_session,
                item_type="node",
                name="Bad Node",
                description="",
                category="General",
                tags=[],
                author_id=1,
                content=json.dumps({"step_type": "nonexistent_type", "definition": {}}),
                content_format="json",
            )

    @pytest.mark.asyncio
    async def test_node_validation_missing_required_field(self, db_session):
        with pytest.raises(ValueError, match="Missing required field 'method'"):
            await marketplace_service.create_item(
                db_session,
                item_type="node",
                name="Bad Node",
                description="",
                category="General",
                tags=[],
                author_id=1,
                content=json.dumps({"step_type": "api_call", "definition": {"url": "https://x.com"}}),
                content_format="json",
            )

    @pytest.mark.asyncio
    async def test_secrets_blocked_for_workflow(self, db_session):
        content = json.dumps({
            "workflow": {"name": "Bad"},
            "steps": [{"definition": {"url": "https://api.example.com?api_key='sk-1234567890abcdefghij'"}}]
        })
        with pytest.raises(ValueError, match="contains potential secrets"):
            await marketplace_service.create_item(
                db_session,
                item_type="workflow",
                name="Secret Workflow",
                description="",
                category="General",
                tags=[],
                author_id=1,
                content=content,
                content_format="json",
            )

    @pytest.mark.asyncio
    async def test_secrets_warned_for_node(self, db_session):
        content = json.dumps({
            "step_type": "api_call",
            "definition": {"method": "GET", "url": "https://api.example.com?api_key='sk-1234567890abcdefghij'"}
        })
        item = await marketplace_service.create_item(
            db_session,
            item_type="node",
            name="Node with Secret",
            description="",
            category="General",
            tags=[],
            author_id=1,
            content=content,
            content_format="json",
            node_type="api_call",
        )
        assert item.id is not None

    @pytest.mark.asyncio
    async def test_get_item(self, db_session):
        item = await marketplace_service.create_item(
            db_session,
            item_type="workflow",
            name="Findable",
            description="",
            category="General",
            tags=[],
            author_id=1,
            content="{}",
            content_format="json",
        )
        found = await marketplace_service.get_item(db_session, item.id)
        assert found is not None
        assert found.name == "Findable"

        missing = await marketplace_service.get_item(db_session, 9999)
        assert missing is None

    @pytest.mark.asyncio
    async def test_update_item_by_author(self, db_session):
        item = await marketplace_service.create_item(
            db_session,
            item_type="workflow",
            name="Original",
            description="",
            category="General",
            tags=[],
            author_id=1,
            content="{}",
            content_format="json",
        )
        updated = await marketplace_service.update_item(
            db_session, item_id=item.id, author_id=1, is_admin=False, name="Updated Name"
        )
        assert updated.name == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_item_by_non_author_rejected(self, db_session):
        item = await marketplace_service.create_item(
            db_session,
            item_type="workflow",
            name="Protected",
            description="",
            category="General",
            tags=[],
            author_id=1,
            content="{}",
            content_format="json",
        )
        with pytest.raises(ValueError, match="Only the author or an admin"):
            await marketplace_service.update_item(
                db_session, item_id=item.id, author_id=99, is_admin=False, name="Hacked"
            )

    @pytest.mark.asyncio
    async def test_update_item_by_admin(self, db_session):
        item = await marketplace_service.create_item(
            db_session,
            item_type="workflow",
            name="Admin Target",
            description="",
            category="General",
            tags=[],
            author_id=1,
            content="{}",
            content_format="json",
        )
        updated = await marketplace_service.update_item(
            db_session, item_id=item.id, author_id=2, is_admin=True, name="Admin Updated"
        )
        assert updated.name == "Admin Updated"

    @pytest.mark.asyncio
    async def test_delete_item_by_author(self, db_session):
        item = await marketplace_service.create_item(
            db_session,
            item_type="workflow",
            name="ToDelete",
            description="",
            category="General",
            tags=[],
            author_id=1,
            content="{}",
            content_format="json",
        )
        deleted = await marketplace_service.delete_item(
            db_session, item_id=item.id, author_id=1, is_admin=False
        )
        # Deletes are soft archives: the row stays for provenance/download history
        assert deleted is not None
        assert deleted.status == "archived"
        assert deleted.is_active is False
        remaining = await marketplace_service.get_item(db_session, item.id)
        assert remaining is not None
        assert remaining.status == "archived"

    @pytest.mark.asyncio
    async def test_delete_item_archived_by_admin(self, db_session):
        item = await marketplace_service.create_item(
            db_session,
            item_type="workflow",
            name="ToArchive",
            description="",
            category="General",
            tags=[],
            author_id=1,
            content="{}",
            content_format="json",
        )
        archived = await marketplace_service.delete_item(
            db_session, item_id=item.id, author_id=2, is_admin=True, archive_only=True
        )
        assert archived.status == "archived"
        assert archived.is_active is False


# ── List / Search / Filter / Sort / Pagination ────────────────────────

class TestMarketplaceList:
    @pytest.mark.asyncio
    async def _seed_items(self, db_session):
        for i in range(6):
            await marketplace_service.create_item(
                db_session,
                item_type="workflow" if i < 4 else "node",
                name=f"Workflow {i}" if i < 4 else f"Node {i}",
                description=f"Description for item {i}",
                category="Data / ETL" if i % 2 == 0 else "Notifications",
                tags=[f"tag{i}"] if i < 3 else [],
                author_id=1,
                content=json.dumps({"step_type": "api_call", "definition": {"method": "GET", "url": "https://x.com"}}) if i >= 4 else "{}",
                content_format="json",
                node_type="api_call" if i >= 4 else None,
            )

    @pytest.mark.asyncio
    async def test_list_default_published_only(self, db_session):
        await self._seed_items(db_session)
        items, total = await marketplace_service.list_items(db_session)
        assert total == 6
        assert len(items) == 6

    @pytest.mark.asyncio
    async def test_filter_by_item_type(self, db_session):
        await self._seed_items(db_session)
        workflows, wf_total = await marketplace_service.list_items(db_session, item_type="workflow")
        assert wf_total == 4
        nodes, node_total = await marketplace_service.list_items(db_session, item_type="node")
        assert node_total == 2

    @pytest.mark.asyncio
    async def test_filter_by_category(self, db_session):
        await self._seed_items(db_session)
        items, total = await marketplace_service.list_items(db_session, category="Data / ETL")
        assert total == 3

    @pytest.mark.asyncio
    async def test_search_by_name(self, db_session):
        await self._seed_items(db_session)
        items, total = await marketplace_service.list_items(db_session, search="Workflow 1")
        assert total == 1
        assert items[0]["name"] == "Workflow 1"

    @pytest.mark.asyncio
    async def test_search_by_description(self, db_session):
        await self._seed_items(db_session)
        items, total = await marketplace_service.list_items(db_session, search="item 3")
        assert total == 1

    @pytest.mark.asyncio
    async def test_sort_by_name_asc(self, db_session):
        await self._seed_items(db_session)
        items, _ = await marketplace_service.list_items(db_session, sort_by="name", sort_order="asc")
        names = [i["name"] for i in items]
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_pagination(self, db_session):
        await self._seed_items(db_session)
        page1, total = await marketplace_service.list_items(db_session, offset=0, limit=3)
        assert total == 6
        assert len(page1) == 3
        page2, _ = await marketplace_service.list_items(db_session, offset=3, limit=3)
        assert len(page2) == 3
        assert page1[0]["id"] != page2[0]["id"]


# ── Saved Node Template tests ────────────────────────────────────────

class TestSavedNodeTemplates:
    @pytest.mark.asyncio
    async def test_create_and_list(self, db_session):
        node = await marketplace_service.create_saved_node(
            db_session,
            user_id=1,
            step_type="email",
            title="My Email Node",
            description="Sends emails",
            definition={"to": "test@example.com", "subject": "Test"},
        )
        assert node.id is not None
        assert node.step_type == "email"

        nodes = await marketplace_service.list_saved_nodes(db_session, user_id=1)
        assert len(nodes) == 1
        assert nodes[0].title == "My Email Node"

    @pytest.mark.asyncio
    async def test_create_invalid_step_type(self, db_session):
        with pytest.raises(ValueError, match="Invalid step_type"):
            await marketplace_service.create_saved_node(
                db_session,
                user_id=1,
                step_type="nonexistent",
                title="Bad",
                description="",
                definition={},
            )

    @pytest.mark.asyncio
    async def test_delete_owned_node(self, db_session):
        node = await marketplace_service.create_saved_node(
            db_session,
            user_id=1,
            step_type="delay",
            title="Delay Node",
            description="",
            definition={"seconds": 5},
        )
        result = await marketplace_service.delete_saved_node(db_session, node.id, user_id=1)
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_unowned_node_rejected(self, db_session):
        node = await marketplace_service.create_saved_node(
            db_session,
            user_id=1,
            step_type="delay",
            title="Delay Node",
            description="",
            definition={"seconds": 5},
        )
        with pytest.raises(ValueError, match="not found or access denied"):
            await marketplace_service.delete_saved_node(db_session, node.id, user_id=99)


# ── Categories / Tags ────────────────────────────────────────────────

class TestCategories:
    @pytest.mark.asyncio
    async def test_categories_and_tags(self, db_session):
        await marketplace_service.create_item(
            db_session,
            item_type="workflow",
            name="ETL Job",
            description="",
            category="Data / ETL",
            tags=["etl", "data"],
            author_id=1,
            content="{}",
            content_format="json",
        )
        await marketplace_service.create_item(
            db_session,
            item_type="workflow",
            name="Notify Team",
            description="",
            category="Notifications",
            tags=["slack", "data"],
            author_id=1,
            content="{}",
            content_format="json",
        )

        result = await marketplace_service.get_categories_and_tags(db_session)
        assert "Data / ETL" in [c["name"] for c in result["categories"]]
        assert "Notifications" in [c["name"] for c in result["categories"]]
        tag_names = [t["name"] for t in result["tagCloud"]]
        assert "data" in tag_names
        assert result["allCategories"] == [
            "Data / ETL", "Notifications", "Approvals & Tasks", "Reporting",
            "Integrations", "Schedules & Maintenance", "Onboarding", "General",
        ]


# ── Phase 2: Install / Preview / Audit ────────────────────────────────

class TestInstallWorkflowItem:
    @pytest.mark.asyncio
    async def test_install_workflow_item_success(self, db_session):
        """Installing a workflow item calls import service and bumps downloads."""
        wf_content = json.dumps({
            "workflow": {"name": "Imported Workflow", "isPublished": False, "environment": "test"},
            "steps": [
                {
                    "refId": "step-1",
                    "type": "delay",
                    "position": 0,
                    "title": "Wait",
                    "definition": {"seconds": 5},
                }
            ],
            "schedules": [],
            "forms": [],
            "groups": [],
        })

        item = await marketplace_service.create_item(
            db_session,
            item_type="workflow",
            name="Imported Workflow",
            description="Test workflow for install",
            category="General",
            tags=["test"],
            author_id=1,
            content=wf_content,
            content_format="json",
        )

        assert item.downloads_count == 0

        result = await marketplace_service.install_workflow_item(
            db_session,
            item_id=item.id,
            user_id=1,
            options={"on_conflict": "copy"},
        )

        assert result is not None
        assert hasattr(result, "to_dict")
        assert len(result.workflows_created) == 1
        assert result.workflows_created[0].startswith("Imported Workflow")

        refreshed = await marketplace_service.get_item(db_session, item.id)
        assert refreshed.downloads_count == 1

    @pytest.mark.asyncio
    async def test_install_workflow_item_not_found(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            await marketplace_service.install_workflow_item(
                db_session, item_id=9999, user_id=1, options={}
            )

    @pytest.mark.asyncio
    async def test_install_workflow_item_wrong_type(self, db_session):
        node_content = json.dumps({
            "step_type": "api_call",
            "definition": {"method": "GET", "url": "https://example.com"},
        })
        item = await marketplace_service.create_item(
            db_session,
            item_type="node",
            name="A Node",
            description="",
            category="General",
            tags=[],
            author_id=1,
            content=node_content,
            content_format="json",
            node_type="api_call",
        )

        with pytest.raises(ValueError, match="is not a workflow"):
            await marketplace_service.install_workflow_item(
                db_session, item_id=item.id, user_id=1, options={}
            )

    @pytest.mark.asyncio
    async def test_install_workflow_item_not_published(self, db_session):
        item = await marketplace_service.create_item(
            db_session,
            item_type="workflow",
            name="Draft Workflow",
            description="",
            category="General",
            tags=[],
            author_id=1,
            content=json.dumps({"workflow": {"name": "Draft"}, "steps": []}),
            content_format="json",
            status="draft",
        )

        with pytest.raises(ValueError, match="is not published"):
            await marketplace_service.install_workflow_item(
                db_session, item_id=item.id, user_id=1, options={}
            )


class TestInstallNodeItem:
    @pytest.mark.asyncio
    async def test_install_node_item_success(self, db_session):
        """Installing a node returns step payload and saves to My Nodes."""
        node_content = json.dumps({
            "step_type": "api_call",
            "title": "Fetch Users",
            "description": "GET /users endpoint",
            "definition": {"method": "GET", "url": "https://api.example.com/users"},
            "is_enabled": True,
            "max_retries": 2,
            "retry_delay_seconds": 10,
        })

        item = await marketplace_service.create_item(
            db_session,
            item_type="node",
            name="Fetch Users Node",
            description="GET /users endpoint",
            category="Integrations",
            tags=["api"],
            author_id=1,
            content=node_content,
            content_format="json",
            node_type="api_call",
        )

        assert item.downloads_count == 0

        result = await marketplace_service.install_node_item(
            db_session, item_id=item.id, user_id=1
        )

        assert "step_payload" in result
        assert "saved_node" in result
        assert result["step_payload"]["step_type"] == "api_call"
        assert result["step_payload"]["title"] == "Fetch Users"
        assert result["saved_node"]["id"] is not None
        assert result["saved_node"]["step_type"] == "api_call"
        assert result["saved_node"]["title"] == "Fetch Users"
        assert result["saved_node"]["max_retries"] == 2

        refreshed = await marketplace_service.get_item(db_session, item.id)
        assert refreshed.downloads_count == 1

        saved_nodes = await marketplace_service.list_saved_nodes(db_session, user_id=1)
        assert len(saved_nodes) == 1
        assert saved_nodes[0].source_marketplace_item_id == item.id

    @pytest.mark.asyncio
    async def test_install_node_item_not_found(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            await marketplace_service.install_node_item(
                db_session, item_id=9999, user_id=1
            )

    @pytest.mark.asyncio
    async def test_install_node_item_wrong_type(self, db_session):
        item = await marketplace_service.create_item(
            db_session,
            item_type="workflow",
            name="A Workflow",
            description="",
            category="General",
            tags=[],
            author_id=1,
            content=json.dumps({"workflow": {"name": "A"}, "steps": []}),
            content_format="json",
        )

        with pytest.raises(ValueError, match="is not a node"):
            await marketplace_service.install_node_item(
                db_session, item_id=item.id, user_id=1
            )


class TestPreviewAudit:
    @pytest.mark.asyncio
    async def test_preview_workflow_json(self, db_session):
        wf_content = json.dumps({
            "workflow": {"name": "Audit Me", "isPublished": False, "environment": "test"},
            "steps": [
                {
                    "refId": "step-1",
                    "type": "api_call",
                    "position": 0,
                    "title": "Call API",
                    "definition": {"method": "GET", "url": "https://api.example.com/data"},
                },
                {
                    "refId": "step-2",
                    "type": "custom_code",
                    "position": 1,
                    "title": "Process",
                    "definition": {"code": "return data['items']"},
                },
                {
                    "refId": "step-3",
                    "type": "database_query",
                    "position": 2,
                    "title": "Save",
                    "definition": {"type": "select", "table": "users", "query": "SELECT * FROM users"},
                },
                {
                    "refId": "step-4",
                    "type": "email",
                    "position": 3,
                    "title": "Notify",
                    "definition": {"to": "admin@example.com;ops@example.com", "subject": "Done"},
                },
            ],
            "schedules": [{"cronExpression": "0 0 * * *"}],
            "forms": [],
            "groups": [],
        })

        item = await marketplace_service.create_item(
            db_session,
            item_type="workflow",
            name="Audit Me",
            description="",
            category="General",
            tags=[],
            author_id=1,
            content=wf_content,
            content_format="json",
        )

        audit = await marketplace_service.preview_item(db_session, item.id)

        assert audit["item_type"] == "workflow"
        assert "api_call" in audit["step_types"]
        assert "custom_code" in audit["step_types"]
        assert "database_query" in audit["step_types"]
        assert "email" in audit["step_types"]
        assert audit["has_custom_code"] is True
        assert audit["has_database_query"] is True
        assert "https://api.example.com/data" in audit["external_urls"]
        assert "admin@example.com" in audit["email_recipients"]
        assert "ops@example.com" in audit["email_recipients"]
        assert audit["steps_count"] == 4
        assert audit["schedules_count"] == 1
        assert any("Custom code present" in w for w in audit["warnings"])
        assert any("Database query present" in w for w in audit["warnings"])

    @pytest.mark.asyncio
    async def test_preview_workflow_xml(self, db_session):
        wf_content = """<?xml version="1.0"?>
        <WorkflowPackage version="1.0">
            <Workflow name="XML Audit" isPublished="false" environment="test">
                <Steps>
                    <Step id="step-1" type="webhook" position="0">
                        <Title>Webhook Step</Title>
                        <Definition>{"url": "https://hooks.example.com/notify"}</Definition>
                    </Step>
                    <Step id="step-2" type="custom_code" position="1">
                        <Title>Code Step</Title>
                        <Definition>{"code": "x = 1 + 2"}</Definition>
                    </Step>
                </Steps>
            </Workflow>
        </WorkflowPackage>"""

        item = await marketplace_service.create_item(
            db_session,
            item_type="workflow",
            name="XML Audit",
            description="",
            category="General",
            tags=[],
            author_id=1,
            content=wf_content,
            content_format="xml",
        )

        audit = await marketplace_service.preview_item(db_session, item.id)

        assert audit["item_type"] == "workflow"
        assert "webhook" in audit["step_types"]
        assert "custom_code" in audit["step_types"]
        assert audit["has_custom_code"] is True
        assert "https://hooks.example.com/notify" in audit["external_urls"]
        assert audit["workflow_name"] == "XML Audit"
        assert audit["steps_count"] == 2

    @pytest.mark.asyncio
    async def test_preview_node(self, db_session):
        node_content = json.dumps({
            "step_type": "api_call",
            "title": "Preview Node",
            "description": "A node for preview testing",
            "definition": {
                "method": "POST",
                "url": "https://api.test.com/submit",
                "headers": {"Authorization": "Bearer test"},
            },
            "failure_hook_url": "https://hooks.test.com/fail",
        })

        item = await marketplace_service.create_item(
            db_session,
            item_type="node",
            name="Preview Node",
            description="",
            category="General",
            tags=[],
            author_id=1,
            content=node_content,
            content_format="json",
            node_type="api_call",
        )

        audit = await marketplace_service.preview_item(db_session, item.id)

        assert audit["item_type"] == "node"
        assert audit["step_types"] == ["api_call"]
        assert "https://api.test.com/submit" in audit["external_urls"]
        assert "https://hooks.test.com/fail" in audit["external_urls"]
        assert audit["node_title"] == "Preview Node"

    @pytest.mark.asyncio
    async def test_preview_not_found(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            await marketplace_service.preview_item(db_session, 9999)

    @pytest.mark.asyncio
    async def test_preview_not_published(self, db_session):
        item = await marketplace_service.create_item(
            db_session,
            item_type="workflow",
            name="Draft Preview",
            description="",
            category="General",
            tags=[],
            author_id=1,
            content=json.dumps({"workflow": {"name": "Draft"}, "steps": []}),
            content_format="json",
            status="draft",
        )

        with pytest.raises(ValueError, match="is not published"):
            await marketplace_service.preview_item(db_session, item.id)


class TestDownloadsCounter:
    @pytest.mark.asyncio
    async def test_downloads_increment_on_each_workflow_install(self, db_session):
        wf_content = json.dumps({
            "workflow": {"name": "Multi Install WF", "isPublished": False, "environment": "test"},
            "steps": [{"refId": "s1", "type": "delay", "position": 0, "definition": {"seconds": 1}}],
        })

        item = await marketplace_service.create_item(
            db_session,
            item_type="workflow",
            name="Multi Install WF",
            description="",
            category="General",
            tags=[],
            author_id=1,
            content=wf_content,
            content_format="json",
        )

        for i in range(3):
            await marketplace_service.install_workflow_item(
                db_session, item_id=item.id, user_id=1, options={"on_conflict": "copy"}
            )
            refreshed = await marketplace_service.get_item(db_session, item.id)
            assert refreshed.downloads_count == i + 1

    @pytest.mark.asyncio
    async def test_downloads_increment_on_each_node_install(self, db_session):
        node_content = json.dumps({
            "step_type": "delay",
            "title": "Multi Install Node",
            "definition": {"seconds": 5},
        })

        item = await marketplace_service.create_item(
            db_session,
            item_type="node",
            name="Multi Install Node",
            description="",
            category="General",
            tags=[],
            author_id=1,
            content=node_content,
            content_format="json",
            node_type="delay",
        )

        for i in range(3):
            await marketplace_service.install_node_item(
                db_session, item_id=item.id, user_id=1
            )
            refreshed = await marketplace_service.get_item(db_session, item.id)
            assert refreshed.downloads_count == i + 1
