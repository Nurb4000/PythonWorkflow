"""
Step executors for different workflow step types
"""
import asyncio
import logging
import re
from typing import Dict, Any, Optional
import httpx
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text as sa_text, select

logger = logging.getLogger(__name__)


def _is_safe_url(url: str, allow_loopback: bool = False) -> bool:
    """Check if URL is safe (not private/loopback).

    C4 fix: DNS-resolves hostnames and inspects all A/AAAA records.
    Blocks private, loopback, link-local, and reserved addresses.
    For literal IP hosts, checks directly without DNS.
    For hostname hosts, resolves via socket.getaddrinfo and validates each record.

    Args:
        url: The URL to check
        allow_loopback: If True, allow localhost/loopback URLs (for tests)
    """
    from urllib.parse import urlparse
    import ipaddress
    import socket

    parsed = urlparse(url)
    host = parsed.hostname

    if not host:
        return False

    # Block localhost/loopback hostnames (unless explicitly allowed)
    loopback_hosts = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
    if host.lower() in loopback_hosts:
        return allow_loopback

    # Try parsing as a literal IP address first
    try:
        ip = ipaddress.ip_address(host)
        if _is_private_ip(ip):
            return allow_loopback  # treat private IPs like loopback when flag is set
        return True  # public IP
    except ValueError:
        pass  # not a literal IP — resolve via DNS

    # DNS resolution: check all A/AAAA records
    try:
        addr_infos = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except (socket.gaierror, socket.timeout):
        logger.info(f"SSRF check: hostname {host!r} failed DNS resolution — blocked")
        return False

    for info in addr_infos:
        ip_str = info[4][0]  # address tuple (ip, port, ...)
        try:
            ip = ipaddress.ip_address(ip_str)
            if _is_private_ip(ip):
                logger.info(f"SSRF check: {host!r} resolved to private IP {ip_str} — blocked")
                return False
        except ValueError:
            continue  # unexpected address format

    return True


def _is_private_ip(ip) -> bool:
    """Return True if the IP falls in a private, loopback, link-local, or reserved range."""
    import ipaddress
    if ip.is_loopback:
        return True
    if ip.is_private:
        return True
    if ip.is_reserved:
        return True
    if ip.is_link_local:
        return True
    return False


def _is_json_response(response) -> bool:
    """Check if response content-type indicates JSON (L6 fix).

    Handles both exact matches and MIME parameters like charset.
    """
    ct = (response.headers.get("content-type") or "").lower()
    return ct.startswith("application/json")


def _parse_cron_field(field: str, name: str, min_val: int, max_val: int) -> int:
    """Parse a single cron field into an integer value (L7 fix).

    Supports:
    - '*' → returns min_val (0)
    - Exact number → returns the number
    - '*/N' → returns 0 with a warning (step expressions not fully supported)
    - 'N-M' → returns N with a warning (range expressions not fully supported)

    Raises ValueError for invalid syntax.
    """
    if field == "*":
        return min_val
    try:
        val = int(field)
        if min_val <= val <= max_val:
            return val
        raise ValueError(
            f"Cron {name} field {val} out of range [{min_val}-{max_val}]"
        )
    except ValueError as e:
        if str(e).startswith("Cron"):
            raise
        # Handle step/range expressions with a warning
        if "/" in field or "-" in field:
            logger.warning(
                f"Cron {name} field {field!r} uses step/range syntax "
                f"(not fully supported); treating as 0. "
                f"Use exact values for reliable behavior."
            )
            return min_val
        raise ValueError(f"Invalid cron {name} field: {field!r}") from e


class BaseExecutor:
    """Base class for step executors"""

    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        raise NotImplementedError


class APICallExecutor(BaseExecutor):
    """Execute HTTP API calls with SSRF protection (P6.1)."""

    def _is_safe_url(self, url: str, allow_loopback: bool = False) -> bool:
        """Check if URL is safe (not private/loopback) for SSRF protection.

        This method delegates to the module-level _is_safe_url function so that
        tests can patch it via patch.object(APICallExecutor, '_is_safe_url').
        """
        return _is_safe_url(url, allow_loopback=allow_loopback)

    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        method = step_definition.get("method", "GET").upper()
        url = step_definition.get("url", "")
        headers = step_definition.get("headers", {})
        body = step_definition.get("body")
        
        # P6.1: SSRF protection - block private/loopback URLs
        if not self._is_safe_url(url):
            raise ValueError(f"API call to private/loopback URL blocked for security: {url}")
        
        # Merge input data into request
        if "$input" in headers:
            headers.update(input_data)
        if body is not None and "$input" in body:
            body = input_data
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=body,
                    timeout=30.0
                )
                
                return {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response.json() if _is_json_response(response) else response.text,
                    "executed_at": datetime.utcnow().isoformat()
                }
            except Exception as e:
                logger.error(f"API call failed: {str(e)}")
                raise ValueError(f"API call failed: {str(e)}")


