"""
Pydantic schemas for request/response validation
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


# Workflow Schemas
class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    steps: List[Dict[str, Any]] = []


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    steps: Optional[List[Dict[str, Any]]] = None


class WorkflowResponse(BaseModel):
    id: int
    name: str
    description: str
    version: int
    is_active: bool
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


# Workflow Run Schemas
class WorkflowRunCreate(BaseModel):
    input_data: Optional[Dict[str, Any]] = {}
    triggered_by: str = "manual"


class WorkflowRunResponse(BaseModel):
    id: int
    workflow_id: int
    status: str
    triggered_by: str
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    error_message: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class StepInstanceResponse(BaseModel):
    id: int
    workflow_run_id: int
    step_id: int
    status: str
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    error_message: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

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
