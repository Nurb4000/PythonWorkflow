"""
Pydantic schemas for request/response validation
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


# Step Schemas
class StepCreate(BaseModel):
    step_type: str
    definition: Dict[str, Any]
    position: int = 0
    condition_expr: str = ""
    is_enabled: bool = True


class StepResponse(BaseModel):
    id: int
    workflow_id: int
    step_type: str
    definition: Dict[str, Any]
    position: int
    condition_expr: str
    is_enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


# Workflow Schemas
class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    steps: List[Dict[str, Any]] = []
    config: Dict[str, Any] = {}
    allowed_group_ids: List[int] = []
    portal_icon: str = ""
    portal_order: int = 0
    portal_visible: bool = True
    entry_form_id: Optional[int] = None  # P3.3: form to show before triggering


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    is_published: Optional[bool] = None
    environment: Optional[str] = None
    steps: Optional[List[Dict[str, Any]]] = None
    config: Optional[Dict[str, Any]] = None
    portal_icon: Optional[str] = None
    portal_order: Optional[int] = None
    portal_visible: Optional[bool] = None
    portal_link_url: Optional[str] = None
    entry_form_id: Optional[int] = None  # P3.3
    service_id: Optional[int] = None  # SERVICE_MANAGEMENT_PLAN Phase 1.4
    manual_version_increment: bool = False  # P7: Manual version bump


class WorkflowResponse(BaseModel):
    id: int
    name: str
    description: str
    version: int
    is_active: bool
    config: Dict[str, Any] = {}
    steps: List[StepResponse] = []
    portal_icon: str = ""
    portal_order: int = 0
    portal_visible: bool = True
    entry_form_id: Optional[int] = None  # P3.3
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkflowListResponse(BaseModel):
    id: int
    name: str
    description: str
    is_active: bool
    steps_count: int
    runs_count: int
    created_at: datetime

    class Config:
        from_attributes = True


# Workflow Run Schemas
class WorkflowRunCreate(BaseModel):
    input_data: Optional[Dict[str, Any]] = {}
    triggered_by: str = "manual"
    timeout_seconds: int = 0  # 0 means no timeout
    max_retries: int = 0  # Maximum retries per step
    failure_hooks: List[Dict[str, Any]] = []  # List of failure hook configurations
    priority: Optional[int] = None  # SERVICE_MANAGEMENT_PLAN Phase 3
    service_id: Optional[int] = None  # SERVICE_MANAGEMENT_PLAN Phase 4


class WorkflowRunResponse(BaseModel):
    id: int
    workflow_id: Optional[int] = None
    workflow_name: Optional[str] = None
    status: str
    triggered_by: str
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    error_message: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    timeout_seconds: int = 0
    max_retries: int = 0
    retry_count: int = 0
    failure_hooks: List[Dict[str, Any]] = []
    created_at: datetime

    class Config:
        from_attributes = True


class StepInstanceResponse(BaseModel):
    id: int
    workflow_run_id: int
    step_id: Optional[int] = None
    status: str
    step_type: str = ""
    title: str = ""
    description: str = ""
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    error_message: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[float] = None
    position: int = 0
    retry_count: int = 0
    max_retries: int = 0
    last_error: str = ""
    route_taken: List[int] = []
    custom_data: Dict[str, Any] = {}

    class Config:
        from_attributes = True


# Schedule Schemas
class ScheduleCreate(BaseModel):
    cron_expression: str
    is_enabled: bool = True


class ScheduleResponse(BaseModel):
    id: int
    workflow_id: int
    cron_expression: str
    is_enabled: bool
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# Admin/Report Schemas
class RunStatsResponse(BaseModel):
    total_runs: int
    completed_runs: int
    failed_runs: int
    average_duration_seconds: float
    last_run_at: Optional[datetime]


class AuditLogEntry(BaseModel):
    timestamp: datetime
    action: str
    user: str
    details: Dict[str, Any]


# Task Schemas
class TaskCreate(BaseModel):
    workflow_run_id: Optional[int] = None
    step_id: Optional[int] = None
    title: str
    description: Optional[str] = ""
    assigned_to_user_id: Optional[int] = None
    assigned_group_id: Optional[int] = None
    form_id: Optional[int] = None
    task_data: Dict[str, Any] = {}


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    assigned_to_user_id: Optional[int] = None
    assigned_group_id: Optional[int] = None
    form_id: Optional[int] = None
    task_data: Optional[Dict[str, Any]] = None
    result_data: Optional[Dict[str, Any]] = None


class TaskResponse(BaseModel):
    id: int
    workflow_run_id: Optional[int]
    step_id: Optional[int]
    title: str
    description: str
    status: str
    assigned_to_user_id: Optional[int]
    assigned_group_id: Optional[int]
    form_id: Optional[int]
    task_data: Dict[str, Any]
    result_data: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    closed_at: Optional[datetime]

    class Config:
        from_attributes = True
