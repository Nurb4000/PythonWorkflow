"""
Marketplace API — browse, publish, and manage workflow packages and node templates.
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select as sa_select
from typing import List, Optional

from app.core.database import get_db
from app.models.auth import User
from app.models.marketplace import MarketplaceItem
from app.api.auth import get_current_user, get_current_developer, get_current_admin
from app.services.marketplace_service import marketplace_service

router = APIRouter()


class MarketplaceItemCreate(BaseModel):
    item_type: str = Field(..., description="'workflow' or 'node'")
    name: str = Field(..., min_length=1)
    description: str = ""
    category: str = "General"
    tags: List[str] = []
    content: str = ""
    content_format: str = "json"
    node_type: Optional[str] = None
    status: str = "published"


def _item_to_dict(item) -> dict:
    return {
        "id": item.id,
        "item_type": item.item_type,
        "name": item.name,
        "description": item.description,
        "category": item.category,
        "tags": item.tags_list,
        "author_id": item.author_id,
        "version": item.version,
        "content_format": item.content_format,
        "node_type": item.node_type,
        "status": item.status,
        "is_active": item.is_active,
        "downloads_count": item.downloads_count,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _saved_node_to_dict(node) -> dict:
    return {
        "id": node.id,
        "user_id": node.user_id,
        "step_type": node.step_type,
        "title": node.title,
        "description": node.description,
        "definition": node.definition_dict,
        "condition_expr": node.condition_expr,
        "is_enabled": node.is_enabled,
        "max_retries": node.max_retries,
        "retry_delay_seconds": node.retry_delay_seconds,
        "failure_hook_url": node.failure_hook_url,
        "source_marketplace_item_id": node.source_marketplace_item_id,
        "created_at": node.created_at.isoformat() if node.created_at else None,
    }


# ── List / Browse ─────────────────────────────────────────────────────

@router.get("/items")
async def list_items(
    item_type: Optional[str] = Query(None, description="'workflow' or 'node'"),
    search: Optional[str] = Query(None, description="Search name/description"),
    category: Optional[str] = Query(None, description="Filter by category"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    status: Optional[str] = Query(None, description="Filter by status"),
    sort_by: str = Query("updated_at", description="Sort field: name, updated_at, created_at, downloads"),
    sort_order: str = Query("desc", description="asc or desc"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await marketplace_service.list_items(
        db,
        item_type=item_type,
        search=search,
        category=category,
        tag=tag,
        status=status,
        sort_by=sort_by,
        sort_order=sort_order,
        offset=offset,
        limit=limit,
    )
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/items/{item_id}")
async def get_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await marketplace_service.get_item(db, item_id)
    if not item or item.status != "published":
        raise HTTPException(status_code=404, detail="Item not found")
    result = _item_to_dict(item)
    result["author_name"] = item.author.username if item.author else None
    return result


@router.get("/items/{item_id}/package")
async def get_package(
    item_id: int,
    developer: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    item = await marketplace_service.get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return {
        "content": item.content,
        "content_format": item.content_format,
        "filename": f"{item.name.lower().replace(' ', '-')}.{item.content_format}",
    }


# ── CRUD (Admin/Developer) ────────────────────────────────────────────

@router.post("/items")
async def create_item(
    body: MarketplaceItemCreate,
    developer: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await marketplace_service.create_item(
            db,
            item_type=body.item_type,
            name=body.name,
            description=body.description,
            category=body.category,
            tags=body.tags or [],
            author_id=developer.id,
            content=body.content,
            content_format=body.content_format,
            node_type=body.node_type,
            status=body.status,
        )
        return _item_to_dict(item)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/items/{item_id}")
async def update_item(
    item_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[List[str]] = None,
    content: Optional[str] = None,
    content_format: Optional[str] = None,
    node_type: Optional[str] = None,
    status: Optional[str] = None,
    version: Optional[int] = None,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await marketplace_service.update_item(
            db,
            item_id=item_id,
            author_id=current_user.id,
            is_admin=current_user.role == "admin",
            name=name,
            description=description,
            category=category,
            tags=tags,
            content=content,
            content_format=content_format,
            node_type=node_type,
            status=status,
            version=version,
        )
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        return _item_to_dict(item)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/items/{item_id}")
async def delete_item(
    item_id: int,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await marketplace_service.delete_item(
            db,
            item_id=item_id,
            author_id=current_user.id,
            is_admin=current_user.role == "admin",
            archive_only=True,
        )
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        return {"message": "Item archived", "item_id": item_id}
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ── My Nodes (personal library) ───────────────────────────────────────

@router.get("/my-nodes")
async def list_my_nodes(
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    nodes = await marketplace_service.list_saved_nodes(db, current_user.id)
    return [_saved_node_to_dict(n) for n in nodes]


@router.post("/my-nodes")
async def save_node(
    step_type: str,
    title: str,
    description: str = "",
    definition: Optional[dict] = None,
    condition_expr: str = "",
    is_enabled: bool = True,
    max_retries: int = 0,
    retry_delay_seconds: int = 0,
    failure_hook_url: str = "",
    source_marketplace_item_id: Optional[int] = None,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    try:
        node = await marketplace_service.create_saved_node(
            db,
            user_id=current_user.id,
            step_type=step_type,
            title=title,
            description=description,
            definition=definition or {},
            condition_expr=condition_expr,
            is_enabled=is_enabled,
            max_retries=max_retries,
            retry_delay_seconds=retry_delay_seconds,
            failure_hook_url=failure_hook_url,
            source_marketplace_item_id=source_marketplace_item_id,
        )
        return _saved_node_to_dict(node)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/my-nodes/{node_id}")
async def delete_my_node(
    node_id: int,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    try:
        await marketplace_service.delete_saved_node(db, node_id, current_user.id)
        return {"message": "Node template deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Install ───────────────────────────────────────────────────────────

@router.post("/items/{item_id}/install")
async def install_item(
    item_id: int,
    on_conflict: str = Query("copy", description="'copy', 'skip', or 'overwrite'"),
    environment: Optional[str] = Query(None, description="Target environment: test, production, or preserve"),
    create_forms: bool = Query(True, description="Create missing forms during import"),
    create_groups: bool = Query(True, description="Create missing groups during import"),
    match_users_by_email: bool = Query(True, description="Resolve user refs by email"),
    workflow_name: Optional[str] = Query(None, description="Custom name for the imported workflow"),
    developer: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    item = await marketplace_service.get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    options = {
        "on_conflict": on_conflict,
        "create_forms": create_forms,
        "create_groups": create_groups,
        "match_users_by_email": match_users_by_email,
    }
    if environment:
        options["environment"] = environment
    if workflow_name:
        options["workflow_name"] = workflow_name

    try:
        if item.item_type == "workflow":
            result = await marketplace_service.install_workflow_item(
                db, item_id, developer.id, options
            )
            return {
                "installed": True,
                "item_id": item_id,
                "item_type": "workflow",
                "import_result": result.to_dict(),
            }
        elif item.item_type == "node":
            result = await marketplace_service.install_node_item(
                db, item_id, developer.id
            )
            return {
                "installed": True,
                "item_id": item_id,
                "item_type": "node",
                "step_payload": result["step_payload"],
                "saved_node": result["saved_node"],
            }
        elif item.item_type == "kb_article":
            result = await marketplace_service.install_kb_article_item(
                db, item_id, developer.id, options
            )
            return {
                "installed": True,
                "item_id": item_id,
                "item_type": "kb_article",
                **result,
            }
        else:
            raise HTTPException(status_code=400, detail=f"Cannot install item type: {item.item_type}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Preview / Audit ───────────────────────────────────────────────────

@router.post("/items/{item_id}/preview")
async def preview_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        audit = await marketplace_service.preview_item(db, item_id)
        return audit
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/items/{item_id}/graph")
async def get_workflow_graph(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get graph-ready data for visual workflow preview."""
    try:
        graph = await marketplace_service.get_workflow_graph(db, item_id)
        return graph
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Categories ────────────────────────────────────────────────────────

