"""
API endpoints for knowledge base and templates
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from app.core.database import get_db
from app.services.template_service import template_service

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
