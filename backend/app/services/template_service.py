"""
Workflow template service for managing reusable templates
"""
import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.schemas import Workflow, WorkflowStep
from app.schemas.workflow import WorkflowCreate

logger = logging.getLogger(__name__)


class TemplateService:
    """Manage workflow templates"""
    
    def __init__(self):
        self.templates_path = Path("knowledge-base/templates")
        self._templates: List[Dict[str, Any]] = []
        self._load_templates()
    
    def _load_templates(self):
        """Load templates from knowledge base"""
        if self.templates_path.exists():
            for file in self.templates_path.glob("*.json"):
                try:
                    with open(file, 'r') as f:
                        template = json.load(f)
                        template['source_file'] = file.name
                        self._templates.append(template)
                    logger.info(f"Loaded template: {template.get('name', file.name)}")
                except Exception as e:
                    logger.error(f"Failed to load template {file}: {str(e)}")
    
    def get_templates(self) -> List[Dict[str, Any]]:
        """Get all available templates"""
        return self._templates
    
    def get_template(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a specific template by name"""
        return next((t for t in self._templates if t.get("name") == name), None)
    
    async def create_from_template(self, db: AsyncSession, template_name: str, 
                                    customizations: Optional[Dict[str, Any]] = None) -> Workflow:
        """Create a workflow from a template"""
        
        template = self.get_template(template_name)
        if not template:
            raise ValueError(f"Template '{template_name}' not found")
        
        # Apply customizations
        if customizations:
            if "name" in customizations:
                template["name"] = customizations["name"]
            if "description" in customizations:
                template["description"] = customizations["description"]
            if "steps" in customizations:
                template["steps"] = customizations["steps"]
        
        # Create workflow
        workflow_create = WorkflowCreate(
            name=template["name"],
            description=template.get("description", ""),
            steps=template.get("steps", [])
        )
        
        workflow = Workflow(
            name=workflow_create.name,
            description=workflow_create.description,
            version=1
        )
        db.add(workflow)
        await db.flush()
        
        # Create steps
        for i, step_data in enumerate(workflow_create.steps):
            step = WorkflowStep(
                workflow_id=workflow.id,
                step_type=step_data["step_type"],
                definition=step_data.get("definition", {}),
                position=i,
                condition_expr=step_data.get("condition_expr", ""),
                is_enabled=step_data.get("is_enabled", True)
            )
            db.add(step)
        
        await db.commit()
        await db.refresh(workflow)
        
        logger.info(f"Created workflow '{workflow.name}' from template '{template_name}'")
        return workflow
    
    async def save_template(self, db: AsyncSession, workflow_id: int, template_name: str) -> bool:
        """Save a workflow as a template"""
        
        # Get workflow with steps
        stmt = (
            select(Workflow)
            .where(Workflow.id == workflow_id)
        )
        result = await db.execute(stmt)
        workflow = result.scalar_one_or_none()
        
        if not workflow:
            return False
        
        # Get steps
        stmt = select(WorkflowStep).where(WorkflowStep.workflow_id == workflow_id)
        result = await db.execute(stmt)
        steps = result.scalars().all()
        
        # Create template structure
        template = {
            "name": template_name,
            "description": workflow.description,
            "steps": [
                {
                    "step_type": step.step_type,
                    "definition": step.definition,
                    "condition_expr": step.condition_expr,
                    "is_enabled": step.is_enabled
                }
                for step in steps
            ]
        }
        
        # Save to file
        template_file = self.templates_path / f"{template_name.lower().replace(' ', '-')}.json"
        with open(template_file, 'w') as f:
            json.dump(template, f, indent=2)
        
        logger.info(f"Saved template: {template_name}")
        return True


# Singleton instance
template_service = TemplateService()
