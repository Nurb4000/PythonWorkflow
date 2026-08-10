"""
Pydantic schemas for CMDB — CI Types, Configuration Items, and Relationships.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List
from datetime import datetime
import re


# --- Field Schema Entry ---
class FieldSchemaEntry(BaseModel):
    key: str = Field(..., min_length=1, max_length=100)
    label: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., description="Field type: string, text, number, boolean, date, datetime, select, email, url, relationship")
    required: bool = False
    options: List[str] = []
    validation: Optional[str] = None
    help_text: Optional[str] = None


ALLOWED_FIELD_TYPES = {"string", "text", "number", "boolean", "date", "datetime", "select", "email", "url", "relationship"}


# --- CI Type Schemas ---
class CITypeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    key: Optional[str] = None
    description: str = ""
    icon: str = ""
    field_schema: List[FieldSchemaEntry] = []

    @field_validator("key")
    @classmethod
    def default_key_from_name(cls, v, info):
        if v is None:
            return None
        return re.sub(r'[^a-z0-9_]', '', v.lower().replace(' ', '_'))

    @field_validator("icon")
    @classmethod
    def limit_icon_length(cls, v):
        return v[:50] if v else ""


class CITypeUpdate(BaseModel):
    name: Optional[str] = None
    key: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    field_schema: Optional[List[FieldSchemaEntry]] = None
    is_active: Optional[bool] = None


class CITypeResponse(BaseModel):
    id: int
    name: str
    key: str
    description: str
    icon: str
    field_schema: List[Dict[str, Any]] = []
    is_active: bool
    item_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- Configuration Item Schemas ---
class CICreate(BaseModel):
    type_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=255)
    status: str = "active"
    ci_data: Dict[str, Any] = {}
    custom_data: Dict[str, Any] = {}


class CIUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    ci_data: Optional[Dict[str, Any]] = None
    custom_data: Optional[Dict[str, Any]] = None


class CIResponse(BaseModel):
    id: int
    type_id: int
    name: str
    status: str
    ci_data: Dict[str, Any] = {}
    custom_data: Dict[str, Any] = {}
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CITypeDetailResponse(BaseModel):
    """CI response that includes the parent type info."""
    id: int
    type_id: int
    name: str
    status: str
    ci_data: Dict[str, Any] = {}
    custom_data: Dict[str, Any] = {}
    type_name: str = ""
    type_key: str = ""
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime


# --- Relationship Schemas ---
class CIRelationshipCreate(BaseModel):
    source_ci_id: int = Field(..., gt=0)
    target_ci_id: int = Field(..., gt=0)
    relationship_type: str = Field(..., min_length=1, max_length=50)
    description: str = ""


class CIRelationshipResponse(BaseModel):
    id: int
    source_ci_id: int
    target_ci_id: int
    relationship_type: str
    description: str
    source_name: str = ""
    target_name: str = ""
    created_at: datetime

    class Config:
        from_attributes = True


# --- Bulk Import ---
class CIBulkImportRecord(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    status: str = "active"
    ci_data: Dict[str, Any] = {}


class CIBulkImportRequest(BaseModel):
    type_key: str = Field(..., min_length=1)
    records: List[CIBulkImportRecord] = Field(..., min_length=1)
    upsert_key: Optional[str] = None
    dry_run: bool = False


# --- History Schemas ---
class CIHistoryEntry(BaseModel):
    id: int
    ci_id: int
    changed_by: Optional[int] = None
    changed_at: datetime
    field_key: Optional[str] = None
    old_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None
    change_type: str

    class Config:
        from_attributes = True


# --- Stats Schema ---
class CMDBStatsResponse(BaseModel):
    total_types: int = 0
    total_items: int = 0
    items_by_status: Dict[str, int] = {}
    items_by_type: List[Dict[str, Any]] = []
    recent_changes: int = 0
