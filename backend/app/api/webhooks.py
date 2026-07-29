"""
API endpoints for webhooks and external triggers
"""
from fastapi import APIRouter, HTTPException, Header, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.core.database import get_db
from app.services.scheduler import scheduler_service
from app.models.schemas import Workflow

router = APIRouter()


@router.post("/webhook/{workflow_id}")
async def webhook_trigger(
    workflow_id: int,
    payload: dict,
    x_webhook_secret: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
):
    """Trigger a workflow via webhook"""
    
    try:
        # Verify workflow exists
        stmt = Workflow.__table__.select().where(Workflow.id == workflow_id)
        result = await db.execute(stmt)
        workflow = result.fetchone()
        
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        # Trigger the workflow
        run = await scheduler_service.trigger_webhook(workflow_id, payload, x_webhook_secret)
        
        return {
            "success": True,
            "run_id": run.id,
            "workflow_id": workflow_id,
            "message": "Workflow triggered successfully"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Webhook trigger failed: {str(e)}")


@router.post("/api/trigger/{workflow_id}")
async def external_trigger(
    workflow_id: int,
    input_data: dict,
    x_api_key: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
):
    """Trigger a workflow via external API"""
    
    try:
        # Verify workflow exists
        stmt = Workflow.__table__.select().where(Workflow.id == workflow_id)
        result = await db.execute(stmt)
        workflow = result.fetchone()
        
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        # Trigger the workflow
        run = await scheduler_service.trigger_external_api(workflow_id, input_data, x_api_key)
        
        return {
            "success": True,
            "run_id": run.id,
            "workflow_id": workflow_id,
            "message": "Workflow triggered successfully"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API trigger failed: {str(e)}")


@router.get("/schedules/status")
async def get_schedule_status():
    """Get status of all active schedules"""
    schedules = scheduler_service.get_active_schedules()
    return {
        "active_schedules": len(schedules),
        "schedules": schedules
    }
