"""
Marketplace API — browse, publish, and manage workflow packages and node templates.
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.core.database import get_db
from app.models.auth import User
from app.api.auth import get_current_user, get_current_developer, get_current_admin
from app.services.marketplace_service import marketplace_service

router = APIRouter()


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
    item_type: str,
    name: str,
    description: str = "",
    category: str = "General",
    tags: Optional[List[str]] = None,
    content: str = "",
    content_format: str = "json",
    node_type: Optional[str] = None,
    status: str = "published",
    developer: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await marketplace_service.create_item(
            db,
            item_type=item_type,
            name=name,
            description=description,
            category=category,
            tags=tags or [],
            author_id=developer.id,
            content=content,
            content_format=content_format,
            node_type=node_type,
            status=status,
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
    archive: bool = Query(False, description="Archive instead of delete (admin cross-user)"),
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    try:
        item = await marketplace_service.delete_item(
            db,
            item_id=item_id,
            author_id=current_user.id,
            is_admin=current_user.role == "admin",
            archive_only=archive or current_user.role == "admin",
        )
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        return {"message": "Item deleted", "item_id": item_id}
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


# ── Categories ────────────────────────────────────────────────────────

@router.get("/categories")
async def get_categories(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await marketplace_service.get_categories_and_tags(db)
