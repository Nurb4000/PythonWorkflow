"""
Marketplace service — CRUD, search, validation for marketplace items and saved nodes.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketplace import MarketplaceItem, SavedNodeTemplate
from app.models.auth import User
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)

CATEGORIES = [
    "Data / ETL",
    "Notifications",
    "Approvals & Tasks",
    "Reporting",
    "Integrations",
    "Schedules & Maintenance",
    "Onboarding",
    "General",
]

SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9]{20,}",
    r"Bearer\s+[A-Za-z0-9\-._~+/]+=*",
    r"api_key\s*=\s*['\"][^'\"]{8,}",
    r"password\s*=\s*['\"][^'\"]+",
    r"secret\s*=\s*['\"][^'\"]+",
]


class MarketplaceService:
    """Service for marketplace item CRUD, search, and validation."""

    def __init__(self):
        self.ai = AIService()

    # ── MarketplaceItem CRUD ──────────────────────────────────────────

    async def create_item(
        self,
        db: AsyncSession,
        item_type: str,
        name: str,
        description: str,
        category: str,
        tags: List[str],
        author_id: int,
        content: str,
        content_format: str,
        node_type: Optional[str] = None,
        status: str = "published",
    ) -> MarketplaceItem:
        if item_type not in ("workflow", "node"):
            raise ValueError("item_type must be 'workflow' or 'node'")

        if content_format not in ("xml", "json"):
            raise ValueError("content_format must be 'xml' or 'json'")

        if category and category not in CATEGORIES:
            raise ValueError(f"category must be one of {CATEGORIES}")

        if item_type == "node":
            self._validate_node_content(content)
        else:
            self._validate_workflow_content(content, content_format)

        warnings = self._scan_secrets(content, item_type)
        if item_type == "workflow" and warnings:
            raise ValueError(
                f"Workflow contains potential secrets. Remove them before publishing: {'; '.join(warnings)}"
            )

        item = MarketplaceItem(
            item_type=item_type,
            name=name,
            description=description or "",
            category=category or "General",
            author_id=author_id,
            content=content,
            content_format=content_format,
            node_type=node_type,
            status=status or "published",
        )
        item.tags_list = tags or []

        db.add(item)
        await db.commit()
        await db.refresh(item)
        logger.info(f"Created marketplace item {item.id} ({name})")
        return item

    async def get_item(self, db: AsyncSession, item_id: int) -> Optional[MarketplaceItem]:
        stmt = select(MarketplaceItem).where(MarketplaceItem.id == item_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_items(
        self,
        db: AsyncSession,
        item_type: Optional[str] = None,
        search: Optional[str] = None,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        status: Optional[str] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
        offset: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int]:
        base_query = select(
            MarketplaceItem.id,
            MarketplaceItem.item_type,
            MarketplaceItem.name,
            MarketplaceItem.description,
            MarketplaceItem.category,
            MarketplaceItem.tags,
            MarketplaceItem.author_id,
            MarketplaceItem.version,
            MarketplaceItem.content_format,
            MarketplaceItem.node_type,
            MarketplaceItem.status,
            MarketplaceItem.is_active,
            MarketplaceItem.downloads_count,
            MarketplaceItem.created_at,
            MarketplaceItem.updated_at,
            User.username.label("author_name"),
        ).outerjoin(User, User.id == MarketplaceItem.author_id)

        stmt = base_query

        if item_type:
            stmt = stmt.where(MarketplaceItem.item_type == item_type)

        if status:
            stmt = stmt.where(MarketplaceItem.status == status)
        else:
            stmt = stmt.where(MarketplaceItem.status == "published")

        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    MarketplaceItem.name.ilike(pattern),
                    MarketplaceItem.description.ilike(pattern),
                )
            )

        if category:
            stmt = stmt.where(MarketplaceItem.category == category)

        if tag:
            stmt = stmt.where(MarketplaceItem.tags.like(f"%\"{tag}\"%"))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await db.execute(count_stmt)
        total = total_result.scalar() or 0

        valid_sort = {
            "name": MarketplaceItem.name,
            "updated_at": MarketplaceItem.updated_at,
            "created_at": MarketplaceItem.created_at,
            "downloads": MarketplaceItem.downloads_count,
        }
        sort_col = valid_sort.get(sort_by, MarketplaceItem.updated_at)
        stmt = stmt.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())
        stmt = stmt.offset(offset).limit(limit)

        result = await db.execute(stmt)
        rows = result.mappings().all()

        items = []
        for r in rows:
            d = dict(r)
            try:
                d["tags"] = json.loads(d.get("tags", "[]"))
            except (json.JSONDecodeError, TypeError):
                d["tags"] = []
            items.append(d)

        return items, total

    async def update_item(
        self,
        db: AsyncSession,
        item_id: int,
        author_id: int,
        is_admin: bool,
        **kwargs,
    ) -> Optional[MarketplaceItem]:
        item = await self.get_item(db, item_id)
        if not item:
            return None

        if not is_admin and item.author_id != author_id:
            raise ValueError("Only the author or an admin can update this item")

        allowed = {
            "name", "description", "category", "tags", "content",
            "content_format", "node_type", "status", "version",
        }
        for key, value in kwargs.items():
            if key in allowed and value is not None:
                setattr(item, key, value)

        if "tags" in kwargs and kwargs["tags"] is not None:
            item.tags_list = kwargs["tags"]

        if "content" in kwargs and item.item_type == "node":
            self._validate_node_content(kwargs["content"])

        await db.commit()
        await db.refresh(item)
        return item

    async def delete_item(
        self,
        db: AsyncSession,
        item_id: int,
        author_id: int,
        is_admin: bool,
        archive_only: bool = False,
    ) -> Optional[MarketplaceItem]:
        item = await self.get_item(db, item_id)
        if not item:
            return None

        if not is_admin and item.author_id != author_id:
            raise ValueError("Only the author or an admin can delete this item")

        if archive_only or (is_admin and not item.author_id == author_id):
            item.status = "archived"
            item.is_active = False
        else:
            await db.delete(item)

        await db.commit()
        return item

    # ── SavedNodeTemplate CRUD ────────────────────────────────────────

    async def create_saved_node(
        self,
        db: AsyncSession,
        user_id: int,
        step_type: str,
        title: str,
        description: str,
        definition: Dict[str, Any],
        condition_expr: str = "",
        is_enabled: bool = True,
        max_retries: int = 0,
        retry_delay_seconds: int = 0,
        failure_hook_url: str = "",
        source_marketplace_item_id: Optional[int] = None,
    ) -> SavedNodeTemplate:
        if step_type not in self.ai.VALID_STEP_TYPES:
            raise ValueError(f"Invalid step_type: {step_type}")

        node = SavedNodeTemplate(
            user_id=user_id,
            step_type=step_type,
            title=title,
            description=description or "",
            condition_expr=condition_expr or "",
            is_enabled=is_enabled,
            max_retries=max_retries,
            retry_delay_seconds=retry_delay_seconds,
            failure_hook_url=failure_hook_url or "",
            source_marketplace_item_id=source_marketplace_item_id,
        )
        node.definition_dict = definition

        db.add(node)
        await db.commit()
        await db.refresh(node)
        return node

    async def list_saved_nodes(
        self,
        db: AsyncSession,
        user_id: int,
    ) -> List[SavedNodeTemplate]:
        stmt = (
            select(SavedNodeTemplate)
            .where(SavedNodeTemplate.user_id == user_id)
            .order_by(SavedNodeTemplate.created_at.desc())
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_saved_node(
        self,
        db: AsyncSession,
        node_id: int,
        user_id: int,
    ) -> Optional[SavedNodeTemplate]:
        stmt = select(SavedNodeTemplate).where(
            SavedNodeTemplate.id == node_id,
            SavedNodeTemplate.user_id == user_id,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_saved_node(
        self,
        db: AsyncSession,
        node_id: int,
        user_id: int,
    ) -> bool:
        node = await self.get_saved_node(db, node_id, user_id)
        if not node:
            raise ValueError("Node template not found or access denied")
        await db.delete(node)
        await db.commit()
        return True

    # ── Validation helpers ────────────────────────────────────────────

    def _validate_node_content(self, content: str) -> Dict[str, Any]:
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            raise ValueError("Node content must be valid JSON")

        if "step_type" not in data:
            raise ValueError("Node content must include 'step_type'")

        step_type = data["step_type"]
        if step_type not in self.ai.VALID_STEP_TYPES:
            raise ValueError(f"Invalid step_type: {step_type}")

        required = self.ai.VALID_STEP_TYPES.get(step_type, [])
        definition = data.get("definition", {})
        for field in required:
            if field not in definition:
                raise ValueError(f"Missing required field '{field}' in definition for step_type '{step_type}'")

        return data

    def _validate_workflow_content(self, content: str, content_format: str) -> None:
        if content_format == "json":
            try:
                json.loads(content)
            except (json.JSONDecodeError, TypeError):
                raise ValueError("Workflow content must be valid JSON")
        elif content_format == "xml":
            if "<WorkflowPackage" not in content and "<workflow" not in content.lower():
                raise ValueError("XML content must contain a WorkflowPackage root element")

    def _scan_secrets(self, content: str, item_type: str) -> List[str]:
        warnings = []
        for pattern in SECRET_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                warnings.append(f"Pattern matched: {pattern}")
        return warnings

    # ── Categories / tags ─────────────────────────────────────────────

    async def get_categories_and_tags(self, db: AsyncSession) -> Dict[str, Any]:
        cat_stmt = select(MarketplaceItem.category, func.count(MarketplaceItem.id).label("count")).where(
            MarketplaceItem.status == "published"
        ).group_by(MarketplaceItem.category)
        cat_result = await db.execute(cat_stmt)
        categories = [{"name": r[0], "count": r[1]} for r in cat_result.all()]

        tag_counts: Dict[str, int] = {}
        all_stmt = select(MarketplaceItem.tags).where(MarketplaceItem.status == "published")
        all_result = await db.execute(all_stmt)
        for row in all_result.scalars().all():
            try:
                tags = json.loads(row) if row else []
                for t in tags:
                    tag_counts[t] = tag_counts.get(t, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass

        tag_cloud = [{"name": k, "count": v} for k, v in sorted(tag_counts.items(), key=lambda x: -x[1])]

        return {
            "categories": categories,
            "tagCloud": tag_cloud,
            "allCategories": CATEGORIES,
        }


marketplace_service = MarketplaceService()
