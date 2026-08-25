"""
API endpoints for AI-powered generation and assistance
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from app.services.ai_service import ai_service
from app.api.auth import get_current_developer
from app.models.auth import User

router = APIRouter()


# ---------------------------------------------------------------------------
# Request/Response schemas
# ---------------------------------------------------------------------------

class AssistNodeRequest(BaseModel):
    action: str = Field(..., description="generate, explain, fix, or optimize")
    step_type: str = Field(..., description="Workflow step type")
    description: Optional[str] = None
    current_config: Optional[Dict[str, Any]] = None
    upstream_data_shapes: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class AssistQueryRequest(BaseModel):
    action: str = Field(..., description="generate, explain, or fix")
    description: Optional[str] = None
    table: Optional[str] = None
    sql: Optional[str] = None
    error_message: Optional[str] = None
    available_columns: Optional[List[Dict[str, Any]]] = None


class AssistFormRequest(BaseModel):
    action: str = Field(..., description="suggest_fields or improve_schema")
    description: Optional[str] = None
    current_schema: Optional[Dict[str, Any]] = None


class ExplainErrorRequest(BaseModel):
    step_type: str
    step_config: Dict[str, Any]
    error_message: str
    input_data_sample: Optional[Dict[str, Any]] = None


class AssistReportRequest(BaseModel):
    action: str = Field(..., description="generate or improve")
    description: Optional[str] = None
    current_report: Optional[Dict[str, Any]] = None


class AssistCronRequest(BaseModel):
    description: str = Field(..., description="Natural language description of schedule")


class AssistWebhookRequest(BaseModel):
    action: str = Field(..., description="generate or validate")
    description: Optional[str] = None
    current_config: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Existing endpoints (preserved)
# ---------------------------------------------------------------------------

@router.post("/ai/generate-step")
async def generate_step(
    description: str = Query(..., description="Natural language description of the step"),
    context: Optional[dict] = None,
    user: Any = Depends(get_current_developer),
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
    template_name: Optional[str] = None,
    user: Any = Depends(get_current_developer),
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
    description: str = Query(..., description="Natural language description of the form"),
    user: Any = Depends(get_current_developer),
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
async def get_knowledge_base(user: User = Depends(get_current_developer)):
    """Get available knowledge base domains"""
    return {
        "domains": list(ai_service.kb.keys()),
        "step_types": list(ai_service.VALID_STEP_TYPES.keys()),
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
                "kb_domains_loaded": len(ai_service.kb),
            }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "llama_cpp_url": ai_service.base_url
        }


# ---------------------------------------------------------------------------
# New assist endpoints
# ---------------------------------------------------------------------------

@router.post("/ai/assist-node")
async def assist_node(
    request: AssistNodeRequest,
    user: Any = Depends(get_current_developer),
):
    """Generate, explain, fix, or optimize a workflow node configuration"""
    valid_actions = {"generate", "explain", "fix", "optimize"}
    if request.action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Action must be one of: {valid_actions}")

    if request.action == "generate" and not request.description:
        raise HTTPException(status_code=400, detail="Description is required for generate action")

    if request.action in ("explain", "fix", "optimize") and not request.current_config:
        raise HTTPException(status_code=400, detail="current_config is required for this action")

    try:
        result = await ai_service.assist_node(
            action=request.action,
            step_type=request.step_type,
            description=request.description,
            current_config=request.current_config,
            upstream_data_shapes=request.upstream_data_shapes,
            error_message=request.error_message,
        )
        return {
            "success": True,
            "result": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI assist failed: {str(e)}")


@router.post("/ai/assist-query")
async def assist_query(
    request: AssistQueryRequest,
    user: Any = Depends(get_current_developer),
):
    """Generate, explain, or fix SQL queries for the data explorer"""
    valid_actions = {"generate", "explain", "fix"}
    if request.action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Action must be one of: {valid_actions}")

    if request.action == "generate" and not request.description:
        raise HTTPException(status_code=400, detail="Description is required for generate action")

    if request.action in ("explain", "fix") and not request.sql:
        raise HTTPException(status_code=400, detail="SQL is required for this action")

    try:
        result = await ai_service.assist_query(
            action=request.action,
            description=request.description,
            table=request.table,
            sql=request.sql,
            error_message=request.error_message,
            available_columns=request.available_columns,
        )
        return {
            "success": True,
            "result": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI query assist failed: {str(e)}")


@router.post("/ai/assist-form")
async def assist_form(
    request: AssistFormRequest,
    user: Any = Depends(get_current_developer),
):
    """Suggest or improve form fields"""
    valid_actions = {"suggest_fields", "improve_schema"}
    if request.action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Action must be one of: {valid_actions}")

    if request.action == "suggest_fields" and not request.description:
        raise HTTPException(status_code=400, detail="Description is required for suggest_fields action")

    if request.action == "improve_schema" and not request.current_schema:
        raise HTTPException(status_code=400, detail="current_schema is required for improve_schema action")

    try:
        result = await ai_service.assist_form(
            action=request.action,
            description=request.description,
            current_schema=request.current_schema,
        )
        return {
            "success": True,
            "result": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI form assist failed: {str(e)}")


@router.post("/ai/assist-report")
async def assist_report(
    request: AssistReportRequest,
    user: Any = Depends(get_current_developer),
):
    """Assist with report definition creation and improvement"""
    valid_actions = {"generate", "improve"}
    if request.action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Action must be one of: {valid_actions}")

    if request.action == "generate" and not request.description:
        raise HTTPException(status_code=400, detail="Description is required for generate action")

    if request.action == "improve" and not request.current_report:
        raise HTTPException(status_code=400, detail="current_report is required for improve action")

    try:
        result = await ai_service.assist_report(
            action=request.action,
            description=request.description,
            current_report=request.current_report,
        )
        return {
            "success": True,
            "result": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI report assist failed: {str(e)}")


@router.post("/ai/assist-cron")
async def assist_cron(
    request: AssistCronRequest,
    user: Any = Depends(get_current_developer),
):
    """Generate cron expression from natural language description"""
    try:
        result = await ai_service.assist_cron(
            description=request.description,
        )
        return {
            "success": True,
            "result": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI cron assist failed: {str(e)}")


@router.post("/ai/assist-webhook")
async def assist_webhook(
    request: AssistWebhookRequest,
    user: Any = Depends(get_current_developer),
):
    """Assist with webhook configuration"""
    valid_actions = {"generate", "validate"}
    if request.action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Action must be one of: {valid_actions}")

    if request.action == "generate" and not request.description:
        raise HTTPException(status_code=400, detail="Description is required for generate action")

    if request.action == "validate" and not request.current_config:
        raise HTTPException(status_code=400, detail="current_config is required for validate action")

    try:
        result = await ai_service.assist_webhook(
            action=request.action,
            description=request.description,
            current_config=request.current_config,
        )
        return {
            "success": True,
            "result": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI webhook assist failed: {str(e)}")


@router.post("/ai/explain-error")
async def explain_error(
    request: ExplainErrorRequest,
    user: Any = Depends(get_current_developer),
):
    """Diagnose a workflow run failure"""
    try:
        result = await ai_service.explain_error(
            step_type=request.step_type,
            step_config=request.step_config,
            error_message=request.error_message,
            input_data_sample=request.input_data_sample,
        )
        return {
            "success": True,
            "result": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI error diagnosis failed: {str(e)}")
