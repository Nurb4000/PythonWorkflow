import logging
import re
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text as sa_text

from app.models.sql_views import SQLView

logger = logging.getLogger(__name__)

DANGEROUS_KEYWORDS = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE TABLE", "TRUNCATE", "EXEC", "EXECUTE"]


class SQLViewService:
    """Manage SQL views lifecycle."""

    def _validate_view_sql(self, sql: str) -> None:
        """Validate that the SQL is a safe CREATE VIEW statement."""
        stripped = sql.strip().upper()
        if not stripped.startswith("CREATE"):
            raise ValueError("SQL must start with CREATE")

        for keyword in DANGEROUS_KEYWORDS:
            pattern = r'\b' + keyword + r'\b'
            if re.search(pattern, sql, re.IGNORECASE):
                raise ValueError(f"View definition contains disallowed keyword: {keyword}")

    async def list_views(self, db: AsyncSession, include_inactive: bool = False) -> List[SQLView]:
        """List all SQL views."""
        stmt = select(SQLView).order_by(SQLView.name)
        if not include_inactive:
            stmt = stmt.where(SQLView.is_active == True)
        result = await db.execute(stmt)
        return result.scalars().all()

    async def get_view(self, db: AsyncSession, view_id: int) -> Optional[SQLView]:
        """Get a single SQL view by ID."""
        stmt = select(SQLView).where(SQLView.id == view_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_view(self, db: AsyncSession, name: str, definition_sql: str,
                          description: str = "", created_by: Optional[int] = None) -> SQLView:
        """Create a new SQL view."""
        self._validate_view_sql(definition_sql)

        existing = await self.get_view_by_name(db, name)
        if existing:
            raise ValueError(f"View '{name}' already exists")

        view = SQLView(
            name=name,
            definition_sql=definition_sql,
            description=description,
            created_by=created_by,
            is_active=True
        )
        db.add(view)

        await db.execute(sa_text(definition_sql))
        await db.commit()
        await db.refresh(view)

        logger.info(f"Created SQL view: {name}")
        return view

    async def update_view(self, db: AsyncSession, view_id: int, definition_sql: Optional[str] = None,
                          description: Optional[str] = None, is_active: Optional[bool] = None) -> SQLView:
        """Update an existing SQL view."""
        view = await self.get_view(db, view_id)
        if not view:
            raise ValueError(f"View {view_id} not found")

        if definition_sql:
            self._validate_view_sql(definition_sql)
            view.definition_sql = definition_sql
            await db.execute(sa_text("CREATE OR REPLACE " + definition_sql))

        if description is not None:
            view.description = description
        if is_active is not None:
            view.is_active = is_active

        await db.commit()
        await db.refresh(view)

        logger.info(f"Updated SQL view: {view.name}")
        return view

    async def delete_view(self, db: AsyncSession, view_id: int) -> bool:
        """Deactivate a SQL view (drops from database but keeps record)."""
        view = await self.get_view(db, view_id)
        if not view:
            return False

        await db.execute(sa_text(f"DROP VIEW IF EXISTS {view.name}"))
        view.is_active = False
        await db.commit()

        logger.info(f"Deactivated SQL view: {view.name}")
        return True

    async def get_view_by_name(self, db: AsyncSession, name: str) -> Optional[SQLView]:
        """Get a view by its database name."""
        stmt = select(SQLView).where(SQLView.name == name)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def sync_views(self, db: AsyncSession) -> None:
        """Sync all active views in the database (run on startup)."""
        stmt = select(SQLView).where(SQLView.is_active == True)
        result = await db.execute(stmt)
        views = result.scalars().all()

        for view in views:
            try:
                await db.execute(sa_text(view.definition_sql))
                logger.info(f"Synced view: {view.name}")
            except Exception as e:
                logger.warning(f"Failed to sync view {view.name}: {e}")

        await db.commit()


sql_view_service = SQLViewService()
