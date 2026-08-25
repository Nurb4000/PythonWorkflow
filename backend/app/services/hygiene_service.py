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
        """Generate full hygiene report."""
        return {
            "near_duplicates": await self.find_near_duplicates(db),
            "unreferenced_forms": await self.find_unreferenced_forms(db),
            "broken_references": await self.find_broken_references(db),
            "generated_at": datetime.utcnow().isoformat()
        }


hygiene_service = HygieneService()
