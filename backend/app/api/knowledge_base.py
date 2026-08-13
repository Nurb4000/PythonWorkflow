"""
API endpoints for knowledge base and templates
"""
import re
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from typing import List, Optional
from app.core.database import get_db
from app.services.template_service import template_service
from app.models.auth import User
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
    return result


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

    stmt = stmt.options(selectinload(KnowledgeBaseArticle.service))
    stmt = stmt.order_by(KnowledgeBaseArticle.sort_order.asc(), KnowledgeBaseArticle.title.asc())
    result = await db.execute(stmt)
    articles = result.scalars().all()

    return [_kb_article_to_dict(a) for a in articles]


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
    )
    db.add(article)
    await db.commit()
    await db.refresh(article)

    # Reload with service relationship
    stmt = select(KnowledgeBaseArticle).where(
        KnowledgeBaseArticle.id == article.id
    ).options(selectinload(KnowledgeBaseArticle.service))
    result = await db.execute(stmt)
    return _kb_article_to_dict(result.scalar_one())


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
    if "sort_order" in data:
        article.sort_order = data["sort_order"]

    await db.commit()
    await db.refresh(article)

    stmt = select(KnowledgeBaseArticle).where(
        KnowledgeBaseArticle.id == article.id
    ).options(selectinload(KnowledgeBaseArticle.service))
    result = await db.execute(stmt)
    return _kb_article_to_dict(result.scalar_one())


@router.delete("/kb-articles/{article_id}")
async def delete_kb_article(
    article_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a KB article (admin only)."""
    stmt = select(KnowledgeBaseArticle).where(KnowledgeBaseArticle.id == article_id)
    result = await db.execute(stmt)
    article = result.scalar_one_or_none()

    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    await db.delete(article)
    await db.commit()
    return {"message": "Article deleted"}