@router.get("/categories")
async def get_categories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await marketplace_service.get_categories_and_tags(db)


@router.put("/categories")
async def update_categories(
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update marketplace categories (admin only). Expects { categories: [...] }."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    cats = body.get("categories", [])
    if not isinstance(cats, list) or not all(isinstance(c, str) and c for c in cats):
        raise HTTPException(status_code=400, detail="categories must be a non-empty list of strings")

    await marketplace_service.set_categories(db, cats)
    return {"message": "Categories updated", "categories": cats}


# ── FG7: Export / Restore (backup) ─────────────────────────────────────

@router.get("/export")
async def export_marketplace(
    item_type: Optional[str] = None,
    category: Optional[str] = None,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Export marketplace items as JSON for backup/restore."""
    stmt = sa_select(MarketplaceItem).where(MarketplaceItem.is_active == True)
    if item_type:
        stmt = stmt.where(MarketplaceItem.item_type == item_type)
    if category:
        stmt = stmt.where(MarketplaceItem.category == category)

    result = await db.execute(stmt)
    items = result.scalars().all()

    export_data = {
        "version": "1.0",
        "exported_by": current_user.username,
        "item_count": len(items),
        "items": [],
    }

    for item in items:
        export_data["items"].append({
            "item_type": item.item_type,
            "name": item.name,
            "description": item.description or "",
            "category": item.category or "General",
            "tags": item.tags_list or [],
            "content": item.content or "",
            "content_format": item.content_format or "json",
            "node_type": item.node_type,
            "status": item.status or "published",
        })

    return JSONResponse(content=export_data)


class MarketplaceRestoreItem(BaseModel):
    item_type: str
    name: str
    description: str = ""
    category: str = "General"
    tags: List[str] = []
    content: str
    content_format: str = "json"
    node_type: Optional[str] = None
    status: str = "published"


class MarketplaceRestoreRequest(BaseModel):
    items: List[MarketplaceRestoreItem]


@router.post("/restore")
async def restore_marketplace(
    body: MarketplaceRestoreRequest,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Restore marketplace items from a previously exported JSON payload."""
    created = 0
    skipped = 0
    errors: List[str] = []

    for item_data in body.items:
        try:
            # Check for duplicate (same name + type)
            check_stmt = sa_select(MarketplaceItem).where(
                MarketplaceItem.name == item_data.name,
                MarketplaceItem.item_type == item_data.item_type,
                MarketplaceItem.is_active == True,
            )
            check_result = await db.execute(check_stmt)
            if check_result.scalar_one_or_none():
                skipped += 1
                continue

            await marketplace_service.create_item(
                db=db,
                item_type=item_data.item_type,
                name=item_data.name,
                description=item_data.description,
                category=item_data.category,
                tags=item_data.tags,
                author_id=current_user.id,
                content=item_data.content,
                content_format=item_data.content_format,
                node_type=item_data.node_type,
                status=item_data.status,
            )
            created += 1
        except ValueError as e:
            errors.append(f"{item_data.name}: {str(e)}")

    return {
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "total_processed": len(body.items),
    }