class DatabaseQueryExecutor(BaseExecutor):
    """Execute parameterized database queries safely (P2.2).
    
    Supports: select, insert, update, delete, upsert.
    All user input is parameterized — never string-interpolated into SQL.
    Also supports visual_query format from the QueryBuilder component.
    """
    
    ALLOWED_QUERY_TYPES = {"select", "insert", "update", "delete", "upsert"}
    
    def _interpolate_value(self, value: Any, input_data: Dict[str, Any]) -> Any:
        """Recursively interpolate $input.* references in values."""
        if isinstance(value, str) and value.startswith("$input."):
            field = value[7:]  # Remove "$input." prefix
            return input_data.get(field, value)
        elif isinstance(value, dict):
            return {k: self._interpolate_value(v, input_data) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._interpolate_value(item, input_data) for item in value]
        return value
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        # Check for visual_query format from QueryBuilder
        visual_query = step_definition.get("visual_query")
        if visual_query and isinstance(visual_query, dict):
            return await self._execute_visual_query(input_data, step_definition, visual_query, db)
        
        query_type = step_definition.get("type", "select").lower()
        
        if query_type not in self.ALLOWED_QUERY_TYPES:
            raise ValueError(f"Unsupported query type: {query_type}. Allowed: {self.ALLOWED_QUERY_TYPES}")
        
        table = step_definition.get("table")
        if not table:
            raise ValueError("Database query requires a 'table' name")
        
        # Validate table name (alphanumeric + underscore only)
        if not all(c.isalnum() or c == '_' for c in table):
            raise ValueError(f"Invalid table name: {table}")
        
        # Interpolate values from input_data
        data = self._interpolate_value(step_definition.get("data"), input_data)
        conditions = self._interpolate_value(step_definition.get("conditions"), input_data)
        
        # Build parameterized query (simulated for now — real impl would use asyncpg)
        param_idx = 1
        
        def next_param():
            nonlocal param_idx
            p = f"${param_idx}"
            param_idx += 1
            return p
        
        if query_type == "select":
            columns = step_definition.get("columns", "*")
            if columns == "*":
                sql = f"SELECT * FROM {table}"
            else:
                # Validate column names
                col_list = [c.strip() for c in columns.split(",")]
                for col in col_list:
                    if not all(c.isalnum() or c == '_' for c in col):
                        raise ValueError(f"Invalid column name: {col}")
                sql = f"SELECT {', '.join(col_list)} FROM {table}"
            
            if conditions:
                where_parts = []
                for k in conditions.keys():
                    where_parts.append(f"{k} = {next_param()}")
                sql += f" WHERE {' AND '.join(where_parts)}"
                params = list(conditions.values())
            else:
                params = []
        
        elif query_type == "insert":
            if not data or not isinstance(data, dict):
                raise ValueError("INSERT requires 'data' as a dict")
            columns = list(data.keys())
            for col in columns:
                if not all(c.isalnum() or c == '_' for c in col):
                    raise ValueError(f"Invalid column name: {col}")
            placeholders = ", ".join(next_param() for _ in columns)
            sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
            params = list(data.values())
        
        elif query_type == "update":
            if not data or not isinstance(data, dict):
                raise ValueError("UPDATE requires 'data' as a dict")
            if not conditions or not isinstance(conditions, dict):
                raise ValueError("UPDATE requires 'conditions' as a dict")
            
            set_parts = []
            for k in data.keys():
                set_parts.append(f"{k} = {next_param()}")
            where_parts = []
            for k in conditions.keys():
                where_parts.append(f"{k} = {next_param()}")
            sql = f"UPDATE {table} SET {', '.join(set_parts)} WHERE {' AND '.join(where_parts)}"
            params = list(data.values()) + list(conditions.values())
        
        elif query_type == "delete":
            if not conditions or not isinstance(conditions, dict):
                raise ValueError("DELETE requires 'conditions' as a dict")
            where_parts = []
            for k in conditions.keys():
                where_parts.append(f"{k} = {next_param()}")
            sql = f"DELETE FROM {table} WHERE {' AND '.join(where_parts)}"
            params = list(conditions.values())
        
        elif query_type == "upsert":
            # Simplified upsert: try insert, catch unique violation and update
            if not data or not isinstance(data, dict):
                raise ValueError("UPSERT requires 'data' as a dict")
            columns = list(data.keys())
            for col in columns:
                if not all(c.isalnum() or c == '_' for c in col):
                    raise ValueError(f"Invalid column name: {col}")
            placeholders = ", ".join(next_param() for _ in columns)
            set_clauses = ", ".join(f"{col} = EXCLUDED.{col}" for col in columns)
            sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) ON CONFLICT DO UPDATE SET {set_clauses}"
            params = list(data.values())

        # M14 fix: actually execute the parameterized query instead of returning
        # a simulated result.  Convert positional placeholders ($1, $2, ...) to
        # SQLAlchemy named parameters (:p1, :p2, ...). The bind *name* must be
        # colon-free (``bindparams(p1=...)``) — including the colon here (the old
        # ``":p{i}"`` key) made bindparams raise ArgumentError, so any real
        # parameterized DB query silently broke.
        named_sql = sql
        named_params: dict[str, Any] = {}
        for i, val in enumerate(params, 1):
            placeholder = f"${i}"
            named = f"p{i}"
            named_sql = named_sql.replace(placeholder, f":{named}")
            named_params[named] = val

        logger.info(f"DatabaseQueryExecutor: {named_sql} with {len(named_params)} params")

        if db is not None:
            bound = sa_text(named_sql).bindparams(**named_params)
            result = await db.execute(bound)
            rows_affected = result.rowcount if result.rowcount is not None else 0
        else:
            rows_affected = -1  # no session available

        return {
            "query_type": query_type,
            "table": table,
            "rows_affected": rows_affected,
            "executed_at": datetime.utcnow().isoformat(),
            "sql": named_sql,
            "params_count": len(named_params),
        }

    async def _execute_visual_query(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], visual_query: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        """Execute a visual query built with the QueryBuilder component.

        Delegates to shared query_executor service (Phase 4).
        """
        from app.core.database import async_session_factory
        from app.services.query_executor import execute_visual_query as run_visual

        table = visual_query.get("table", step_definition.get("table", ""))
        filters = visual_query.get("filters", [])
        logic = visual_query.get("logic", "AND")
        sort_by = visual_query.get("sortBy") or visual_query.get("sort_by")
        sort_order = visual_query.get("sortOrder", "desc")
        limit = min(visual_query.get("limit", 100), 10000)

        session = db
        if not session:
            session = async_session_factory()
            if hasattr(session, '__aenter__'):
                session = await session.__aenter__()

        try:
            result = await run_visual(
                session,
                table_name=table,
                raw_filters=filters,
                input_data=input_data,
                logic=logic,
                sort_by=sort_by,
                sort_order=sort_order,
                limit=limit,
                offset=0,
            )

            return {
                "query_type": "select",
                "table": table,
                "visual_query": True,
                "rows": result.get("items", []),
                "total": result.get("total", 0),
                "executed_at": datetime.utcnow().isoformat(),
            }
        finally:
            if not db and hasattr(session, 'close'):
                await session.close()


class EmailExecutor(BaseExecutor):
    """Send email notifications via SMTP (P2.1)."""
    
    def _interpolate(self, value: str, input_data: Dict[str, Any]) -> str:
        """Replace $input.field references with actual values from input_data."""
        if not isinstance(value, str) or "$input." not in value:
            return str(value)
        
        import re
        def replace_match(match):
            field = match.group(1)
            return str(input_data.get(field, match.group(0)))
        
        return re.sub(r'\$input\.(\w+)', replace_match, value)
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        to = self._interpolate(step_definition.get("to", ""), input_data)
        subject = self._interpolate(step_definition.get("subject", ""), input_data)
        body = self._interpolate(step_definition.get("body", ""), input_data)

        if not to:
            raise ValueError("Email step requires a 'to' recipient")

        # M11 fix: run blocking SMTP I/O in a thread pool so the async event
        # loop is not blocked for the duration of the SMTP transaction.
        from app.services.email_service import send_email
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: send_email(to=to, subject=subject, body=body)
        )

        if not result["sent"]:
            logger.warning(f"Email not sent to {to}: {subject} (SMTP not configured)")

        return result


class ConditionExecutor(BaseExecutor):
    """Evaluate conditions for branching"""
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        routes = step_definition.get("routes")
        expression = "True"
        if isinstance(routes, list) and routes:
            expression = (routes[0].get("expression") or "").strip() or "True"
        else:
            expression = (step_definition.get("expression") or "").strip() or "True"

        # C2 fix: use shared AST-based safe evaluator instead of raw eval
        from app.services.safe_eval import safe_eval, SafeEvalError
        try:
            result = safe_eval(expression, input_data)
            return {
                "condition_met": bool(result),
                "executed_at": datetime.utcnow().isoformat()
            }
        except SafeEvalError as e:
            raise ValueError(
                f"Condition evaluation failed for expression {expression!r}: {e}"
            ) from e
        except Exception as e:
            raise ValueError(
                f"Condition evaluation failed for expression {expression!r}: "
                f"{type(e).__name__}: {e}"
            )


