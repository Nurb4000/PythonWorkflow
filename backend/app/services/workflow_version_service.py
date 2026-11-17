"""Workflow version snapshots (Feature-Plan §2.4).

Each successful create/save captures a point-in-time snapshot of a workflow's
definition so versions can be listed, inspected, and restored. The full
definition (name/description/config/tags + serialized steps) is stored as JSON;
step *connections* live inside each step's ``definition`` JSON, so serializing the
steps preserves the graph.

Design notes:
- Snapshots are tagged with ``Workflow.version`` at capture time, so every version
  (including the latest) has an inspectable/restore-able definition.
- Serialization is intentionally defensive (``or {}`` / ``or []``) so a snapshot
  is always valid JSON even if a field was later changed on the model.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import Workflow, WorkflowStep, WorkflowVersion


def _serialize_steps(steps) -> List[Dict[str, Any]]:
    return [
        {
            "step_type": s.step_type,
            "title": s.title,
            "definition": s.definition or {},
            "position": s.position,
            "condition_expr": s.condition_expr,
            "is_enabled": s.is_enabled,
            "description": s.description,
            "max_retries": s.max_retries,
            "retry_delay_seconds": s.retry_delay_seconds,
            "failure_hook_url": s.failure_hook_url,
        }
        for s in steps
    ]


def build_snapshot(workflow: Workflow, steps) -> Dict[str, Any]:
    """Build the JSON snapshot stored on a WorkflowVersion row."""
    return {
        "name": workflow.name,
        "description": workflow.description or "",
        "config": workflow.config or {},
        "tags": workflow.tags or [],
        "entry_form_id": workflow.entry_form_id,
        "service_id": workflow.service_id,
        "environment": workflow.environment,
        "steps": _serialize_steps(steps),
    }


async def _steps_for(db: AsyncSession, workflow_id: int):
    stmt = select(WorkflowStep).where(
        WorkflowStep.workflow_id == workflow_id
    ).order_by(WorkflowStep.position)
    return (await db.execute(stmt)).scalars().all()


async def snapshot_workflow(
    db: AsyncSession,
    workflow: Workflow,
    version_number: int,
    label: str = "",
    created_by: Optional[int] = None,
) -> WorkflowVersion:
    """Persist a snapshot of ``workflow``'s current definition as ``version_number``."""
    steps = await _steps_for(db, workflow.id)
    row = WorkflowVersion(
        workflow_id=workflow.id,
        version_number=version_number,
        label=label or "",
        snapshot=build_snapshot(workflow, steps),
        created_by=created_by,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()
    return row


async def list_versions(db: AsyncSession, workflow_id: int) -> List[Dict[str, Any]]:
    """Version metadata (newest first) -- no payload, for the history list UI."""
    rows = (
        await db.execute(
            select(WorkflowVersion).where(
                WorkflowVersion.workflow_id == workflow_id
            ).order_by(WorkflowVersion.version_number.desc())
        )
    ).scalars().all()
    out = []
    for r in rows:
        steps = (r.snapshot or {}).get("steps", [])
        out.append({
            "id": r.id,
            "version_number": r.version_number,
            "label": r.label,
            "step_count": len(steps),
            "created_by": r.created_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return out


async def get_version(db: AsyncSession, version_id: int) -> Optional[WorkflowVersion]:
    return await db.get(WorkflowVersion, version_id)


async def restore_version(
    db: AsyncSession,
    workflow_id: int,
    version_id: int,
    created_by: Optional[int] = None,
) -> Optional[Workflow]:
    """Revert a workflow to an earlier snapshot, capturing the result as a new version.

    Returns the updated ``Workflow`` (with steps reloaded), or ``None`` if the
    version/workflow does not exist or belongs to a different workflow.
    """
    row = await db.get(WorkflowVersion, version_id)
    if row is None or row.workflow_id != workflow_id:
        return None
    if not isinstance(row.snapshot, dict):
        return None

    workflow = await db.get(Workflow, workflow_id)
    if workflow is None:
        return None

    snap = row.snapshot
    workflow.name = snap.get("name", workflow.name)
    workflow.description = snap.get("description", workflow.description)
    workflow.config = snap.get("config", workflow.config)
    workflow.tags = snap.get("tags", workflow.tags)
    workflow.entry_form_id = snap.get("entry_form_id", workflow.entry_form_id)
    workflow.service_id = snap.get("service_id", workflow.service_id)

    # Replace steps with the snapshot's steps (connections are inside each definition).
    existing = await _steps_for(db, workflow_id)
    for step in existing:
        await db.delete(step)
    for i, sd in enumerate(snap.get("steps", [])):
        db.add(WorkflowStep(
            workflow_id=workflow_id,
            step_type=sd["step_type"],
            definition=sd.get("definition", {}),
            position=i,
            condition_expr=sd.get("condition_expr", ""),
            is_enabled=sd.get("is_enabled", True),
            title=sd.get("title", ""),
            description=sd.get("description", ""),
            max_retries=sd.get("max_retries", 0),
            retry_delay_seconds=sd.get("retry_delay_seconds", 0),
            failure_hook_url=sd.get("failure_hook_url", ""),
        ))

    workflow.version += 1
    await db.commit()
    await snapshot_workflow(
        db, workflow, workflow.version,
        label=f"Restored from v{row.version_number}", created_by=created_by,
    )
    await db.refresh(workflow, attribute_names=["steps"])
    return workflow
