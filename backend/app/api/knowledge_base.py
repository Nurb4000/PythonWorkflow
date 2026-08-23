"""
API endpoints for knowledge base and templates
"""
import re
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, delete, insert
from sqlalchemy.orm import selectinload
from typing import List, Optional
from app.core.database import get_db
from app.services.template_service import template_service
from app.models.auth import User, Group, kb_article_permissions
from app.api.auth import get_current_user, get_current_admin

router = APIRouter()


@router.get("/knowledge-base")
async def get_knowledge_base():
    """Get available knowledge base content"""
    return {
        "templates": template_service.get_templates(),
        "template_count": len(template_service.get_templates())
    }


@router.get("/templates")
async def list_templates():
    """List all available templates"""
    templates = template_service.get_templates()
    return [
        {
            "name": t.get("name"),
            "description": t.get("description", ""),
            "steps_count": len(t.get("steps", []))
        }
        for t in templates
    ]


@router.get("/templates/{template_name}")
async def get_template(template_name: str):
    """Get a specific template"""
    template = template_service.get_template(template_name)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{template_name}' not found")
    return template


@router.post("/templates/{template_name}/create")
async def create_from_template(
    template_name: str,
    customizations: Optional[dict] = None,
    db: AsyncSession = Depends(get_db)
):
    """Create a workflow from a template"""
    try:
        workflow = await template_service.create_from_template(db, template_name, customizations)
        return {
            "id": workflow.id,
            "name": workflow.name,
            "message": f"Workflow created from template '{template_name}'"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create workflow: {str(e)}")


@router.post("/workflows/{workflow_id}/save-template")
async def save_as_template(
    workflow_id: int,
    template_name: str,
    db: AsyncSession = Depends(get_db)
):
    """Save a workflow as a template"""
    try:
        success = await template_service.save_template(db, workflow_id, template_name)
        if not success:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return {"message": f"Template '{template_name}' saved successfully"}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/step-templates")
async def list_step_templates():
    """P5.4: List all available step templates."""
    step_templates = template_service.get_step_templates()
    return [
        {
            "step_type": t["step_type"],
            "title": t["title"],
            "definition": t["definition"],
            "template_name": t["template_name"],
        }
        for t in step_templates
    ]


@router.get("/step-templates/{step_type}")
async def get_step_template(step_type: str):
    """P5.4: Get a specific step template by type."""
    template = template_service.get_step_template(step_type)
    if not template:
        raise HTTPException(status_code=404, detail=f"Step template '{step_type}' not found")
    return template


# ------------------------------------------------------------------
# Knowledge Base Articles (SERVICE_MANAGEMENT_PLAN Phase 6)
# ------------------------------------------------------------------

from app.models.services import KnowledgeBaseArticle, Service


def _slugify(text: str) -> str:
    slug = re.sub(r'[^\w\s-]', '', text.lower()).strip().replace(' ', '-').replace('_', '-')
    return slug or 'article'


def _kb_article_to_dict(article: KnowledgeBaseArticle) -> dict:
    result = {
        "id": article.id,
        "title": article.title,
        "slug": article.slug,
        "content": article.content or "",
        "service_id": article.service_id,
        "is_published": article.is_published,
        "is_featured": getattr(article, 'is_featured', False),
        "display_order": getattr(article, 'display_order', 0),
        "sort_order": article.sort_order or 0,
        "created_at": article.created_at,
        "updated_at": article.updated_at,
    }
    if article.service:
        result["service"] = {
            "id": article.service.id,
            "name": article.service.name,
            "key": article.service.key,
            "icon": article.service.icon or "",
        }
    if hasattr(article, 'allowed_groups') and article.allowed_groups:
        result["allowed_groups"] = [{"id": g.id, "name": g.name} for g in article.allowed_groups]
    else:
        result["allowed_groups"] = []
    return result


async def _load_article_with_groups(db: AsyncSession, article_id: int):
    """Load article with service and allowed groups."""
    stmt = select(KnowledgeBaseArticle).where(
        KnowledgeBaseArticle.id == article_id
    ).options(selectinload(KnowledgeBaseArticle.service))
    result = await db.execute(stmt)
    article = result.scalar_one_or_none()
    if not article:
        return None

    # Load allowed groups
    grp_stmt = select(Group).join(
        kb_article_permissions, kb_article_permissions.c.group_id == Group.id
    ).where(kb_article_permissions.c.article_id == article_id)
    grp_result = await db.execute(grp_stmt)
    article.allowed_groups = grp_result.scalars().all()
    return article


@router.get("/kb-articles")
async def list_kb_articles(
    service_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List published KB articles. Filter by service or search."""
    stmt = select(KnowledgeBaseArticle).where(KnowledgeBaseArticle.is_published == True)

    if service_id is not None:
        stmt = stmt.where(KnowledgeBaseArticle.service_id == service_id)

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                KnowledgeBaseArticle.title.ilike(pattern),
                KnowledgeBaseArticle.content.ilike(pattern),
                KnowledgeBaseArticle.slug.ilike(pattern),
            )
        )

    # Non-admin users only see articles visible to their groups
    if current_user.role != "admin":
        user_group_ids = {g.id for g in current_user.groups}
        # Articles with no group restrictions are visible to all
        # Articles with group restrictions are only visible if user's group matches
        if user_group_ids:
            restricted_stmt = select(kb_article_permissions.c.article_id).where(
                kb_article_permissions.c.group_id.in_(user_group_ids)
            )
            stmt = stmt.where(
                or_(
                    # No group restrictions (not in permissions table)
                    ~KnowledgeBaseArticle.id.in_(select(kb_article_permissions.c.article_id).distinct()),
                    # User's groups have access
                    KnowledgeBaseArticle.id.in_(restricted_stmt)
                )
            )
        else:
            # User with no groups only sees articles with no restrictions
            stmt = stmt.where(
                ~KnowledgeBaseArticle.id.in_(select(kb_article_permissions.c.article_id).distinct())
            )

    stmt = stmt.options(selectinload(KnowledgeBaseArticle.service))
    stmt = stmt.order_by(KnowledgeBaseArticle.sort_order.asc(), KnowledgeBaseArticle.title.asc())
    result = await db.execute(stmt)
    articles = result.scalars().all()

    return [_kb_article_to_dict(a) for a in articles]


@router.get("/kb-articles/featured")
async def list_featured_kb_articles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List featured (top) KB articles for the browse page."""
    stmt = select(KnowledgeBaseArticle).where(
        KnowledgeBaseArticle.is_published == True,
        KnowledgeBaseArticle.is_featured == True
    )

    # Non-admin users only see articles visible to their groups
    if current_user.role != "admin":
        user_group_ids = {g.id for g in current_user.groups}
        if user_group_ids:
            restricted_stmt = select(kb_article_permissions.c.article_id).where(
                kb_article_permissions.c.group_id.in_(user_group_ids)
            )
            stmt = stmt.where(
                or_(
                    ~KnowledgeBaseArticle.id.in_(select(kb_article_permissions.c.article_id).distinct()),
                    KnowledgeBaseArticle.id.in_(restricted_stmt)
                )
            )
        else:
            stmt = stmt.where(
                ~KnowledgeBaseArticle.id.in_(select(kb_article_permissions.c.article_id).distinct())
            )

    stmt = stmt.options(selectinload(KnowledgeBaseArticle.service))
    stmt = stmt.order_by(KnowledgeBaseArticle.display_order.asc(), KnowledgeBaseArticle.title.asc())
    result = await db.execute(stmt)
    articles = result.scalars().all()

    return [_kb_article_to_dict(a) for a in articles]


@router.get("/kb-articles/admin")
async def list_kb_articles_admin(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all KB articles including drafts (admin only)."""
    stmt = select(KnowledgeBaseArticle).options(selectinload(KnowledgeBaseArticle.service))
    stmt = stmt.order_by(KnowledgeBaseArticle.sort_order.asc(), KnowledgeBaseArticle.title.asc())
    result = await db.execute(stmt)
    articles = result.scalars().all()

    # Load allowed groups for each article
    for article in articles:
        grp_stmt = select(Group).join(
            kb_article_permissions, kb_article_permissions.c.group_id == Group.id
        ).where(kb_article_permissions.c.article_id == article.id)
        grp_result = await db.execute(grp_stmt)
        article.allowed_groups = grp_result.scalars().all()

    return [_kb_article_to_dict(a) for a in articles]


@router.get("/kb-articles/export")
async def export_kb_articles(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Export all KB articles as JSON (admin only)."""
    from fastapi.responses import JSONResponse

    stmt = select(KnowledgeBaseArticle).options(selectinload(KnowledgeBaseArticle.service))
    result = await db.execute(stmt)
    articles = result.scalars().all()

    exported = []
    for article in articles:
        # Load allowed groups
        grp_stmt = select(Group).join(
            kb_article_permissions, kb_article_permissions.c.group_id == Group.id
        ).where(kb_article_permissions.c.article_id == article.id)
        grp_result = await db.execute(grp_stmt)
        allowed_groups = grp_result.scalars().all()

        exported.append({
            "title": article.title,
            "slug": article.slug,
            "content": article.content or "",
            "service_id": article.service_id,
            "is_published": article.is_published,
            "is_featured": getattr(article, 'is_featured', False),
            "display_order": getattr(article, 'display_order', 0),
            "sort_order": article.sort_order or 0,
            "allowed_group_ids": [g.id for g in allowed_groups],
        })

    return JSONResponse(
        content=exported,
        headers={"Content-Disposition": "attachment; filename=kb_articles.json"}
    )


@router.post("/kb-articles/import")
async def import_kb_articles(
    articles: List[dict],
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Import KB articles from JSON (admin only)."""
    imported_count = 0

    for article_data in articles:
        title = article_data.get("title", "")
        slug = article_data.get("slug", _slugify(title))
        content = article_data.get("content", "")
        service_id = article_data.get("service_id")
        is_published = article_data.get("is_published", True)
        is_featured = article_data.get("is_featured", False)
        display_order = article_data.get("display_order", 0)
        sort_order = article_data.get("sort_order", 0)
        allowed_group_ids = article_data.get("allowed_group_ids", [])

        if not title:
            continue

        # Check for duplicate slug
        existing = await db.execute(
            select(KnowledgeBaseArticle).where(KnowledgeBaseArticle.slug == slug)
        )
        if existing.scalar_one_or_none():
            continue

        # Validate service if provided
        if service_id is not None:
            svc = await db.execute(select(Service).where(Service.id == service_id))
            if not svc.scalar_one_or_none():
                service_id = None

        article = KnowledgeBaseArticle(
            title=title,
            slug=slug,
            content=content,
            service_id=service_id,
            is_published=is_published,
            is_featured=is_featured,
            display_order=display_order,
            sort_order=sort_order,
        )
        db.add(article)
        await db.flush()

        # Set group permissions
        if allowed_group_ids:
            grp_stmt = select(Group).where(Group.id.in_(allowed_group_ids))
            grp_result = await db.execute(grp_stmt)
            groups = grp_result.scalars().all()
            await db.execute(
                insert(kb_article_permissions),
                [{"article_id": article.id, "group_id": g.id} for g in groups]
            )

        imported_count += 1

    await db.commit()
    return {"message": f"Imported {imported_count} of {len(articles)} articles"}


@router.get("/kb-articles/{article_id}")
async def get_kb_article(
    article_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a single KB article by ID."""
    stmt = select(KnowledgeBaseArticle).where(
        KnowledgeBaseArticle.id == article_id
    ).options(selectinload(KnowledgeBaseArticle.service))
    result = await db.execute(stmt)
    article = result.scalar_one_or_none()

    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    # Non-admins only see published articles
    if not article.is_published and current_user.role != "admin":
        raise HTTPException(status_code=404, detail="Article not found")

    return _kb_article_to_dict(article)


@router.get("/kb-articles/slug/{slug}")
async def get_kb_article_by_slug(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a single KB article by slug."""
    stmt = select(KnowledgeBaseArticle).where(
        KnowledgeBaseArticle.slug == slug
    ).options(selectinload(KnowledgeBaseArticle.service))
    result = await db.execute(stmt)
    article = result.scalar_one_or_none()

    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    if not article.is_published and current_user.role != "admin":
        raise HTTPException(status_code=404, detail="Article not found")

    return _kb_article_to_dict(article)


@router.post("/kb-articles")
async def create_kb_article(
    title: str,
    content: str = "",
    service_id: Optional[int] = None,
    slug: Optional[str] = None,
    sort_order: int = 0,
    is_featured: bool = False,
    display_order: int = 0,
    allowed_group_ids: Optional[List[int]] = Query(None),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new KB article (admin only)."""
    article_slug = slug or _slugify(title)

    # Check for duplicate slug
    existing = await db.execute(
        select(KnowledgeBaseArticle).where(KnowledgeBaseArticle.slug == article_slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Article with this slug already exists")

    # Validate service if provided
    if service_id is not None:
        svc = await db.execute(select(Service).where(Service.id == service_id))
        if not svc.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Service not found")

    article = KnowledgeBaseArticle(
        title=title,
        slug=article_slug,
        content=content or "",
        service_id=service_id,
        sort_order=sort_order,
        is_featured=is_featured,
        display_order=display_order,
    )
    db.add(article)
    await db.flush()

    # Set group permissions (empty list = visible to all)
    if allowed_group_ids is not None:
        await db.execute(delete(kb_article_permissions).where(kb_article_permissions.c.article_id == article.id))
        if allowed_group_ids:
            grp_stmt = select(Group).where(Group.id.in_(allowed_group_ids))
            grp_result = await db.execute(grp_stmt)
            groups = grp_result.scalars().all()
            if len(groups) != len(set(allowed_group_ids)):
                raise HTTPException(status_code=400, detail="One or more groups not found")
            await db.execute(
                insert(kb_article_permissions),
                [{"article_id": article.id, "group_id": g.id} for g in groups]
            )

    await db.commit()
    await db.refresh(article)

    result_article = await _load_article_with_groups(db, article.id)
    return _kb_article_to_dict(result_article)


@router.put("/kb-articles/{article_id}")
async def update_kb_article(
    article_id: int,
    data: dict,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a KB article (admin only)."""
    stmt = select(KnowledgeBaseArticle).where(
        KnowledgeBaseArticle.id == article_id
    ).options(selectinload(KnowledgeBaseArticle.service))
    result = await db.execute(stmt)
    article = result.scalar_one_or_none()

    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    if "title" in data:
        article.title = data["title"]
    if "content" in data:
        article.content = data["content"]
    if "slug" in data and data["slug"] != article.slug:
        existing = await db.execute(
            select(KnowledgeBaseArticle).where(KnowledgeBaseArticle.slug == data["slug"], KnowledgeBaseArticle.id != article_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Article with this slug already exists")
        article.slug = data["slug"]
    if "service_id" in data:
        if data["service_id"] is not None:
            svc = await db.execute(select(Service).where(Service.id == data["service_id"]))
            if not svc.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Service not found")
        article.service_id = data["service_id"]
    if "is_published" in data:
        article.is_published = data["is_published"]
    if "is_featured" in data:
        article.is_featured = data["is_featured"]
    if "display_order" in data:
        article.display_order = data["display_order"]
    if "sort_order" in data:
        article.sort_order = data["sort_order"]

    # Handle group permissions update
    if "allowed_group_ids" in data:
        group_ids = data["allowed_group_ids"]
        await db.execute(delete(kb_article_permissions).where(kb_article_permissions.c.article_id == article.id))
        if group_ids:
            grp_stmt = select(Group).where(Group.id.in_(group_ids))
            grp_result = await db.execute(grp_stmt)
            groups = grp_result.scalars().all()
            if len(groups) != len(set(group_ids)):
                raise HTTPException(status_code=400, detail="One or more groups not found")
            await db.execute(
                insert(kb_article_permissions),
                [{"article_id": article.id, "group_id": g.id} for g in groups]
            )

    await db.commit()
    await db.refresh(article)

    result_article = await _load_article_with_groups(db, article.id)
    return _kb_article_to_dict(result_article)


@router.delete("/kb-articles/{article_id}")
async def delete_kb_article(
    article_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Unpublish a KB article (soft-delete)."""
    stmt = select(KnowledgeBaseArticle).where(KnowledgeBaseArticle.id == article_id)
    result = await db.execute(stmt)
    article = result.scalar_one_or_none()

    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    article.is_published = False
    await db.commit()
    return {"message": "Article unpublished"}
