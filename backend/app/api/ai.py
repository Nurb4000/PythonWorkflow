"""
API endpoints for AI-powered generation
"""
from fastapi import APIRouter, HTTPException
from app.services.ai_service import ai_service

router = APIRouter()


@router.post("/ai/generate-step")
async def generate_step(description: str, context: dict = None):
    """Generate a workflow step from natural language description"""
    try:
        step = await ai_service.generate_step(description, context)
        return step
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai/generate-form")
async def generate_form(description: str):
    """Generate a form schema from natural language description"""
    try:
        schema = await ai_service.generate_form_schema(description)
        return schema
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
