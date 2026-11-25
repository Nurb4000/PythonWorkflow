"""
Regression test for findings #36: ``resolve_project_root()`` must prefer a
*populated* knowledge-base over a stray empty one.

In a dev checkout a stray *empty* ``backend/knowledge-base/`` can shadow the real
repo-root ``knowledge-base/``. The resolver walks up from ``app/core`` and must
skip empty knowledge-base dirs, returning the closest *populated* one — otherwise
``template_service`` and ``ai_service`` silently load zero templates / KB prompts
(no error), which is exactly what broke ``test_step_templates_loaded``,
``test_step_template_by_type`` and ``test_template_service_loads_real_json``.
"""
import json
from pathlib import Path

import app.core.config as config


def _seed_populated_kb(root: Path) -> Path:
    """Create a populated repo-root-style knowledge-base with a templates/ dir."""
    templates = root / "knowledge-base" / "templates"
    templates.mkdir(parents=True, exist_ok=True)
    (templates / "demo.json").write_text(
        json.dumps({"name": "demo", "steps": [{"step_type": "delay", "definition": {}}]})
    )
    return root


def _make_app_core_with_stray_empty_kb(tmp_path: Path) -> Path:
    """Simulate <root>/app/core containing a stray EMPTY knowledge-base."""
    app_core = tmp_path / "app" / "core"
    app_core.mkdir(parents=True)
    (app_core / "knowledge-base").mkdir()  # stray empty kb, like backend/knowledge-base
    fake_config = app_core / "config.py"
    fake_config.write_text("")
    return fake_config


def test_resolve_prefers_populated_knowledge_base(tmp_path, monkeypatch):
    _make_app_core_with_stray_empty_kb(tmp_path)
    _seed_populated_kb(tmp_path)

    fake_config = tmp_path / "app" / "core" / "config.py"
    monkeypatch.setattr(config, "__file__", str(fake_config))

    from app.core.config import resolve_project_root

    # Must skip the empty backend/knowledge-base and return the repo root that
    # holds the populated knowledge-base/templates.
    assert resolve_project_root() == tmp_path


def test_resolve_falls_back_to_closest_when_none_populated(tmp_path, monkeypatch):
    app_core = tmp_path / "app" / "core"
    app_core.mkdir(parents=True)
    (app_core / "knowledge-base").mkdir()  # only an empty kb exists

    fake_config = app_core / "config.py"
    fake_config.write_text("")
    monkeypatch.setattr(config, "__file__", str(fake_config))

    from app.core.config import resolve_project_root

    # No populated kb: fall back to the closest dir that contains a knowledge-base
    # (the empty one at app/core/knowledge-base => app/core).
    assert resolve_project_root() == tmp_path / "app" / "core"


def test_template_service_loads_real_templates():
    """Symptom guard: the real repo templates must load (was 0 before the fix)."""
    from app.services.template_service import TemplateService

    ts = TemplateService()
    assert len(ts.get_templates()) >= 1
    assert ts.get_step_template("delay") is not None
