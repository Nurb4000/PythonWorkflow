"""
Pydantic schemas for Service Management (SERVICE_MANAGEMENT_PLAN Phase 1)
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


# --- Category Schemas ---

class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    key: Optional[str] = None
    icon: str = ""
    description: str = ""
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    key: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class CategoryResponse(BaseModel):
    id: int
    name: str
    key: str
    icon: str
    description: str
    sort_order: int
    is_active: bool
    service_count: int = 0

    class Config:
        from_attributes = True


# --- Service Schemas ---

class ServiceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    key: Optional[str] = None
    description: str = ""
    icon: str = ""
    category_id: Optional[int] = None
    owner_id: Optional[int] = None
    support_group_id: Optional[int] = None
    sort_order: int = 0
    custom_data: Dict[str, Any] = {}


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    key: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    category_id: Optional[int] = None
    owner_id: Optional[int] = None
    support_group_id: Optional[int] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    custom_data: Optional[Dict[str, Any]] = None


class ServiceResponse(BaseModel):
    id: int
    name: str
    key: str
    description: str
    icon: str
    category_id: Optional[int]
    owner_id: Optional[int]
    support_group_id: Optional[int]
    is_active: bool
    sort_order: int
    custom_data: Dict[str, Any]
    workflow_count: int = 0

    class Config:
        from_attributes = True
