"""
Form API endpoints
"""
import os
import uuid

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File as FileParam
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from typing import Optional, List
from app.core.database import get_db
from app.services.form_service import form_service
from app.services.auth_service import auth_service
from app.models.auth import User
from app.models.forms import Form, FormUpload
from app.models.schemas import Task, WorkflowRun
from app.api.auth import get_current_user, get_current_developer

router = APIRouter()

UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "uploads", "form_uploads"
)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


def _contains_ref(data, stored_name: str) -> bool:
    """True if stored_name appears anywhere in nested form data (dict/list)."""
    if isinstance(data, dict):
        return any(_contains_ref(v, stored_name) for v in data.values())
    if isinstance(data, list):
        return any(_contains_ref(v, stored_name) for v in data)
    return data == stored_name


async def _file_accessible(db: AsyncSession, user: User, stored_name: str) -> bool:
    """Who may download a file:
    - admins/developers: always
    - the uploader: always
    - staff: if the file is referenced by a task assigned to them (or their group)
      or by the run of a task assigned to them
    """
    if user.role in ("admin", "developer"):
        return True

    result = await db.execute(select(FormUpload).where(FormUpload.stored_name == stored_name))
    upload = result.scalar_one_or_none()
    if not upload:
        return False
    if upload.uploaded_by is not None and upload.uploaded_by == user.id:
        return True

    if user.role != "staff":
        return False

    conditions = [Task.assigned_to_user_id == user.id]
    from app.models.auth import user_groups
    group_result = await db.execute(
        select(user_groups.c.group_id).where(user_groups.c.user_id == user.id)
    )
    group_ids = [row[0] for row in group_result.all()]
    if group_ids:
        conditions.append(Task.assigned_group_id.in_(group_ids))
    tasks_result = await db.execute(select(Task).where(or_(*conditions)))
    tasks = tasks_result.scalars().all()
    for t in tasks:
        if _contains_ref(t.task_data, stored_name) or _contains_ref(t.result_data, stored_name):
            return True
    run_ids = [t.workflow_run_id for t in tasks if t.workflow_run_id]
    if run_ids:
        runs_result = await db.execute(select(WorkflowRun).where(WorkflowRun.id.in_(run_ids)))
        for run in runs_result.scalars().all():
            if _contains_ref(run.input_data, stored_name) or _contains_ref(run.output_data, stored_name):
                return True
    return False


