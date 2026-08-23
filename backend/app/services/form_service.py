"""
Form management service
"""
import json
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from app.models.forms import Form, FormSubmission, FormTemplate
from app.models.auth import User

logger = logging.getLogger(__name__)


VALID_FIELD_TYPES = [
    "string", "number", "integer", "boolean", "object", "array",
    "email", "textarea", "select", "info",
    "date", "date-time", "file",
]

STRING_FIELD_TYPES = {"string", "email", "textarea", "select", "info", "date", "date-time", "file"}


class FormService:
    """Manage forms, submissions, and templates"""
    
    async def create_form(self, db: AsyncSession, name: str, description: str, 
                         schema: Dict[str, Any], user_id: int, environment: str = "test") -> Form:
        """Create a new form"""
        
        # Validate schema
        self._validate_schema(schema)
        
        form = Form(
            name=name,
            description=description,
            schema_json=schema,
            version=1,
            created_by=user_id,
            environment=environment
        )
        
        db.add(form)
        await db.commit()
        await db.refresh(form)
        
        logger.info(f"Created form: {name} (ID: {form.id})")
        return form
    
    async def update_form(self, db: AsyncSession, form_id: int, **kwargs) -> Form:
        """Update a form"""
        stmt = select(Form).where(Form.id == form_id)
        result = await db.execute(stmt)
        form = result.scalar_one_or_none()
        
        if not form:
            raise ValueError(f"Form {form_id} not found")
        
        allowed_fields = ['name', 'description', 'schema_json', 'is_active', 'environment', 'is_published']
        for field in allowed_fields:
            if field in kwargs:
                setattr(form, field, kwargs[field])
        
        form.version += 1
        await db.commit()
        await db.refresh(form)
        
        logger.info(f"Updated form: {form.name} (ID: {form.id})")
        return form
    
    async def delete_form(self, db: AsyncSession, form_id: int) -> bool:
        """Deactivate a form (soft-delete)"""
        stmt = select(Form).where(Form.id == form_id)
        result = await db.execute(stmt)
        form = result.scalar_one_or_none()

        if not form:
            return False

        form.is_active = False
        await db.commit()
        return True
    
    async def get_form(self, db: AsyncSession, form_id: int) -> Optional[Form]:
        """Get form by ID"""
        stmt = select(Form).where(Form.id == form_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def list_forms(self, db: AsyncSession, user: User, environment: Optional[str] = None, include_inactive: bool = False) -> List[Form]:
        """List forms accessible to user"""

        if user.role in ("admin", "developer"):
            stmt = select(Form)
            if not include_inactive:
                stmt = stmt.where(Form.is_active == True)
            if environment:
                stmt = stmt.where(Form.environment == environment)
        else:
            # Non-developer users can only see published forms in production
            stmt = select(Form).where(
                Form.is_published == True,
                Form.environment == "production",
                Form.is_active == True
            )
        
        result = await db.execute(stmt)
        return result.scalars().all()
    
    async def submit_form(self, db: AsyncSession, form_id: int, data: Dict[str, Any],
                         user_id: Optional[int] = None) -> FormSubmission:
        """Submit data to a form"""

        # Get form and validate data against schema
        stmt = select(Form).where(Form.id == form_id, Form.is_active == True, Form.is_published == True)
        result = await db.execute(stmt)
        form = result.scalar_one_or_none()

        if not form:
            raise ValueError(f"Form {form_id} not found, inactive, or not published")

        # Validate submission data
        self._validate_submission(form.schema_json, data)

        # Handle reference fields - save values back to source table
        properties = form.schema_json.get("properties", {})
        for field_name, field_def in properties.items():
            if field_def.get("source") == "reference" and field_name in data:
                ref_table = field_def.get("ref_table")
                ref_column = field_def.get("ref_column")
                # Look for ref_record_id in submission data (prefixed with __ref_)
                ref_key = f"__ref_{field_name}"
                ref_record_id = data.get(ref_key) or field_def.get("ref_record_id")
                if ref_table and ref_column and ref_record_id:
                    from app.services.data_query_service import QUERYABLE_TABLES
                    if ref_table in QUERYABLE_TABLES:
                        model = QUERYABLE_TABLES[ref_table][0]
                        stmt = select(model).where(model.id == ref_record_id)
                        result = await db.execute(stmt)
                        record = result.scalar_one_or_none()
                        if record:
                            setattr(record, ref_column, data[field_name])
                            logger.info(f"Saved reference field '{field_name}' to {ref_table}.{ref_column} for record {ref_record_id}")

        submission = FormSubmission(
            form_id=form_id,
            submitted_by=user_id,
            data=data,
            status="submitted"
        )

        db.add(submission)
        await db.commit()
        await db.refresh(submission)

        logger.info(f"Form submission: {form.name} (ID: {submission.id})")
        return submission
    
    async def get_submissions(self, db: AsyncSession, form_id: int, 
                            user_id: Optional[int] = None, limit: int = 100) -> List[FormSubmission]:
        """Get form submissions"""
        
        stmt = select(FormSubmission).where(FormSubmission.form_id == form_id)
        
        if user_id:
            stmt = stmt.where(FormSubmission.submitted_by == user_id)
        
        stmt = stmt.order_by(FormSubmission.created_at.desc()).limit(limit)
        
        result = await db.execute(stmt)
        return result.scalars().all()
    
    async def update_submission_status(self, db: AsyncSession, submission_id: int, status: str) -> FormSubmission:
        """Update submission status (approved/rejected)"""
        stmt = select(FormSubmission).where(FormSubmission.id == submission_id)
        result = await db.execute(stmt)
        submission = result.scalar_one_or_none()
        
        if not submission:
            raise ValueError(f"Submission {submission_id} not found")
        
        if status not in ["submitted", "approved", "rejected"]:
            raise ValueError(f"Invalid status: {status}")
        
        submission.status = status
        await db.commit()
        await db.refresh(submission)
        
        return submission
    
    async def create_template(self, db: AsyncSession, name: str, description: str, 
                            schema: Dict[str, Any], category: str = "general") -> FormTemplate:
        """Create a form template"""
        
        template = FormTemplate(
            name=name,
            description=description,
            schema_json=schema,
            category=category
        )
        
        db.add(template)
        await db.commit()
        await db.refresh(template)
        
        logger.info(f"Created form template: {name}")
        return template
    
    async def list_templates(self, db: AsyncSession, category: Optional[str] = None) -> List[FormTemplate]:
        """List form templates"""
        stmt = select(FormTemplate).where(FormTemplate.is_active == True)
        
        if category:
            stmt = stmt.where(FormTemplate.category == category)
        
        result = await db.execute(stmt)
        return result.scalars().all()
    
    async def save_as_template(self, db: AsyncSession, form_id: int, template_name: str, 
                              category: str = "general") -> FormTemplate:
        """Save a form as a template"""
        form = await self.get_form(db, form_id)
        if not form:
            raise ValueError(f"Form {form_id} not found")
        
        template = await self.create_template(db, template_name, form.description, form.schema_json, category)
        logger.info(f"Saved form {form.name} as template: {template_name}")
        return template
    
    def _validate_schema(self, schema: Dict[str, Any]) -> None:
        """Validate form schema"""
        if schema.get("type") != "object":
            raise ValueError("Form schema must have type 'object'")
        
        if "properties" not in schema:
            raise ValueError("Form schema must have 'properties'")
        
        for field_name, field_def in schema["properties"].items():
            if "type" not in field_def:
                raise ValueError(f"Field '{field_name}' must have a 'type'")
            if field_def["type"] not in VALID_FIELD_TYPES:
                raise ValueError(f"Field '{field_name}' has invalid type: {field_def['type']}")
    
    def _validate_submission(self, schema: Dict[str, Any], data: Dict[str, Any]) -> None:
        """Validate submission data against schema"""
        properties = schema.get("properties", {})
        required_fields = schema.get("required", [])
        
        # Check required fields
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate field types
        for field_name, value in data.items():
            if field_name in properties:
                expected_type = properties[field_name].get("type")
                if expected_type in STRING_FIELD_TYPES and not isinstance(value, str):
                    raise ValueError(f"Field '{field_name}' must be a string")
                elif expected_type == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
                    raise ValueError(f"Field '{field_name}' must be a number")
                elif expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                    raise ValueError(f"Field '{field_name}' must be an integer")
                elif expected_type == "boolean" and not isinstance(value, bool):
                    raise ValueError(f"Field '{field_name}' must be a boolean")


# Singleton instance
form_service = FormService()