class DelayExecutor(BaseExecutor):
    """Add a delay/sleep"""
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        seconds = step_definition.get("seconds", 0)
        
        if seconds > 0:
            await asyncio.sleep(seconds)
        
        return {
            "delayed_by": seconds,
            "executed_at": datetime.utcnow().isoformat()
        }


class FormExecutor(BaseExecutor):
    """Handle form collection steps (P2.3).
    
    Pulls the latest submission data for a form into the step output.
    If no submission exists, creates a new one from input_data.
    """
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        form_id = step_definition.get("form_id")
        if not form_id:
            raise ValueError("Form step requires a 'form_id'")
        
        # Try to get existing submission for this form
        from app.services.form_service import form_service
        from app.core.database import async_session_factory
        
        async with async_session_factory() as db:
            # Get the form
            form = await form_service.get_form(db, form_id)
            if not form:
                raise ValueError(f"Form {form_id} not found")
            
            # Get latest submission
            submissions = await form_service.get_submissions(db, form_id, limit=1)
            
            if submissions:
                # Use existing submission data
                submission = submissions[0]
                submission_data = submission.data or {}
            else:
                # Create new submission from input_data
                # Filter input_data to only include form fields
                schema = form.schema_json or {}
                properties = schema.get("properties", {})
                
                filtered_data = {}
                for field_name, field_def in properties.items():
                    if field_name in input_data:
                        value = input_data[field_name]
                        # Type coercion based on schema
                        expected_type = field_def.get("type", "string")
                        if expected_type == "number" and isinstance(value, (int, float)):
                            filtered_data[field_name] = float(value)
                        elif expected_type == "integer" and isinstance(value, int):
                            filtered_data[field_name] = value
                        elif expected_type == "boolean" and isinstance(value, bool):
                            filtered_data[field_name] = value
                        else:
                            filtered_data[field_name] = str(value) if value is not None else ""
                
                submission = await form_service.submit_form(db, form_id, filtered_data)
                submission_data = submission.data
        
        return {
            "form_id": form_id,
            "submission_id": submission.id,
            "data": submission_data,
            "status": "form_submitted",
            "executed_at": datetime.utcnow().isoformat(),
        }


class WebhookExecutor(BaseExecutor):
    """Handle webhook callbacks (P2.4).
    
    Makes an HTTP POST request to the configured URL with the input data as JSON.
    """
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        url = step_definition.get("url")
        if not url:
            raise ValueError("Webhook step requires a 'url'")

        # SSRF protection — block private/loopback URLs
        if not _is_safe_url(url):
            raise ValueError(f"Webhook to private/loopback URL blocked for security: {url}")

        method = step_definition.get("method", "POST").upper()
        headers = step_definition.get("headers", {"Content-Type": "application/json"})
        timeout = step_definition.get("timeout", 30)
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    json=input_data,
                    headers=headers,
                )
                
                return {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response.json() if _is_json_response(response) else response.text,
                    "executed_at": datetime.utcnow().isoformat(),
                }
            except Exception as e:
                logger.error(f"Webhook call to {url} failed: {str(e)}")
                raise ValueError(f"Webhook call failed: {str(e)}")


# ---------------------------------------------------------------------------
# C1 fix: Restricted namespace that blocks dangerous dunder attributes.
# Wraps every value returned from the sandbox so that attribute traversal
# (e.g. obj.__class__.__bases__) hits a gate before reaching the real object.
# ---------------------------------------------------------------------------

_DANGEROUS_ATTRS = frozenset({
    "__class__", "__bases__", "__subclasses__", "__mro__",
    "__globals__", "__closure__", "__code__", "__builtins__",
    "__dict__", "__getattribute__", "__setattr__", "__reduce__",
    "__reduce_ex__", "__setstate__", "__getstate__",
})


class _RestrictedProxy:
    """Wrap an object so that dangerous dunder attributes are blocked.

    Uses ``__getattribute__`` (not ``__getattr__``) so that *every* attribute
    access — including built-in dunders like ``__class__`` — passes through the
    gate before reaching the wrapped object.

    For ``isinstance`` / ``issubclass`` compatibility, ``__class__`` returns a
    synthetic class object whose ``__bases__`` and ``__subclasses__`` are also
    gated.
    """

    __slots__ = ("_obj",)

    def __init__(self, obj: Any):
        object.__setattr__(self, "_obj", obj)

    def __getattribute__(self, name: str) -> Any:
        # Let the proxy's own internal attributes pass through
        if name == "_obj":
            return object.__getattribute__(self, "_obj")
        # Proxy methods used by the sandbox's custom builtins
        if name in ("_getattr", "_hasattr", "_setattr"):
            return object.__getattribute__(self, name)
        if name == "__class__":
            # Return a synthetic class that preserves isinstance() but gates
            # further traversal (__bases__, __subclasses__).
            obj = object.__getattribute__(self, "_obj")
            return _SyntheticClass(type(obj))
        if name in _DANGEROUS_ATTRS:
            obj = object.__getattribute__(self, "_obj")
            raise AttributeError(
                f"'{type(obj).__name__}' sandbox attribute '{name}' blocked"
            )
        # Delegate to the wrapped object
        obj = object.__getattribute__(self, "_obj")
        val = getattr(obj, name)
        return _wrap(val)

    def __getitem__(self, key: Any) -> Any:
        obj = object.__getattribute__(self, "_obj")
        return _wrap(obj[key])

    def __iter__(self):
        obj = object.__getattribute__(self, "_obj")
        return (_wrap(item) for item in obj)

    def __len__(self) -> int:
        obj = object.__getattribute__(self, "_obj")
        return len(obj)

    def __bool__(self) -> bool:
        obj = object.__getattribute__(self, "_obj")
        return bool(obj)

    def __eq__(self, other: Any) -> bool:
        obj = object.__getattribute__(self, "_obj")
        return obj == _unwrap(other)

    def __ne__(self, other: Any) -> bool:
        obj = object.__getattribute__(self, "_obj")
        return obj != _unwrap(other)

    def __lt__(self, other: Any) -> bool:
        obj = object.__getattribute__(self, "_obj")
        return obj < _unwrap(other)

    def __le__(self, other: Any) -> bool:
        obj = object.__getattribute__(self, "_obj")
        return obj <= _unwrap(other)

    def __gt__(self, other: Any) -> bool:
        obj = object.__getattribute__(self, "_obj")
        return obj > _unwrap(other)

    def __ge__(self, other: Any) -> bool:
        obj = object.__getattribute__(self, "_obj")
        return obj >= _unwrap(other)

    def __contains__(self, item: Any) -> bool:
        obj = object.__getattribute__(self, "_obj")
        return item in obj

    def __add__(self, other: Any) -> Any:
        obj = object.__getattribute__(self, "_obj")
        return _wrap(obj + _unwrap(other))

    def __sub__(self, other: Any) -> Any:
        obj = object.__getattribute__(self, "_obj")
        return _wrap(obj - _unwrap(other))

    def __mul__(self, other: Any) -> Any:
        obj = object.__getattribute__(self, "_obj")
        return _wrap(obj * _unwrap(other))

    def __truediv__(self, other: Any) -> Any:
        obj = object.__getattribute__(self, "_obj")
        return _wrap(obj / _unwrap(other))

    def __mod__(self, other: Any) -> Any:
        obj = object.__getattribute__(self, "_obj")
        return _wrap(obj % _unwrap(other))

    def __str__(self) -> str:
        obj = object.__getattribute__(self, "_obj")
        return str(obj)

    def __repr__(self) -> str:
        obj = object.__getattribute__(self, "_obj")
        return repr(obj)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Allow calling proxied callables (e.g., bound methods like str.upper())."""
        obj = object.__getattribute__(self, "_obj")
        result = obj(*(_unwrap(a) for a in args), **{k: _unwrap(v) for k, v in kwargs.items()})
        return _wrap(result)

    # --- Custom getattr/hasattr/setattr that route through the proxy gate ---

    def _getattr(self, name: str, default: tuple) -> Any:
        """Called by the sandbox's builtins.getattr(obj, attr, default)."""
        if name in _DANGEROUS_ATTRS:
            if default:
                return _wrap(default[0])
            raise AttributeError(
                f"'{type(self._obj).__name__}' sandbox attribute '{name}' blocked"
            )
        val = getattr(self._obj, name, *default)
        return _wrap(val)

    def _hasattr(self, name: str) -> bool:
        """Called by the sandbox's builtins.hasattr(obj, attr)."""
        try:
            self._getattr(name, ())
            return True
        except AttributeError:
            return False

    def _setattr(self, name: str, value: Any) -> None:
        """Called by the sandbox's builtins.setattr(obj, attr, value)."""
        if name in _DANGEROUS_ATTRS:
            raise AttributeError(
                f"'{type(self._obj).__name__}' sandbox attribute '{name}' blocked"
            )
        setattr(self._obj, name, _unwrap(value))


