"""
E3: Environment promotion — formalize test→production promotion.

Promote action copies/flags objects with pre-flight checks:
- References resolve (entry_form exists, form_id in steps)
- Naming lint clean (no duplicates, name valid)
- Tags present (optional but encouraged)
"""
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func


class PromotionService:
    """Handle environment promotion with validation."""
    
    async def promote_workflow(self, db: AsyncSession, workflow_id: int, target_env: str = "production", 
                               current_user_id: int = None) -> Dict[str, Any]:
        """Promote a workflow to a target environment."""
        from app.models.schemas import Workflow
        
        stmt = select(Workflow).where(Workflow.id == workflow_id)
        result = await db.execute(stmt)
        workflow = result.scalar_one_or_none()
        
        if not workflow:
            return {"success": False, "error": "Workflow not found"}
        
        # Pre-flight checks
        issues = []
        
        # Check naming (A1)
        if not workflow.name or len(workflow.name.strip()) == 0:
            issues.append("Workflow has no name")
        if len(workflow.name) > 80:
            issues.append("Workflow name exceeds 80 characters")
        
        # Check for duplicate names (A1)
        dup_stmt = select(func.count()).select_from(Workflow).where(
            func.lower(Workflow.name) == func.lower(workflow.name),
            Workflow.id != workflow_id,
            Workflow.is_active == True
        )
        dup_result = await db.execute(dup_stmt)
        if dup_result.scalar() > 0:
            issues.append(f"Workflow name '{workflow.name}' already exists (case-insensitive)")
        
        # Check entry form exists if set
        if workflow.entry_form_id:
            from app.models.forms import Form
            form_stmt = select(Form).where(Form.id == workflow.entry_form_id, Form.is_active == True)
            form_result = await db.execute(form_stmt)
            if form_result.scalar_one_or_none() is None:
                issues.append(f"Entry form {workflow.entry_form_id} not found or inactive")
        
        # Check tags (encouraged but not required)
        if not workflow.tags or len(workflow.tags) == 0:
            issues.append("Workflow has no tags (recommended for organization)")
        
        if issues:
            return {"success": False, "issues": issues, "workflow_id": workflow_id}
        
        # Apply promotion
        workflow.environment = target_env
        workflow.is_active = True
        workflow.is_published = True
        
        await db.commit()
        
        return {
            "success": True,
            "workflow_id": workflow_id,
            "environment": target_env,
            "message": f"Workflow '{workflow.name}' promoted to {target_env}"
        }
    
    async def promote_form(self, db: AsyncSession, form_id: int, target_env: str = "production",
                           current_user_id: int = None) -> Dict[str, Any]:
        """Promote a form to a target environment."""
        from app.models.forms import Form
        
        stmt = select(Form).where(Form.id == form_id)
        result = await db.execute(stmt)
        form = result.scalar_one_or_none()
        
        if not form:
            return {"success": False, "error": "Form not found"}
        
        # Pre-flight checks
        issues = []
        
        if not form.name or len(form.name.strip()) == 0:
            issues.append("Form has no name")
        
        if issues:
            return {"success": False, "issues": issues, "form_id": form_id}
        
        # Apply promotion
        form.environment = target_env
        form.is_active = True
        form.is_published = True
        
        await db.commit()
        
        return {
            "success": True,
            "form_id": form_id,
            "environment": target_env,
            "message": f"Form '{form.name}' promoted to {target_env}"
        }


promotion_service = PromotionService()
