"""
API endpoints for AI-powered generation
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional
from app.services.ai_service import ai_service

router = APIRouter()


@router.post("/ai/generate-step")
async def generate_step(
    description: str = Query(..., description="Natural language description of the step"),
    context: Optional[dict] = Body(None)
):
    """Generate a workflow step from natural language description"""
    try:
        step = await ai_service.generate_step(description, context)
        return {
            "success": True,
            "step": step,
            "message": "Step generated successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")


@router.post("/ai/generate-workflow")
async def generate_workflow(
    description: str = Query(..., description="Natural language description of the workflow"),
    template_name: Optional[str] = Query(None, description="Template to use as reference")
):
    """Generate a complete workflow from natural language description"""
    try:
        steps = await ai_service.generate_workflow(description, template_name)
        return {
            "success": True,
            "steps": steps,
            "message": f"Generated {len(steps)} steps"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")


@router.post("/ai/generate-form")
async def generate_form(
    description: str = Query(..., description="Natural language description of the form")
):
    """Generate a form schema from natural language description"""
    try:
        schema = await ai_service.generate_form_schema(description)
        return {
            "success": True,
            "schema": schema,
            "message": "Form schema generated successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")


@router.get("/ai/knowledge-base")
async def get_knowledge_base():
    """Get available knowledge base content"""
    return {
        "prompts": list(ai_service.knowledge_base["prompts"].keys()),
        "templates": [t.get("name") for t in ai_service.knowledge_base["templates"]],
        "step_types": list(ai_service.VALID_STEP_TYPES.keys())
    }


@router.get("/ai/health")
async def ai_health():
    """Check AI service health"""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{ai_service.base_url}/health", timeout=5.0)
            return {
                "status": "healthy",
                "llama_cpp_url": ai_service.base_url,
                "model": ai_service.model,
                "knowledge_base_loaded": len(ai_service.knowledge_base["templates"]) > 0
            }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "llama_cpp_url": ai_service.base_url
        }
