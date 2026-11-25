"""
Regression tests pinning README.md documented facts to code reality.

These guard the two Feature-Plan documentation items so the README can't silently drift
from what the code actually does:

Item 1 -- documented facts vs. reality:
- The executor count in the "Executors (N types)" header equals the number of concrete
  executor classes in step_executors.py.
- The admin bootstrap-credential flow is documented (random token_urlsafe password +
  `scripts/setup_admin.py --show`) and the weak default `admin123` is not advertised.
- Rate limiting / brute-force protection is documented as shipped, not merely "pending".

Item 2 -- implemented-but-previously-undocumented features are now documented, and every
HTTP path documented in the README's endpoint code blocks resolves to a real route
(method + path), so docs can't point at endpoints that don't exist.

Design notes:
- Route discovery reads the authoritative route table off the running FastAPI app
  (``app.main.app``), so each router's own mount prefix is respected -- including files
  that mount several routers. It falls back to parsing the ``@<router>.<method>``
  decorators + effective prefixes when the app can't be imported. No live PostgreSQL is
  needed; importing the app does not open a connection.
- Trailing slashes are normalized: Starlette registers a ``/`` route under a prefix as
  ``"/prefix/"`` and redirects ``"/prefix"`` -> ``"/prefix/"``, so both spellings reach it.
"""
import os
import re
from pathlib import Path

# Any non-default value clears config's SECRET_KEY validation at import time, so the app
# can be imported in a bare environment (the suite normally provides one via conftest).
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-readme-consistency")

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"
API_DIR = REPO_ROOT / "backend" / "app" / "api"
MAIN = REPO_ROOT / "backend" / "app" / "main.py"
STEP_EXECUTORS = REPO_ROOT / "backend" / "app" / "services" / "step_executors.py"

# Endpoint code blocks introduced for the previously-undocumented feature areas.
NEW_FEATURE_HEADERS = [
    "Field Library",
    "Where-Used (Admin)",
    "SQL Views",
    "Data Explorer & Data Fields",
    "LDAP",
    "Search, Lookup & Audit APIs",
    "Data Export",
    "Reports",
    "Roles & Field-Level Permissions",
    "Bulk Operations",
    "Branding & Portal Customization",
    "SLA / OLA Analytics",
    "Admin Diagnostics & Lifecycle",
    "CMDB Extras",
]