@router.post("/forms/upload")
async def upload_form_file(
    file: UploadFile = FileParam(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload an attachment for a form submission (authenticated users)"""
    try:
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit",
            )
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        original = os.path.basename(file.filename or "file")
        stored = f"{uuid.uuid4().hex}_{original}"
        path = os.path.join(UPLOAD_DIR, stored)
        with open(path, "wb") as f:
            f.write(content)
        upload = FormUpload(
            original_name=original,
            stored_name=stored,
            content_type=file.content_type or "",
            size_bytes=len(content),
            uploaded_by=current_user.id,
        )
        db.add(upload)
        await db.commit()
        return {"filename": stored, "original_name": original}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/forms/download/{filename}")
async def download_form_file(
    filename: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Download an uploaded form attachment"""
    try:
        safe = os.path.basename(filename)
        if not await _file_accessible(db, current_user, safe):
            raise HTTPException(status_code=403, detail="You do not have access to this file")
        path = os.path.join(UPLOAD_DIR, safe)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="File not found")
        result = await db.execute(select(FormUpload).where(FormUpload.stored_name == safe))
        upload = result.scalar_one_or_none()
        download_name = upload.original_name if upload else safe
        return FileResponse(path, filename=download_name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/forms")
async def create_form(
    name: str,
    description: str = "",
    schema: str = None,  # JSON string
    environment: str = "test",
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db)
):
    """Create a new form (admin/developer only)"""
    try:
        import json
        schema_data = json.loads(schema) if schema else {}
        
        form = await form_service.create_form(
            db, name, description, schema_data, current_user.id, environment
        )
        
        return {
            "id": form.id,
            "name": form.name,
            "description": form.description,
            "schema": form.schema_json,
            "version": form.version,
            "environment": form.environment
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/forms")
async def list_forms(
    environment: Optional[str] = None,
    include_inactive: bool = Query(False),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List forms accessible to user. By default excludes deactivated forms."""
    try:
        result = await form_service.list_forms(db, current_user, environment, include_inactive, page, page_size)
        
        return {
            "items": [
                {
                    "id": f.id,
                    "name": f.name,
                    "description": f.description,
                    "version": f.version,
                    "environment": f.environment,
                    "is_published": f.is_published,
                    "is_active": f.is_active,
                    "created_at": f.created_at
                }
                for f in result["items"]
            ],
            "total": result["total"],
            "page": result["page"],
            "page_size": result["page_size"],
            "pages": result["pages"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/forms/{form_id}")
async def get_form(
    form_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get form details"""
    try:
        form = await form_service.get_form(db, form_id)
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")
        
        return {
            "id": form.id,
            "name": form.name,
            "description": form.description,
            "schema": form.schema_json,
            "version": form.version,
            "environment": form.environment,
            "is_published": form.is_published
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/forms/{form_id}")
async def update_form(
    form_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    schema: Optional[str] = None,
    is_published: Optional[bool] = None,
    environment: Optional[str] = None,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db)
):
    """Update a form (admin/developer only)"""
    try:
        kwargs = {}
        if name:
            kwargs["name"] = name
        if description:
            kwargs["description"] = description
        if schema:
            import json
            kwargs["schema_json"] = json.loads(schema)
        if is_published is not None:
            kwargs["is_published"] = is_published
        if environment:
            kwargs["environment"] = environment
        
        form = await form_service.update_form(db, form_id, **kwargs)
        
        return {
            "id": form.id,
            "name": form.name,
            "version": form.version
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/forms/{form_id}")
async def delete_form(
    form_id: int,
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db)
):
    """Deactivate a form (admin/developer only)"""
    success = await form_service.delete_form(db, form_id)
    if not success:
        raise HTTPException(status_code=404, detail="Form not found")

    return {"message": "Form deactivated successfully"}


@router.post("/forms/{form_id}/submit")
async def submit_form(
    form_id: int,
    data: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Submit data to a form"""
    try:
        # Process lookup fields before submission
        from app.models.forms import Form
        from sqlalchemy import select
        
        form_stmt = select(Form).where(Form.id == form_id, Form.is_active == True)
        form_result = await db.execute(form_stmt)
        form = form_result.scalar_one_or_none()
        
        if form and form.schema_json:
            import json
            schema = json.loads(form.schema_json) if isinstance(form.schema_json, str) else form.schema_json
            properties = schema.get("properties", {})
            
            # Check for lookup fields and resolve them
            from app.services.lookup_service import lookup_service
            for field_name, field_def in properties.items():
                if isinstance(field_def, dict) and field_def.get("type") == "lookup" and field_def.get("lookup_config"):
                    lookup_value = data.get(field_name)
                    if lookup_value:
                        lookup_result = await lookup_service.perform_lookup(
                            db, 
                            field_def["lookup_config"], 
                            lookup_value
                        )
                        if lookup_result:
                            # Replace lookup field value with selected item ID
                            data[field_name] = str(lookup_result.get('id', lookup_value))
                            
                            # Auto-fill related fields if configured
                            if field_def["lookup_config"].get("auto_fill"):
                                result_fields = field_def["lookup_config"].get("result_fields", [])
                                extracted = await lookup_service.extract_result_fields(lookup_result, result_fields)
                                for rf in result_fields:
                                    if rf in extracted and rf not in data:
                                        data[rf] = extracted[rf]
        
        submission = await form_service.submit_form(db, form_id, data, current_user.id)
        
        return {
            "id": submission.id,
            "form_id": submission.form_id,
            "status": submission.status,
            "submitted_at": submission.created_at,
            "lookup_resolved": True
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/forms/{form_id}/submissions")
async def get_form_submissions(
    form_id: int,
    limit: int = Query(default=100, le=1000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get form submissions"""
    try:
        # Users can only see their own submissions unless admin
        user_id = current_user.id if current_user.role != "admin" else None
        
        submissions = await form_service.get_submissions(db, form_id, user_id, limit)
        
        return [
            {
                "id": s.id,
                "form_id": s.form_id,
                "submitted_by": s.submitted_by,
                "data": s.data,
                "status": s.status,
                "created_at": s.created_at
            }
            for s in submissions
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/submissions/{submission_id}/status")
async def update_submission_status(
    submission_id: int,
    status: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update submission status (admin/staff only)"""
    if current_user.role not in ["admin", "staff"]:
        raise HTTPException(status_code=403, detail="Admin or staff access required")
    
    try:
        submission = await form_service.update_submission_status(db, submission_id, status)
        
        return {
            "id": submission.id,
            "status": submission.status
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/forms/templates")
async def list_templates(
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List form templates"""
    try:
        templates = await form_service.list_templates(db, category)
        
        return [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "schema": t.schema_json
            }
            for t in templates
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/forms/{form_id}/save-template")
async def save_as_template(
    form_id: int,
    template_name: str,
    category: str = "general",
    current_user: User = Depends(get_current_developer),
    db: AsyncSession = Depends(get_db)
):
    """Save a form as a template (admin/developer only)"""
    try:
        template = await form_service.save_as_template(db, form_id, template_name, category)
        
        return {
            "id": template.id,
            "name": template.name,
            "category": template.category
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
