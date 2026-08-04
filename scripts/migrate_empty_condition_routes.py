"""
One-off data migration (P1.1): replace empty-expression condition routes.

Before P1.1, `_get_targets` treated a route with an empty `expression` as a
silent catch-all (always matches). P1.1 makes empty expressions an error, so any
condition step relying on an empty-expression route must be converted to
Model B semantics first.

The conversion is behavior-preserving:

- The FIRST empty route with a real `target_step_id` always matched, so every
  other route and the old default were unreachable. It becomes
  `default_target_step_id` and all routes are dropped.
- An empty route with `target_step_id: null` was a no-op in the old engine; it is
  dropped, keeping the existing `default_target_step_id`.

Run inside the backend container:
    docker compose exec backend python -m scripts.migrate_empty_condition_routes
"""
import asyncio
import logging

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.schemas import WorkflowStep

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migrate_empty_condition_routes")


def transform(step: WorkflowStep) -> bool:
    """Return True if the step was changed."""
    d = step.definition or {}
    routes = list(d.get("routes") or [])
    empty_targets = [r.get("target_step_id") for r in routes if not (r.get("expression") or "").strip()]
    if not empty_targets:
        return False
    first_real = next((t for t in empty_targets if t is not None), None)
    new_routes = [r for r in routes if (r.get("expression") or "").strip()]
    new_default = first_real if first_real is not None else d.get("default_target_step_id")
    step.definition = {**d, "routes": new_routes, "default_target_step_id": new_default}
    return True


async def main() -> None:
    async with async_session_factory() as db:
        steps = (await db.execute(select(WorkflowStep).where(WorkflowStep.step_type == "condition"))).scalars().all()
        changed = 0
        for step in steps:
            before = step.definition
            if transform(step):
                changed += 1
                logger.info("step %s (workflow %s): %s -> %s", step.id, step.workflow_id, before, step.definition)
        await db.commit()
        logger.info("migrated %d/%d condition steps", changed, len(steps))


if __name__ == "__main__":
    asyncio.run(main())
