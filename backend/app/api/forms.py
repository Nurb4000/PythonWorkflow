"""
Form API endpoints
"""
import os
import uuid

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File as FileParam
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from app.core.database import get_db
from app.services.form_service import form_service
from app.services.auth_service import auth_service
from app.models.auth import User
from app.api.auth import get_current_user, get_current_developer

router = APIRouter()

UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "uploads", "form_uploads"
)


@router.post("/forms/upload")
async def upload_form_file(
    file: UploadFile = FileParam(...),
    current_user: User = Depends(get_current_user)
):
    """Upload an attachment for a form submission (authenticated users)"""
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        original = os.path.basename(file.filename or "file")
        stored = f"{uuid.uuid4().hex}_{original}"
        path = os.path.join(UPLOAD_DIR, stored)
        content = await file.read()
        with open(path, "wb") as f:
            f.write(content)
        return {"filename": stored, "original_name": original}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/forms/download/{filename}")
async def download_form_file(
    filename: str,
    current_user: User = Depends(get_current_user)
):
    """Download an uploaded form attachment"""
    try:
        safe = os.path.basename(filename)
        path = os.path.join(UPLOAD_DIR, safe)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(path, filename=safe)
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List forms accessible to user"""
    try:
        forms = await form_service.list_forms(db, current_user, environment)
        
        return [
            {
                "id": f.id,
                "name": f.name,
                "description": f.description,
                "version": f.version,
                "environment": f.environment,
                "is_published": f.is_published,
                "created_at": f.created_at
            }
            for f in forms
        ]
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
    """Delete a form (admin/developer only)"""
    success = await form_service.delete_form(db, form_id)
    if not success:
        raise HTTPException(status_code=404, detail="Form not found")
    
    return {"message": "Form deleted successfully"}


@router.post("/forms/{form_id}/submit")
async def submit_form(
    form_id: int,
    data: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Submit data to a form"""
    try:
        submission = await form_service.submit_form(db, form_id, data, current_user.id)
        
        return {
            "id": submission.id,
            "form_id": submission.form_id,
            "status": submission.status,
            "submitted_at": submission.created_at
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
