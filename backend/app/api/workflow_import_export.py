"""
Workflow import/export API endpoints.
"""
import logging
import os
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.auth import User
from app.api.auth import get_current_developer
from app.services.workflow_export_service import workflow_export_service
from app.services.workflow_import_service import workflow_import_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/{workflow_id}/export")
async def export_workflow(
    workflow_id: int,
    fmt: str = Query(default="xml", description="Export format: xml or json"),
    include_forms: bool = Query(default=True),
    include_groups: bool = Query(default=True),
    include_schedules: bool = Query(default=True),
    include_permissions: bool = Query(default=True),
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Export a workflow with dependencies as XML or JSON."""
    try:
        content, filename = await workflow_export_service.export_workflow(
            db,
            workflow_id,
            format=fmt,
            include_forms=include_forms,
            include_groups=include_groups,
            include_schedules=include_schedules,
            include_permissions=include_permissions,
        )

        content_type = "application/xml" if fmt == "xml" else "application/json"
        return Response(
            content=content.encode("utf-8"),
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Export failed for workflow {workflow_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")


@router.post("/import")
async def import_workflow(
    file_content: str,
    filename: str = "workflow.xml",
    environment: str = "preserve",
    on_conflict: str = "copy",
    create_forms: bool = True,
    create_groups: bool = True,
    match_users_by_email: bool = True,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Import a workflow package from XML or JSON content.

    The file_content is passed as a query parameter (URL-encoded).
    For large files, consider using the body instead.

    Options:
      - environment: 'preserve' (keep source env) or 'test'/'production'
      - on_conflict: 'copy' (create as Copy), 'skip', or 'overwrite'
      - create_forms: create missing forms referenced by the workflow
      - create_groups: create missing groups referenced by the workflow
      - match_users_by_email: resolve user assignments by email address
    """
    if on_conflict not in ("copy", "skip", "overwrite"):
        raise HTTPException(status_code=400, detail="on_conflict must be 'copy', 'skip', or 'overwrite'")

    options = {
        "environment": environment,
        "on_conflict": on_conflict,
        "create_forms": create_forms,
        "create_groups": create_groups,
        "match_users_by_email": match_users_by_email,
    }

    try:
        result = await workflow_import_service.import_workflow(
            db, file_content, filename, current_user.id, options
        )
        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")


@router.post("/import-body")
async def import_workflow_body(
    body: dict,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Import a workflow package with content in the request body (for large files).

    Body format: {
      "file_content": "...",
      "filename": "workflow.xml",
      "environment": "preserve",
      "on_conflict": "copy",
      "create_forms": true,
      "create_groups": true,
      "match_users_by_email": true
    }
    """
    file_content = body.get("file_content", "")
    filename = body.get("filename", "workflow.xml")
    environment = body.get("environment", "preserve")
    on_conflict = body.get("on_conflict", "copy")
    create_forms = body.get("create_forms", True)
    create_groups = body.get("create_groups", True)
    match_users_by_email = body.get("match_users_by_email", True)

    if on_conflict not in ("copy", "skip", "overwrite"):
        raise HTTPException(status_code=400, detail="on_conflict must be 'copy', 'skip', or 'overwrite'")

    options = {
        "environment": environment,
        "on_conflict": on_conflict,
        "create_forms": create_forms,
        "create_groups": create_groups,
        "match_users_by_email": match_users_by_email,
    }

    try:
        result = await workflow_import_service.import_workflow(
            db, file_content, filename, current_user.id, options
        )
        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")


@router.post("/{workflow_id}/duplicate")
async def duplicate_workflow(
    workflow_id: int,
    new_name: str = None,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db),
):
    """Duplicate a workflow within the same system."""
    try:
        new_wf = await workflow_import_service.duplicate_workflow(
            db, workflow_id, current_user.id, new_name
        )
        return {
            "id": new_wf.id,
            "name": new_wf.name,
            "message": f"Workflow duplicated as '{new_wf.name}'"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Duplication failed: {e}")
