"""
Regression test for findings #5: ``add_user_to_group`` had no ``@router``
decorator, so it was never registered as an API route (dead code). Admins could
not add users to groups; membership could only be set via ``set_user_groups``.

The fix adds ``@router.post("/auth/groups/{group_id}/users/{user_id}")`` (matching
the ``remove_user_from_group`` DELETE route). This test asserts the route is now
registered and that the endpoint forwards to ``auth_service.add_user_to_group``.
"""
import pytest

from app.api.auth import router, add_user_to_group


def test_add_user_to_group_route_is_registered():
    """POST /auth/groups/{group_id}/users/{user_id} must be a registered route."""
    matched = [
        (r.path, sorted(r.methods))
        for r in router.routes
        if r.path == "/auth/groups/{group_id}/users/{user_id}"
    ]
    paths = {p for p, _ in matched}
    methods = set()
    for _, m in matched:
        methods.update(m)
    # The DELETE (remove) and POST (add) routes share the same path.
    assert "/auth/groups/{group_id}/users/{user_id}" in paths
    assert "POST" in methods
    assert "DELETE" in methods


@pytest.mark.asyncio
async def test_add_user_to_group_forwards_to_service(monkeypatch):
    """The endpoint must call auth_service.add_user_to_group and return success."""
    called = {}

    async def fake_add_user_to_group(db, user_id, group_id):
        called.update(user_id=user_id, group_id=group_id)

    from app.api import auth
    monkeypatch.setattr(auth.auth_service, "add_user_to_group", fake_add_user_to_group)

    result = await add_user_to_group(
        group_id=7, user_id=3, admin_user=None, db=None
    )
    assert called == {"user_id": 3, "group_id": 7}
    assert result == {"message": "User 3 added to group 7"}