class _SyntheticClass:
    """A lightweight class wrapper that preserves isinstance() but gates
    __bases__ / __subclasses__ / __mro__ traversal.

    Used as the return value for ``_RestrictedProxy.__class__`` so that
    ``isinstance(proxy, int)`` still works while blocking the classic
    ``().__class__.__bases__[0].__subclasses__()`` escape chain.
    """

    __slots__ = ("_real_cls",)

    def __init__(self, real_cls: type):
        object.__setattr__(self, "_real_cls", real_cls)

    def __getattribute__(self, name: str) -> Any:
        if name == "_real_cls":
            return object.__getattribute__(self, "_real_cls")
        real = object.__getattribute__(self, "_real_cls")
        if name in ("__bases__", "__subclasses__", "__mro__", "__mro_entries__"):
            raise AttributeError(
                f"sandbox attribute '{name}' blocked on {real.__name__}"
            )
        return getattr(real, name)

    def __instancecheck__(self, instance: Any) -> bool:
        real = object.__getattribute__(self, "_real_cls")
        # For isinstance(proxy, int): unwrap the proxy and check against real class
        if isinstance(instance, _RestrictedProxy):
            return isinstance(instance._obj, real)
        return isinstance(instance, real)

    def __subclasscheck__(self, subclass: type) -> bool:
        real = object.__getattribute__(self, "_real_cls")
        return issubclass(subclass, real)

    def __str__(self) -> str:
        real = object.__getattribute__(self, "_real_cls")
        return str(real)

    def __repr__(self) -> str:
        real = object.__getattribute__(self, "_real_cls")
        return repr(real)


def _wrap(obj: Any) -> Any:
    """Wrap an object in a RestrictedProxy.

    All values (including primitives) are wrapped so that attribute access
    on *any* sandbox value passes through the gate.
    """
    if obj is None:
        return obj  # None.__class__ is rarely useful; leave it bare
    return _RestrictedProxy(obj)


def _unwrap(obj: Any) -> Any:
    """Unwrap a RestrictedProxy to get the real object."""
    if isinstance(obj, _RestrictedProxy):
        return obj._obj
    return obj


def _sandbox_isinstance(obj: Any, cls_tuple: Any) -> bool:
    """isinstance that unwraps proxies before checking.

    Allows ``isinstance(proxy_wrapping_int, int)`` to return True.
    The class argument is also unwrapped so that ``isinstance(x, proxy_wrapping_int)``
    works when the class itself comes from the sandbox.
    """
    real_obj = _unwrap(obj)
    if isinstance(cls_tuple, _RestrictedProxy):
        cls_tuple = cls_tuple._obj
    # Handle single class or tuple of classes
    if isinstance(cls_tuple, tuple):
        cls_tuple = tuple(_unwrap(c) if isinstance(c, _RestrictedProxy) else c for c in cls_tuple)
    return isinstance(real_obj, cls_tuple)


