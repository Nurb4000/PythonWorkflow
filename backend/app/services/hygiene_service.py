"""
D4: Hygiene reports — find duplicates, unreferenced content, broken refs.
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_


class HygieneService:
    """Find data quality issues across the platform."""
    
    async def find_near_duplicates(self, db: AsyncSession, model, name_col, threshold: float = 0.8) -> List[Dict]:
        """Find items with similar names (simple prefix match for now)."""
        stmt = select(model).order_by(model.name)
        result = await db.execute(stmt)
        items = result.scalars().all()
        
        duplicates = []
        for i, item in enumerate(items):
            for j in range(i + 1, len(items)):
                other = items[j]
                # Simple similarity: check if one name starts with the other
                if item.name.lower().startswith(other.name.lower()) or other.name.lower().startswith(item.name.lower()):
                    duplicates.append({
                        "item1": {"id": item.id, "name": item.name},
                        "item2": {"id": other.id, "name": other.name},
                        "reason": "prefix_match"
                    })
        return duplicates
    
    async def find_unreferenced_forms(self, db: AsyncSession, days_inactive: int = 90) -> List[Dict]:
        """Find forms with no runs in N days."""
        from app.models.forms import Form
        from app.models.schemas import WorkflowRun
        
        cutoff = datetime.utcnow() - timedelta(days=days_inactive)
        
        stmt = select(Form).where(Form.is_active == True)
        result = await db.execute(stmt)
        forms = result.scalars().all()
        
        unreferenced = []
        for form in forms:
            # Check if any workflow uses this form as entry_form
            wf_stmt = select(WorkflowRun).where(
                WorkflowRun.entry_form_id == form.id,
                WorkflowRun.created_at > cutoff
            )
            wf_result = await db.execute(wf_stmt)
            if wf_result.scalars().first() is None:
                # Also check human_task steps
                # Simplified: just check entry_form usage
                unreferenced.append({
                    "id": form.id,
                    "name": form.name,
                    "days_since_last_use": "unknown",
                    "reason": "no_recent_runs"
                })
        
        return unreferenced
    
    async def find_broken_references(self, db: AsyncSession) -> List[Dict]:
        """Find workflows with missing entry_form or forms with missing fields."""
        from app.models.schemas import Workflow
        from app.models.forms import Form
        
        issues = []
        
        # Workflows referencing non-existent forms
        stmt = select(Workflow).where(Workflow.entry_form_id != None)
        result = await db.execute(stmt)
        workflows = result.scalars().all()
        
        for wf in workflows:
            form_stmt = select(Form).where(Form.id == wf.entry_form_id, Form.is_active == True)
            form_result = await db.execute(form_stmt)
            if form_result.scalar_one_or_none() is None:
                issues.append({
                    "type": "workflow",
                    "id": wf.id,
                    "name": wf.name,
                    "issue": f"entry_form_id {wf.entry_form_id} references inactive or missing form"
                })
        
        return issues
    
    async def get_hygiene_report(self, db: AsyncSession) -> Dict[str, Any]:
        """Generate full hygiene report (D4 + E4)."""
        return {
            "near_duplicates": await self.find_near_duplicates(db),
            "unreferenced_forms": await self.find_unreferenced_forms(db),
            "broken_references": await self.find_broken_references(db),
            "stale_drafts": await self.find_stale_drafts(db),
            "orphaned_content": await self.find_orphaned_content(db),
            "churn_hotspots": await self.find_churn_hotspots(db),
            "generated_at": datetime.utcnow().isoformat()
        }


hygiene_service = HygieneService()


    async def find_stale_drafts(self, db: AsyncSession, days_inactive: int = 30) -> List[Dict]:
        """Find workflows/forms with no runs in N days that are still drafts."""
        from app.models.schemas import Workflow, WorkflowRun
        from app.models.forms import Form
        
        cutoff = datetime.utcnow() - timedelta(days=days_inactive)
        
        # Stale workflow drafts
        wf_stmt = select(Workflow).where(
            Workflow.is_published == False,
            Workflow.is_active == True
        )
        wf_result = await db.execute(wf_stmt)
        workflows = wf_result.scalars().all()
        
        stale_workflows = []
        for wf in workflows:
            # Check if any runs exist after cutoff
            run_stmt = select(WorkflowRun).where(
                WorkflowRun.workflow_id == wf.id,
                WorkflowRun.created_at > cutoff
            )
            run_result = await db.execute(run_stmt)
            if run_result.scalars().first() is None:
                stale_workflows.append({
                    "type": "workflow",
                    "id": wf.id,
                    "name": wf.name,
                    "reason": f"unpublished draft with no runs in {days_inactive} days"
                })
        
        # Stale form drafts
        form_stmt = select(Form).where(
            Form.is_published == False,
            Form.is_active == True
        )
        form_result = await db.execute(form_stmt)
        forms = form_result.scalars().all()
        
        stale_forms = []
        for form in forms:
            stale_forms.append({
                "type": "form",
                "id": form.id,
                "name": form.name,
                "reason": f"unpublished draft"
            })
        
        return stale_workflows + stale_forms
    
    async def find_orphaned_content(self, db: AsyncSession) -> List[Dict]:
        """Find content with no owner or owned by inactive users."""
        from app.models.schemas import Workflow
        from app.models.forms import Form
        from app.models.auth import User
        
        issues = []
        
        # Workflows without owner
        wf_stmt = select(Workflow).where(
            Workflow.owner_user_id == None,
            Workflow.is_active == True
        )
        wf_result = await db.execute(wf_stmt)
        for wf in wf_result.scalars().all():
            issues.append({
                "type": "workflow",
                "id": wf.id,
                "name": wf.name,
                "reason": "no owner assigned"
            })
        
        # Forms without owner
        form_stmt = select(Form).where(
            Form.owner_user_id == None,
            Form.is_active == True
        )
        form_result = await db.execute(form_stmt)
        for form in form_result.scalars().all():
            issues.append({
                "type": "form",
                "id": form.id,
                "name": form.name,
                "reason": "no owner assigned"
            })
        
        # Content owned by inactive users
        wf_stmt2 = select(Workflow).where(
            Workflow.owner_user_id != None,
            Workflow.is_active == True
        )
        wf_result2 = await db.execute(wf_stmt2)
        for wf in wf_result2.scalars().all():
            user_stmt = select(User).where(User.id == wf.owner_user_id, User.is_active == False)
            user_result = await db.execute(user_stmt)
            if user_result.scalar_one_or_none():
                issues.append({
                    "type": "workflow",
                    "id": wf.id,
                    "name": wf.name,
                    "reason": f"owned by inactive user {wf.owner_user_id}"
                })
        
        return issues
    
    async def find_churn_hotspots(self, db: AsyncSession, threshold: int = 5) -> List[Dict]:
        """Find workflows/forms with high edit churn (many versions in short time)."""
        from app.models.schemas import Workflow
        
        # This is a simplified version — would need version history tracking
        # For now, return empty list
        return []