# Representative real endpoints for those features, used as a presence spot-check.
FEATURE_ENDPOINTS = [
    "/field-library/migration-plan",
    "/admin/where-used/forms/{field_key}",
    "/sql-views",
    "/data-query/build",
    "/admin/ldap/sync",
    "/lookup/users",
    "/audit/user/{user_id}",
    "/data-export/query",
    "/reports",
    "/admin/role-permissions/visible-fields/{table_name}",
    "/bulk/workflows/deprecate",
    "/settings/priority-matrix",
    "/admin/hygiene-report",
    "/ai/generate-workflow",
    "/cmdb/templates",
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _readme() -> str:
    assert README.is_file(), f"README not found at {README}"
    return README.read_text(encoding="utf-8")


def _effective_prefixes():
    inline = {}
    for f in API_DIR.glob("*.py"):
        m = re.search(r'router\s*=\s*APIRouter\([^)]*prefix\s*=\s*["\']([^"\']+)["\']', f.read_text())
        inline[f.stem] = m.group(1) if m else ""
    include = {}
    msrc = MAIN.read_text()
    for m in re.finditer(
        r'include_router\(\s*(\w+)\.router[^)]*prefix\s*=\s*["\']([^"\']+)["\']', msrc
    ):
        include[m.group(1)] = m.group(2)
    return inline, include


def _route_index(lenient=False):
    """Map normalized_path -> set of supported methods (lowercase) for the real app.

    Uses the authoritative route table from the running FastAPI app so each router's own
    mount prefix is respected (including files that mount several routers, e.g.
    ``workflow_runs``). Falls back to parsing the ``@<router>.<method>`` decorators +
    effective prefixes when the app can't be imported in this environment.
    """
    norm = _lenient if lenient else _normalize
    index = {}

    def _add(path, methods):
        if path and str(path).startswith("/"):
            index.setdefault(norm(path), set()).update(m.lower() for m in (methods or []))

    try:
        import os
        # Any non-default value clears config's SECRET_KEY validation at import time.
        os.environ.setdefault("SECRET_KEY", "test-secret-key-for-readme-consistency")
        from app.main import app
        for r in app.routes:
            if type(r).__name__ == "_IncludedRouter":
                # The mount prefix lives on the include context, not the wrapper itself.
                ctx = getattr(r, "include_context", None)
                prefix = getattr(ctx, "prefix", None) or ""
                orig = getattr(r, "original_router", None)
                if orig is not None:
                    for sub in getattr(orig, "routes", []) or []:
                        _add(prefix + getattr(sub, "path", ""), getattr(sub, "methods", None))
            elif hasattr(r, "path") and str(getattr(r, "path", "")).startswith("/"):
                _add(r.path, getattr(r, "methods", None))
        if index:
            return index
    except Exception:
        pass

    # Fallback: parse decorators + effective prefixes from source.
    inline, include = _effective_prefixes()
    pat = re.compile(r'@router\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']', re.I)
    for f in API_DIR.glob("*.py"):
        prefix = inline.get(f.stem, "") + include.get(f.stem, "")
        for method, path in pat.findall(f.read_text()):
            _add(prefix + path, [method])
    return index


def _concrete_executor_count() -> int:
    src = STEP_EXECUTORS.read_text()
    classes = re.findall(r"^class (\w*Executor)\(", src, flags=re.MULTILINE)
    return len([c for c in classes if c != "BaseExecutor"])


def _normalize(path: str) -> str:
    return path.split("#")[0].strip().rstrip("/")


def _collect_documented(headers, norm):
    """Map normalized_path -> set of methods (lowercase) documented in README code blocks.

    If ``headers`` is None, every code block counts; otherwise only blocks under one of the
    given ``### `` headers.
    """
    paths = {}

    def _scan(lines):
        for line in lines:
            m = re.match(r"\s*(GET|POST|PUT|DELETE|PATCH)\s+(\S+)", line, re.I)
            if m:
                paths.setdefault(norm(m.group(2)), set()).add(m.group(1).lower())

    text = _readme()
    if headers is None:
        _scan(text.splitlines())
    else:
        current = None
        for line in text.splitlines():
            h = re.match(r"^###\s+(.+)$", line.strip())
            if h:
                current = h.group(1)
            if current in headers:
                _scan([line])
    return paths


def _lenient(path: str) -> str:
    """Strip comment, collapse path params (``{x}``/``:x`` -> ``{}``), and trailing slash."""
    path = path.split("#")[0].strip()
    path = re.sub(r"\{[^}]+\}", "{}", path)
    path = re.sub(r":[A-Za-z_]\w*", "{}", path)
    return path.rstrip("/")


def _documented_all(lenient=False):
    """Map normalized_path -> set of methods for every path in every README code block."""
    return _collect_documented(None, _lenient if lenient else _normalize)


# --------------------------------------------------------------------------- #
# Item 1 -- documented facts vs. reality
# --------------------------------------------------------------------------- #
def test_readme_executor_count_matches_code():
    n = _concrete_executor_count()
    readme = _readme()
    assert f"Executors ({n} types)" in readme, (
        f"README should state 'Executors ({n} types)' to match {n} concrete executor classes"
    )


def test_readme_has_no_weak_default_admin_password():
    readme = _readme()
    assert "admin123" not in readme, (
        "README still advertises the weak default admin/admin123 password"
    )


def test_readme_documents_admin_bootstrap_flow():
    readme = _readme()
    assert "token_urlsafe" in readme, "README should document the random bootstrap password"
    assert "setup_admin.py --show" in readme, (
        "README should document retrieving the bootstrap password via setup_admin.py --show"
    )


def test_readme_documents_rate_limiting_as_shipped():
    readme = _readme()
    low = readme.lower()
    assert "rate limit" in low or "brute-force" in low, "README should mention rate limiting"
    # At least one line describes it as shipped (the Next Steps / P7 line).
    assert any(
        ("rate limit" in l.lower() or "brute-force" in l.lower()) and "shipped" in l
        for l in readme.splitlines()
    ), "README should state rate limiting is shipped"
    # The Security section should list it (P7 cross-references it).
    security = readme.split("### Security", 1)[1].split("### Marketplace", 1)[0]
    assert "rate limit" in security.lower() or "brute-force" in security.lower(), (
        "Security section should document rate limiting / brute-force protection"
    )


# --------------------------------------------------------------------------- #
# Item 2 -- undocumented features documented + documented paths exist
# --------------------------------------------------------------------------- #
def test_new_feature_endpoint_paths_all_exist():
    """Every path documented under the newly-documented feature headers resolves to a real route.

    Path *parameter names* are compared exactly (so ``{table_name}`` != ``{table}``); only
    trailing slashes are normalized, since Starlette registers a ``/`` route under a prefix as
    ``"/prefix/"`` and redirects ``"/prefix"`` -> ``"/prefix/"``. A documented verb must be among
    the route's supported methods.
    """
    index = _route_index(lenient=False)
    documented = _collect_documented(NEW_FEATURE_HEADERS, _normalize)
    assert documented, "expected documented paths in the new feature sections"
    missing = sorted(
        f"{m} {p}"
        for p, methods in documented.items()
        for m in methods
        if m not in index.get(p, set())
    )
    assert not missing, f"documented endpoints with no matching route: {missing}"


def test_all_readme_endpoint_paths_exist():
    """Every documented endpoint anywhere in the README resolves to a real route.

    Path *parameter names* are collapsed to a wildcard so pre-existing shorthand (``{id}``,
    ``:id``) still matches the real ``{workflow_id}``-style names, and trailing slashes are
    normalized (Starlette redirects ``/prefix`` -> ``/prefix/``). Param-name *specificity*
    (e.g. ``{table}`` vs ``{table_name}``) is enforced separately in
    ``test_new_feature_endpoint_paths_all_exist``.
    """
    index = _route_index(lenient=True)
    documented = _documented_all(lenient=True)
    missing = sorted(
        f"{m} {p}"
        for p, methods in documented.items()
        for m in methods
        if m not in index.get(p, set())
    )
    assert not missing, f"documented endpoints with no matching route: {missing}"


def test_previously_undocumented_features_are_documented():
    readme = _readme()
    for marker in [
        "Field Library",
        "SQL Views",
        "LDAP",
        "Search, Lookup & Audit",
        "Data Export",
        "Reports",
        "Roles & Field-Level Permissions",
        "Bulk Operations",
        "Branding & Portal Customization",
        "Admin Diagnostics & Lifecycle",
        "CMDB Extras",
    ]:
        assert marker in readme, f"README should document the {marker!r} feature area"


def test_feature_endpoints_present():
    readme = _readme()
    for ep in FEATURE_ENDPOINTS:
        assert ep in readme, f"README should document endpoint {ep}"