class CustomCodeExecutor(BaseExecutor):
    """Execute custom Python code in a thread with timeout (P2.4).

    Trust boundary (C1 fix):
    - Code runs in a restricted namespace with only ``input_data`` and
      ``output`` available.
    - All values returned from the sandbox are wrapped in ``_RestrictedProxy``
      which blocks dangerous dunder attributes (``__class__``, ``__bases__``,
      ``__subclasses__``, ``__globals__``, etc.).
    - Builtins are restricted to a safe subset; ``getattr``/``hasattr``/
      ``setattr`` route through the proxy so dunder traversal is caught.
    - Execution is bounded by a timeout (default 30s, configurable via
      step_definition["timeout"]).
    - Code is run in a separate thread to prevent blocking the async event
      loop.
    """

    DEFAULT_TIMEOUT = 30

    def _run_code(self, code: str, input_data: Dict[str, Any], timeout: int) -> Dict[str, Any]:
        """Synchronous code execution in restricted namespace."""
        # Wrap input_data so that every value accessed by the user code is
        # proxied through _RestrictedProxy.
        wrapped_input = {k: _wrap(v) for k, v in (input_data or {}).items()}
        output_dict: Dict[str, Any] = {}
        local_vars = {"input_data": wrapped_input, "output": output_dict}

        # Restrict builtins to safe subset.  getattr/hasattr/setattr are
        # customised so they route through the proxy gate.
        safe_builtins: Dict[str, Any] = {
            "len": len,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
            "tuple": tuple,
            "set": set,
            "range": range,
            "enumerate": enumerate,
            "zip": zip,
            "map": map,
            "filter": filter,
            "sorted": sorted,
            "reversed": reversed,
            "min": min,
            "max": max,
            "sum": sum,
            "abs": abs,
            "round": round,
            "isinstance": _sandbox_isinstance,
            "issubclass": issubclass,
            # Custom getattr/hasattr/setattr that route through the proxy gate
            "getattr": lambda obj, attr, *default: _RestrictedProxy(obj)._getattr(attr, default),
            "hasattr": lambda obj, attr: _RestrictedProxy(obj)._hasattr(attr),
            "setattr": lambda obj, attr, value: _RestrictedProxy(obj)._setattr(attr, value),
            "print": print,
            "type": type,
            "repr": repr,
            "ord": ord,
            "chr": chr,
            "hex": hex,
            "oct": oct,
            "bin": bin,
            "pow": pow,
            "divmod": divmod,
            "any": any,
            "all": all,
            "iter": iter,
            "next": next,
            "callable": callable,
            # Exception classes
            "Exception": Exception,
            "ValueError": ValueError,
            "TypeError": TypeError,
            "KeyError": KeyError,
            "IndexError": IndexError,
            "RuntimeError": RuntimeError,
            "AttributeError": AttributeError,
            "ImportError": ImportError,
            "NameError": NameError,
            "ZeroDivisionError": ZeroDivisionError,
            "OverflowError": OverflowError,
            "FloatingPointError": FloatingPointError,
        }

        exec(code, {"__builtins__": safe_builtins}, local_vars)

        # Unwrap output values before returning
        return {k: _unwrap(v) for k, v in (output_dict or {}).items()}

    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        code = step_definition.get("code", "")
        if not code:
            raise ValueError("Custom code step requires 'code'")

        timeout = step_definition.get("timeout", self.DEFAULT_TIMEOUT)

        # Run in thread to avoid blocking event loop
        loop = asyncio.get_running_loop()
        try:
            output = await loop.run_in_executor(None, lambda: self._run_code(code, input_data, timeout))
        except Exception as e:
            raise ValueError(f"Custom code execution failed: {str(e)}")

        return {
            **output,
            "executed_at": datetime.utcnow().isoformat(),
        }


class CalculationExecutor(BaseExecutor):
    """Safe calculation executor using condition machinery (P5.1).
    
    Reuses the strict eval from P1 with a safe namespace.
    Expression is evaluated against `data` (step input).

    INCIDENT_CHANGE_PLAN Phase 0.4: When step_definition includes
    ``date_target_key``, the evaluated result is interpreted as an ISO
    datetime string and a ``DateTarget`` record is created so that
    calendar-based deadlines can be tracked independently of SLA/OLA.
    """
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        expression = step_definition.get("expression", "")
        if not expression:
            raise ValueError("Calculation step requires an 'expression'")

        # C2 fix: use shared AST-based safe evaluator instead of raw eval
        from app.services.safe_eval import safe_eval, SafeEvalError
        try:
            result = safe_eval(expression, input_data)
        except SafeEvalError as e:
            raise ValueError(f"Calculation failed for expression {expression!r}: {e}") from e
        except Exception as e:
            raise ValueError(f"Calculation failed for expression {expression!r}: {type(e).__name__}: {e}")

        output = {
            "result": result,
            "expression": expression,
            "executed_at": datetime.utcnow().isoformat(),
        }

        # Phase 0.4: create DateTarget when date_target_key is present
        date_target_key = step_definition.get("date_target_key")
        if date_target_key and db is not None:
            output["date_target_key"] = date_target_key
            output["date_target_created"] = await self._create_date_target(db, input_data, date_target_key, result)

        return output

    @staticmethod
    async def _create_date_target(db: AsyncSession, input_data: Dict[str, Any], target_key: str, result) -> int:
        """Persist a DateTarget record and return its ID."""
        from app.models.date_targets import DateTarget

        # Resolve workflow_run_id from input_data (set by engine at step execution)
        run_id = input_data.get("_workflow_run_id") or input_data.get("workflow_run_id")
        if not run_id:
            logger.warning(f"date_target_key '{target_key}' — no workflow_run_id in input_data, skipping creation")
            return -1

        # Phase 4.3: stamp the originating step so the run inspector can annotate its node
        step_ref = input_data.get("_workflow_step_id")
        try:
            step_id = int(step_ref) if step_ref is not None else None
        except (TypeError, ValueError):
            step_id = None

        # Parse the result as an ISO datetime
        try:
            if isinstance(result, str):
                target_dt = datetime.fromisoformat(result.replace("Z", "+00:00"))
            elif isinstance(result, datetime):
                target_dt = result
            else:
                logger.warning(f"date_target_key '{target_key}' — result is not a datetime string ({type(result).__name__}), skipping")
                return -1
        except (ValueError, TypeError) as e:
            logger.error(f"date_target_key '{target_key}' — failed to parse result as datetime: {e}")
            return -1

        target = DateTarget(
            workflow_run_id=int(run_id),
            step_id=step_id,
            target_key=target_key,
            target_datetime=target_dt,
            status="pending",
        )
        db.add(target)
        await db.flush()
        logger.info(f"Created DateTarget {target.id} for key '{target_key}' on run #{run_id}")
        return target.id


class ReportExecutor(BaseExecutor):
    """Render read-only report (P5.3), including SQL query execution.

    Delegates read operations to the shared query_executor service (Phase 4).
    Supports visual_query format from the QueryBuilder component (Phase 3).
    """

    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        report_type = step_definition.get("report_type", "table")
        title = step_definition.get("title", "Report")
        data_source_step_id = step_definition.get("data_source_step_id")

        # Phase 3: Check for visual_query format from QueryBuilder
        visual_query = step_definition.get("visual_query")
        if visual_query and isinstance(visual_query, dict):
            return await self._execute_visual_query(title, step_definition, visual_query, input_data, db)

        if report_type == "sql_query":
            return await self._execute_sql(title, step_definition, input_data, db)

        # In a real implementation, this would fetch data from the specified step
        # For now, return a placeholder
        return {
            "report_type": report_type,
            "title": title,
            "data_source_step_id": data_source_step_id,
            "rendered_html": f"<h2>{title}</h2><p>Report type: {report_type}</p>",
            "executed_at": datetime.utcnow().isoformat(),
        }

    async def _execute_visual_query(self, title: str, step_definition: Dict[str, Any], visual_query: Dict[str, Any], input_data: Dict[str, Any], db: Optional[AsyncSession]) -> Dict[str, Any]:
        """Execute a visual query via shared query_executor service (Phase 4)."""
        from app.core.database import async_session_factory
        from app.services.query_executor import execute_visual_query as run_visual

        table = visual_query.get("table", "")
        filters = visual_query.get("filters", [])
        logic = visual_query.get("logic", "AND")
        sort_by = visual_query.get("sortBy") or visual_query.get("sort_by")
        sort_order = visual_query.get("sortOrder", "desc")
        limit = min(visual_query.get("limit", 100) or step_definition.get("sql_limit", 100), 10000)

        session = db
        if not session:
            session = async_session_factory()
            if hasattr(session, '__aenter__'):
                session = await session.__aenter__()

        try:
            result = await run_visual(
                session,
                table_name=table,
                raw_filters=filters,
                input_data=input_data,
                logic=logic,
                sort_by=sort_by,
                sort_order=sort_order,
                limit=limit,
                offset=0,
            )

            return {
                "report_type": "sql_query",
                "title": title,
                "visual_query": True,
                "table": table,
                "columns": [],
                "rows": result.get("items", []),
                "row_count": result.get("total", 0),
                "limit": limit,
                "executed_at": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            return {
                "report_type": "sql_query",
                "title": title,
                "visual_query": True,
                "table": table,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "limit": limit,
                "error": str(e),
                "executed_at": datetime.utcnow().isoformat(),
            }
        finally:
            if not db and hasattr(session, 'close'):
                await session.close()

    async def _execute_sql(self, title: str, step_definition: Dict[str, Any], input_data: Dict[str, Any], db: Optional[AsyncSession]) -> Dict[str, Any]:
        """Execute raw SQL via shared query_executor service (Phase 4).

        C3 fix: delegates parameterization to execute_raw_sql which uses
        positional placeholders ($1, $2, ...) resolved by the DB driver.
        L8 fix: removed duplicate validate_readonly_sql call (execute_raw_sql validates internally).
        """
        from app.services.query_executor import execute_raw_sql

        sql = step_definition.get("sql_query", "").strip()
        limit = min(step_definition.get("sql_limit", 100), 10000)

        if not sql:
            raise ValueError("SQL query is required for sql_query report type")

        if db is None:
            return {
                "report_type": "sql_query",
                "title": title,
                "sql": sql,
                "limit": limit,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error": "Database session not available — query was validated but not executed",
                "executed_at": datetime.utcnow().isoformat(),
            }

        try:
            result = await execute_raw_sql(db, sql, input_data, max_rows=limit)
            return {
                "report_type": "sql_query",
                "title": title,
                "sql": sql,
                "limit": limit,
                "columns": result.get("columns", []),
                "rows": result.get("items", []),
                "row_count": result.get("total", 0),
                "executed_at": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            # L2: Raise consistently like other executors instead of returning error dict
            logger.error(f"SQL report query failed: {str(e)}")
            raise ValueError(f"SQL report query failed: {str(e)}") from e


class ReadonlyFormExecutor(BaseExecutor):
    """Render read-only form (P5.3)."""
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        form_id = step_definition.get("form_id")
        title = step_definition.get("title", "Form")
        
        return {
            "form_id": form_id,
            "title": title,
            "rendered_html": f"<h2>{title}</h2><p>Form ID: {form_id}</p>",
            "executed_at": datetime.utcnow().isoformat(),
        }


class AIConditionExecutor(BaseExecutor):
    """AI-generated condition node (P5.2).
    
    Uses the AI service to generate a condition expression based on user description.
    Falls back to a default expression if AI generation fails.
    """
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        description = step_definition.get("description", "")
        fallback_expression = step_definition.get("fallback_expression", "True")
        
        if not description:
            # No description, use fallback
            return await self._evaluate_expression(fallback_expression, input_data)
        
        try:
            # Try to use AI service to generate expression
            from app.services.ai_service import ai_service
            expression = await ai_service.generate_condition_expression(description, input_data)
            return await self._evaluate_expression(expression, input_data)
        except Exception as e:
            # AI service not available or failed, use fallback
            logger.warning(f"AI condition generation failed, using fallback: {e}")
            return await self._evaluate_expression(fallback_expression, input_data)
    
    async def _evaluate_expression(self, expression: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate an expression using the shared AST-based safe evaluator (C2 fix)."""
        from app.services.safe_eval import safe_eval, SafeEvalError
        try:
            result = safe_eval(expression, input_data)
            return {
                "condition_met": bool(result),
                "expression": expression,
                "executed_at": datetime.utcnow().isoformat(),
            }
        except SafeEvalError as e:
            raise ValueError(f"AI condition evaluation failed: {e}") from e
        except Exception as e:
            raise ValueError(f"AI condition evaluation failed: {str(e)}")


class ProgrammableDelayExecutor(BaseExecutor):
    """Programmable delay with SQL wait support (P5.5).
    
    Supports:
    - Simple seconds-based delay
    - SQL WAITFOR DELAY (SQL Server)
    - SQL SELECT SLEEP() (MySQL/PostgreSQL)
    - Cron-like expressions (basic)
    """
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        delay_type = step_definition.get("delay_type", "seconds")
        
        if delay_type == "seconds":
            seconds = step_definition.get("seconds", 0)
            if seconds > 0:
                await asyncio.sleep(seconds)
            return {
                "delayed_by": seconds,
                "delay_type": "seconds",
                "executed_at": datetime.utcnow().isoformat(),
            }
        
        elif delay_type == "sql_wait":
            # SQL WAITFOR DELAY or SELECT SLEEP
            sql_statement = step_definition.get("sql_statement", "SELECT SLEEP(1)")
            # In a real implementation, this would execute the SQL wait
            # For now, just return the statement
            return {
                "sql_statement": sql_statement,
                "delay_type": "sql_wait",
                "executed_at": datetime.utcnow().isoformat(),
            }
        
        elif delay_type == "cron":
            # Basic cron-like expression parsing
            cron_expr = step_definition.get("cron_expression", "")
            # Parse cron expression (simplified)
            parts = cron_expr.split()
            if len(parts) == 5:
                # minute hour day month day_of_week
                # L7 fix: validate cron fields and give clear error for unsupported syntax
                minutes = _parse_cron_field(parts[0], "minute", 0, 59)
                hours = _parse_cron_field(parts[1], "hour", 0, 23)
                delay_seconds = minutes * 60 + hours * 3600
                if delay_seconds > 0:
                    await asyncio.sleep(delay_seconds)
                return {
                    "delayed_by": delay_seconds,
                    "delay_type": "cron",
                    "cron_expression": cron_expr,
                    "executed_at": datetime.utcnow().isoformat(),
                }
            else:
                raise ValueError(
                    f"Cron expression must have 5 fields (minute hour day month day_of_week), "
                    f"got {len(parts)}: {cron_expr!r}"
                )
        
        else:
            raise ValueError(f"Unknown delay type: {delay_type}")


class CmdbLookupExecutor(BaseExecutor):
    """Look up CMDB configuration items by type and field criteria.

    step_definition:
      ci_type_id: int — the CI type to search within
      lookup_fields: list of {field_key, operator, value} — match criteria
        operators: =, !=, >, <, >=, <=, contains, starts_with, ends_with
        value can reference $input.* for dynamic lookups
      output_var: str — key name to store result under in output_data
      match_mode: "first" (default) or "all" — return first match or all matches
    """

    def _interpolate_value(self, value: Any, input_data: Dict[str, Any]) -> Any:
        if isinstance(value, str) and value.startswith("$input."):
            field = value[7:]
            return input_data.get(field, value)
        elif isinstance(value, dict):
            return {k: self._interpolate_value(v, input_data) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._interpolate_value(item, input_data) for item in value]
        return value

    def _match_field(self, ci_value: Any, operator: str, lookup_value: Any) -> bool:
        op = operator.lower().strip()
        if op == "=" or op == "eq":
            return str(ci_value) == str(lookup_value)
        elif op == "!=" or op == "neq":
            return str(ci_value) != str(lookup_value)
        elif op in (">", "gt"):
            try:
                return float(ci_value) > float(lookup_value)
            except (ValueError, TypeError):
                return str(ci_value) > str(lookup_value)
        elif op in ("<", "lt"):
            try:
                return float(ci_value) < float(lookup_value)
            except (ValueError, TypeError):
                return str(ci_value) < str(lookup_value)
        elif op in (">=", "gte"):
            try:
                return float(ci_value) >= float(lookup_value)
            except (ValueError, TypeError):
                return str(ci_value) >= str(lookup_value)
        elif op in ("<=", "lte"):
            try:
                return float(ci_value) <= float(lookup_value)
            except (ValueError, TypeError):
                return str(ci_value) <= str(lookup_value)
        elif op == "contains":
            return str(lookup_value).lower() in str(ci_value).lower()
        elif op == "starts_with":
            return str(ci_value).lower().startswith(str(lookup_value).lower())
        elif op == "ends_with":
            return str(ci_value).lower().endswith(str(lookup_value).lower())
        return str(ci_value) == str(lookup_value)

    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        if not db:
            raise ValueError("cmdb_lookup requires a database session")

        ci_type_id = step_definition.get("ci_type_id")
        if not ci_type_id:
            raise ValueError("cmdb_lookup requires ci_type_id in definition")

        lookup_fields = step_definition.get("lookup_fields", [])
        output_var = step_definition.get("output_var", "cmdb_result")
        match_mode = step_definition.get("match_mode", "first")

        from app.models.cmdb import ConfigurationItem, CIType

        # Verify type exists
        type_stmt = select(CIType).where(CIType.id == ci_type_id)
        type_result = await db.execute(type_stmt)
        ci_type = type_result.scalar_one_or_none()
        if not ci_type:
            raise ValueError(f"CI type with id {ci_type_id} not found")

        # M12 fix: for "first" match mode, limit the query to reduce memory usage.
        # For "all" mode with lookup_fields, we still load all items of the type
        # but apply a reasonable cap (10k) to prevent OOM on very large types.
        # TODO: push equality filters into SQL via JSONB operators for better perf.
        max_items = 1 if match_mode == "first" else 10000
        items_stmt = (
            select(ConfigurationItem)
            .where(ConfigurationItem.type_id == ci_type_id)
            .limit(max_items + 1)  # +1 to detect if we hit the cap
        )
        items_result = await db.execute(items_stmt)
        all_items = items_result.scalars().all()

        # Filter by lookup criteria
        matched = []
        for item in all_items:
            ci_data = item.ci_data or {}
            all_match = True
            for criterion in lookup_fields:
                field_key = criterion.get("field_key", "")
                operator = criterion.get("operator", "=")
                raw_value = criterion.get("value", "")
                lookup_value = self._interpolate_value(raw_value, input_data)

                ci_value = ci_data.get(field_key)
                if ci_value is None:
                    # Check item.name and status as fallback
                    if field_key == "name":
                        ci_value = item.name
                    elif field_key == "status":
                        ci_value = item.status
                    else:
                        all_match = False
                        break

                if not self._match_field(ci_value, operator, lookup_value):
                    all_match = False
                    break

            if all_match:
                matched.append({
                    "id": item.id,
                    "type_id": item.type_id,
                    "name": item.name,
                    "status": item.status,
                    "ci_data": item.ci_data or {},
                })
                # M12: early exit for "first" mode once we have a match
                if match_mode == "first":
                    break

        result = {
            "ci_type_name": ci_type.name,
            "ci_type_key": ci_type.key,
            "match_count": len(matched),
            "lookup_fields": lookup_fields,
            "executed_at": datetime.utcnow().isoformat(),
        }

        if match_mode == "all":
            result["items"] = matched
            result[output_var] = matched
        elif matched:
            single = matched[0]
            result["item"] = single
            result[output_var] = single
        else:
            result["items"] = []
            result[output_var] = None
            result["message"] = "No matching CIs found"

        return result


class CmdbUpdateExecutor(BaseExecutor):
    """Update a CMDB configuration item by ID or lookup.

    step_definition:
      ci_id: int or $input.* reference — direct CI id to update
      lookup_fields: list of {field_key, operator, value} — alternative: find CI by criteria
      updates: dict of field_key → new_value — fields to update in ci_data
      status: str — optional: update the CI's status field directly
      name: str — optional: update the CI's name
    """

    def _interpolate_value(self, value: Any, input_data: Dict[str, Any]) -> Any:
        if isinstance(value, str) and value.startswith("$input."):
            field = value[7:]
            return input_data.get(field, value)
        elif isinstance(value, dict):
            return {k: self._interpolate_value(v, input_data) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._interpolate_value(item, input_data) for item in value]
        return value

    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        if not db:
            raise ValueError("cmdb_update requires a database session")

        from app.models.cmdb import ConfigurationItem, CIType

        ci_id_raw = step_definition.get("ci_id")
        ci_id = self._interpolate_value(ci_id_raw, input_data)

        item = None

        # Direct ID lookup
        if ci_id is not None:
            try:
                ci_id_int = int(ci_id)
                stmt = select(ConfigurationItem).where(ConfigurationItem.id == ci_id_int)
                result = await db.execute(stmt)
                item = result.scalar_one_or_none()
            except (ValueError, TypeError):
                pass

        # Fallback: lookup by criteria
        if not item and step_definition.get("lookup_fields"):
            lookup_fields = step_definition["lookup_fields"]
            # Find the CI type from first lookup field or ci_type_id
            ci_type_id = step_definition.get("ci_type_id")
            if not ci_type_id:
                raise ValueError("cmdb_update requires ci_id, ci_type_id+lookup_fields, or both")

            items_stmt = select(ConfigurationItem).where(ConfigurationItem.type_id == ci_type_id)
            items_result = await db.execute(items_stmt)
            all_items = items_result.scalars().all()

            for candidate in all_items:
                ci_data = candidate.ci_data or {}
                all_match = True
                for criterion in lookup_fields:
                    field_key = criterion.get("field_key", "")
                    operator = criterion.get("operator", "=")
                    raw_value = criterion.get("value", "")
                    lookup_value = self._interpolate_value(raw_value, input_data)

                    ci_value = ci_data.get(field_key)
                    if ci_value is None:
                        if field_key == "name":
                            ci_value = candidate.name
                        elif field_key == "status":
                            ci_value = candidate.status
                        else:
                            all_match = False
                            break

                    op = operator.lower().strip()
                    if op in ("=", "eq"):
                        match = str(ci_value) == str(lookup_value)
                    elif op in ("!=", "neq"):
                        match = str(ci_value) != str(lookup_value)
                    else:
                        match = str(ci_value) == str(lookup_value)

                    if not match:
                        all_match = False
                        break

                if all_match:
                    item = candidate
                    break

        if not item:
            raise ValueError(f"Configuration item not found (ci_id={ci_id_raw})")

        # Apply updates
        old_data = dict(item.ci_data or {})
        new_data = dict(old_data)

        updates = self._interpolate_value(step_definition.get("updates", {}), input_data)
        if updates:
            new_data.update(updates)

        item.ci_data = new_data

        if "status" in step_definition:
            item.status = self._interpolate_value(step_definition["status"], input_data)
        if "name" in step_definition:
            item.name = self._interpolate_value(step_definition["name"], input_data)

        await db.commit()
        await db.refresh(item)

        # Fetch type info
        type_stmt = select(CIType).where(CIType.id == item.type_id)
        type_result = await db.execute(type_stmt)
        ci_type = type_result.scalar_one_or_none()

        return {
            "updated": True,
            "ci_id": item.id,
            "ci_name": item.name,
            "ci_status": item.status,
            "ci_data": item.ci_data or {},
            "ci_type_name": ci_type.name if ci_type else "",
            "ci_type_key": ci_type.key if ci_type else "",
            "fields_updated": list(updates.keys()) if updates else [],
            "old_values": {k: old_data.get(k) for k in updates} if updates else {},
            "executed_at": datetime.utcnow().isoformat(),
        }


class SubWorkflowExecutor(BaseExecutor):
    """B3: Synchronous sub-workflow invocation (call, wait, merge result).
    
    Configuration:
      - workflow_id: int — target workflow to invoke
      - input_data: dict — data to pass to sub-workflow (supports $input.* interpolation)
      - timeout_seconds: int — max wait for sub-run (default 300)
    
    Returns: result_data from the sub-workflow run, or error if timed out/failed.
    """
    
    def _interpolate_input(self, template: Any, input_data: Dict[str, Any]) -> Any:
        """Recursively interpolate $input.* in a template value."""
        if isinstance(template, str) and "$input." in template:
            import re
            def replace(match):
                field = match.group(1)
                return str(input_data.get(field, match.group(0)))
            return re.sub(r'\$input\.(\w+)', replace, template)
        elif isinstance(template, dict):
            return {k: self._interpolate_input(v, input_data) for k, v in template.items()}
        elif isinstance(template, list):
            return [self._interpolate_input(item, input_data) for item in template]
        return template
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any],
                     db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        """Execute sub-workflow synchronously."""
        from app.services.workflow_engine import workflow_engine

        workflow_id = step_definition.get("workflow_id")
        if not workflow_id:
            raise ValueError("sub_workflow step requires 'workflow_id'")

        # Interpolate input data
        raw_input = step_definition.get("input_data", {})
        resolved_input = self._interpolate_input(raw_input, input_data)

        # M16 fix: track parent run ID for audit trail.
        # The WorkflowRun model doesn't have a dedicated parent_run_id column yet,
        # so we store it in custom_data.  When the column is added via migration,
        # this can be moved to the proper field.
        parent_run_id = input_data.get("_workflow_run_id")

        # Create run data for sub-workflow
        from app.schemas.workflow import WorkflowRunCreate
        run_data = WorkflowRunCreate(
            workflow_id=workflow_id,
            input_data=resolved_input,
            triggered_by="sub_workflow",
        )

        # Trigger sub-workflow
        sub_run = await workflow_engine.trigger_workflow(db, workflow_id, run_data)

        # M16: record parent run ID on the sub-run for audit trail
        if parent_run_id is not None:
            sub_run.custom_data = dict(sub_run.custom_data or {})
            sub_run.custom_data["parent_run_id"] = int(parent_run_id)
            await db.commit()
        
        # Wait for completion (synchronous)
        timeout = step_definition.get("timeout_seconds", 300)
        import asyncio
        try:
            await asyncio.wait_for(
                self._wait_for_run_completion(db, sub_run.id, timeout),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return {
                "error": f"Sub-workflow run {sub_run.id} timed out after {timeout}s",
                "run_id": sub_run.id,
                "status": "timeout"
            }
        
        # Fetch final run state
        from sqlalchemy import select as sa_select
        from app.models.schemas import WorkflowRun
        run_stmt = sa_select(WorkflowRun).where(WorkflowRun.id == sub_run.id)
        run_result = await db.execute(run_stmt)
        final_run = run_result.scalar_one_or_none()
        
        if final_run.status == "completed":
            return {
                "success": True,
                "run_id": final_run.id,
                "status": final_run.status,
                "result_data": final_run.result_data or {},
                "duration_seconds": (final_run.completed_at - final_run.started_at).total_seconds() if final_run.completed_at and final_run.started_at else None
            }
        else:
            return {
                "success": False,
                "run_id": final_run.id,
                "status": final_run.status,
                "error_message": final_run.error_message if hasattr(final_run, 'error_message') and final_run.error_message else f"Sub-workflow ended with status: {final_run.status}"
            }
    
    async def _wait_for_run_completion(self, db: AsyncSession, run_id: int, timeout: int):
        """Poll until run completes, fails, times out, or pauses at a human step.

        Mirrors the engine's own terminal set (workflow_engine._execute_workflow):
        a sub-run may legitimately end in ``timeout`` (its own timeout fired) or
        sit at ``waiting`` (paused at a human_task/approval step). Both are real
        outcomes for a synchronous wait — treat them as terminal so the parent
        reports the true state instead of spinning until a spurious parent-side
        timeout.
        """
        import asyncio
        from app.models.schemas import WorkflowRun
        from sqlalchemy import select as sa_select
        
        start = asyncio.get_event_loop().time()
        while True:
            await asyncio.sleep(5)  # Poll every 5 seconds
            
            stmt = sa_select(WorkflowRun).where(WorkflowRun.id == run_id)
            result = await db.execute(stmt)
            run = result.scalar_one_or_none()
            
            if not run:
                raise ValueError(f"Sub-workflow run {run_id} not found")
            
            if run.status in ("completed", "failed", "cancelled", "timeout", "waiting"):
                return  # Done
            
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed > timeout:
                raise asyncio.TimeoutError(f"Timed out after {timeout}s")
