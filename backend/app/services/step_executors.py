"""
Step executors for different workflow step types
"""
import asyncio
import functools
import logging
import multiprocessing as mp
import re
import resource
from typing import Dict, Any, Optional, List
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

    async def compensate(
        self,
        input_data: Dict[str, Any],
        step_definition: Dict[str, Any],
        output_data: Dict[str, Any],
        db: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        """Reverse this step's side effects as a SAGA compensating transaction (G6).

        Default is a no-op: read-only or naturally idempotent steps have nothing to
        undo. Executors that perform irreversible side effects override this to reverse
        them (e.g. :class:`APICallExecutor` turning a POST into a DELETE). Best-effort —
        the engine never lets one compensation abort another.
        """
        return {"compensated": False, "note": "no-op"}


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

    async def compensate(
        self,
        input_data: Dict[str, Any],
        step_definition: Dict[str, Any],
        output_data: Dict[str, Any],
        db: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        """Undo a completed API call via a declared compensating request (G6).

        If the step definition carries a ``compensate`` block
        (``{"method", "url", "headers?", "body?"}``) — typically POST -> DELETE — that
        request is issued to reverse the original side effect. No-op (recorded) when no
        compensating block was declared. SSRF protection still applies to the URL.
        """
        comp = step_definition.get("compensate")
        if not isinstance(comp, dict) or not comp.get("url"):
            return {"compensated": False, "note": "no compensate block declared"}

        method = str(comp.get("method", "DELETE")).upper()
        url = comp["url"]
        headers = comp.get("headers", {})
        body = comp.get("body")

        if not self._is_safe_url(url):
            raise ValueError(f"Compensating call to private/loopback URL blocked: {url}")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method=method, url=url, headers=headers, json=body, timeout=30.0
                )
            except Exception as e:
                raise ValueError(f"Compensating API call failed: {e}")

        return {
            "compensated": True,
            "method": method,
            "url": url,
            "status_code": response.status_code,
        }


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


def _custom_code_worker(code: str, input_data: Dict[str, Any], result_q, timeout: int) -> None:
    """Run custom code inside a child process and report the result via ``result_q``.

    Resource limits (CPU time + address space) are applied *inside* the child so a
    runaway step cannot exhaust host resources. See findings/PythonWorkflow-Findings.md #1.
    """
    try:
        # Hard CPU-time ceiling with a small grace margin above the configured
        # timeout; an address-space cap bounds memory-based DoS.
        resource.setrlimit(resource.RLIMIT_CPU, (timeout + 5, timeout + 5))
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    except (ValueError, OSError):
        # Limits are best-effort; some environments restrict what we can set.
        pass

    try:
        data = CustomCodeExecutor()._run_code(code, input_data, timeout)
        result_q.put(("ok", data))
    except BaseException as exc:  # noqa: BLE001 - re-raised in the parent
        result_q.put(("err", exc))


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
            # NOTE: ``type`` is intentionally omitted. Exposing the real
            # ``type`` builtin lets user code obtain a genuine class object
            # (e.g. ``type("")`` -> ``str``) whose ``__subclasses__`` /
            # ``__mro__`` are not proxied, enabling the classic sandbox-escape
            # chain to reach ``os.system``. See findings/PythonWorkflow-Findings.md #1.
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

        # Run in a child process so we can enforce a *hard* wall-clock timeout
        # (terminate a runaway / infinite-loop step) and apply per-process
        # resource limits. run_in_executor keeps the event loop free while the
        # blocking Process.join(timeout) runs in a thread-pool worker.
        def _run_blocking():
            ctx = mp.get_context("fork")
            result_q = ctx.Queue()
            proc = ctx.Process(target=_custom_code_worker, args=(code, input_data, result_q, timeout))
            proc.start()
            proc.join(timeout)
            if proc.is_alive():
                proc.terminate()
                proc.join()
                raise TimeoutError(
                    f"Custom code step exceeded timeout of {timeout}s and was terminated"
                )
            status, payload = result_q.get()
            if status == "err":
                raise payload
            return payload

        loop = asyncio.get_running_loop()
        try:
            output = await loop.run_in_executor(None, _run_blocking)
        except TimeoutError:
            raise
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


class TransformExecutor(BaseExecutor):
    """Data transform / map / merge node (M2).

    Applies an ordered list of field ``operations`` to derive a new object from
    the step input, so non-trivial rename / restructure / merge / join /
    derived-object work does not require dropping into ``custom_code``. Each
    operation is
    applied in order to a working copy of the step input; the resulting object is
    returned under ``transformed`` (merged into ``run.input_data`` for downstream
    steps).

    Supported operations (all optional, applied top-to-bottom):

    * ``rename``   -- ``{"op": "rename", "fields": {"old": "new"}}``
    * ``remove``   -- ``{"op": "remove", "fields": ["k", ...]}``
    * ``set``      -- ``{"op": "set", "fields": {"k": value}}`` (value may use
                      ``$input.*`` references, resolved against the current
                      working data so later ops can reference earlier output)
    * ``project``  -- ``{"op": "project", "fields": ["k", ...]}`` (keep only these)
    * ``merge``    -- ``{"op": "merge", "fields": <obj | "$input.src">}`` (deep merge)
    * ``map``      -- ``{"op": "map", "items_field": "k", "operations": [...]}``
                      (apply the sub-operations to each element of list ``k``)
    * ``join``     -- ``{"op": "join", "left_field": "k", "right": <list | "$input.r">,
                      "on": "key"}`` (left join; matching right fields are attached)

    ``{{ ... }}`` templates in the definition are pre-resolved by the engine;
    only ``$input.*`` references are interpolated here.
    """

    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        operations = step_definition.get("operations")
        if not isinstance(operations, list) or not operations:
            raise ValueError("Transform step requires a non-empty 'operations' list")

        data = dict(input_data or {})
        applied = 0
        for op in operations:
            data = self._apply_op(data, op)
            applied += 1

        return {
            "transformed": data,
            "operations_applied": applied,
            "executed_at": datetime.utcnow().isoformat(),
        }

    # -- operation dispatch -------------------------------------------------- #
    def _apply_op(self, data: Dict[str, Any], op: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(op, dict) or "op" not in op:
            raise ValueError(f"Invalid transform operation: {op!r} (expected an 'op' key)")
        kind = op["op"]
        handler = getattr(self, f"_op_{kind}", None)
        if handler is None:
            raise ValueError(f"Unknown transform operation '{kind}'")
        return handler(data, op)

    def _op_rename(self, data, op):
        mapping = op.get("fields", {})
        if not isinstance(mapping, dict):
            raise ValueError("rename 'fields' must be an object of {old: new}")
        result = {}
        for key, value in data.items():
            result[mapping.get(key, key)] = value
        return result

    def _op_remove(self, data, op):
        fields = op.get("fields", [])
        if not isinstance(fields, list):
            raise ValueError("remove 'fields' must be a list")
        drop = set(fields)
        return {k: v for k, v in data.items() if k not in drop}

    def _op_project(self, data, op):
        fields = op.get("fields", [])
        if not isinstance(fields, list):
            raise ValueError("project 'fields' must be a list")
        keep = set(fields)
        return {k: v for k, v in data.items() if k in keep}

    def _op_set(self, data, op):
        fields = op.get("fields", {})
        if not isinstance(fields, dict):
            raise ValueError("set 'fields' must be an object of {key: value}")
        result = dict(data)
        for key, raw in fields.items():
            result[key] = self._interpolate_value(raw, data)
        return result

    def _op_merge(self, data, op):
        source = op.get("fields")
        if source is None:
            raise ValueError("merge requires a 'fields' object or '$input.*' source")
        src = self._interpolate_value(source, data) if isinstance(source, str) else source
        if not isinstance(src, dict):
            raise ValueError("merge source must resolve to an object")
        return self._deep_merge(dict(data), src)

    def _op_map(self, data, op):
        items_field = op.get("items_field")
        if not items_field:
            raise ValueError("map requires 'items_field'")
        sub_ops = op.get("operations", [])
        if not isinstance(sub_ops, list):
            raise ValueError("map 'operations' must be a list")
        raw = data.get(items_field)
        if not isinstance(raw, list):
            raise ValueError(f"map 'items_field' '{items_field}' must be an existing list")
        result = []
        for item in raw:
            elem = dict(item) if isinstance(item, dict) else {"value": item}
            for sub in sub_ops:
                elem = self._apply_op(elem, sub)
            result.append(elem)
        new_data = dict(data)
        new_data[items_field] = result
        return new_data

    def _op_join(self, data, op):
        left_field = op.get("left_field")
        right = op.get("right")
        on = op.get("on")
        if not left_field or right is None or on is None:
            raise ValueError("join requires 'left_field', 'right', and 'on'")
        left = data.get(left_field)
        if not isinstance(left, list):
            raise ValueError(f"join 'left_field' '{left_field}' must be a list")
        right_list = self._interpolate_value(right, data) if isinstance(right, str) else right
        if not isinstance(right_list, list):
            raise ValueError("join 'right' must resolve to a list")
        result = []
        for left_rec in left:
            merged = dict(left_rec) if isinstance(left_rec, dict) else {"value": left_rec}
            for right_rec in right_list:
                if isinstance(right_rec, dict) and right_rec.get(on) == merged.get(on):
                    merged.update(right_rec)
                    break
            result.append(merged)
        new_data = dict(data)
        new_data[left_field] = result
        return new_data

    # -- helpers ------------------------------------------------------------- #
    @staticmethod
    def _deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
        for key, value in src.items():
            if isinstance(value, dict) and isinstance(dst.get(key), dict):
                TransformExecutor._deep_merge(dst[key], value)
            else:
                dst[key] = value
        return dst

    def _interpolate_value(self, value: Any, input_data: Dict[str, Any]) -> Any:
        """Recursively interpolate $input.* references (same style as other executors)."""
        if isinstance(value, str) and value.startswith("$input."):
            field = value[len("$input."):]
            return input_data.get(field, value)
        elif isinstance(value, dict):
            return {k: self._interpolate_value(v, input_data) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._interpolate_value(item, input_data) for item in value]
        return value


class JoinExecutor(BaseExecutor):
    """Workflow-level output aggregation / join node (M9).

    Unlike ``TransformExecutor``'s data-level ``join`` operation, this node
    collects *branch outputs* from a fan-in and publishes one deterministic,
    aliased object for downstream steps.

    Definition::

        {
          "sources": [
            {"step_id": 12, "as": "validation"},
            {"step_id": 13, "as": "enrichment"},
            {"key": "manual_input", "as": "manual"}
          ],
          "output_key": "joined",
          "include_input": false,
          "missing": "error"
        }

    * ``step_id`` sources read the latest completed/skipped ``StepInstance`` for
      the current run from the database (the engine injects ``_workflow_run_id``).
      Real graph edges must still wire the branches into this step — source
      declarations only select and alias outputs, they do not create edges.
    * ``key`` sources read an already-flat ``$input`` key. Useful when a branch
      published a value directly into run state and for unit testing.
    * ``as`` gives each source a stable alias, avoiding collisions when branches
      both emit keys like ``rows``. With no ``sources``, all non-meta input keys
      are collected under ``output_key``.
    * ``include_input`` defaults to false when sources are declared and true
      otherwise. ``missing: "skip"`` omits absent sources; the default fails
      closed so a broken join is visible instead of silently producing partial data.

    Read-only: the default ``BaseExecutor.compensate`` no-op is correct.
    """

    META_KEYS = {"_workflow_run_id", "_workflow_step_id"}

    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        sources = step_definition.get("sources") or []
        if not isinstance(sources, list):
            raise ValueError("Join 'sources' must be a list")

        raw_output_key = step_definition.get("output_key")
        output_key = "joined" if raw_output_key is None else raw_output_key
        if not isinstance(output_key, str) or not output_key.strip():
            raise ValueError("Join 'output_key' must be a non-empty string")

        missing_policy = str(step_definition.get("missing", "error")).lower()
        if missing_policy not in ("error", "skip"):
            raise ValueError("Join 'missing' must be 'error' or 'skip'")

        include_input = step_definition.get(
            "include_input", not bool(sources)
        )
        joined = {
            k: v for k, v in (input_data or {}).items() if k not in self.META_KEYS
        } if include_input else {}

        resolved = []
        missing = []
        # Validate every source before any I/O so a bad definition fails with a
        # precise message even when it contains a step_id source.
        parsed = [self._parse_source(source, index) for index, source in enumerate(sources)]
        db_outputs = await self._load_step_outputs(sources, input_data, db) if any(
            step_id is not None for step_id, _, _ in parsed
        ) else {}

        for step_id, key, alias in parsed:
            value = None
            found = False

            if step_id is not None:
                key = ("step_id", step_id)
                if key in db_outputs:
                    value = db_outputs[key]
                    found = True
            elif key is not None:
                found = key in (input_data or {})
                if found:
                    value = (input_data or {})[key]

            if not found:
                if missing_policy == "error":
                    raise ValueError(
                        f"Join source {step_id if step_id is not None else key!r} "
                        "has no completed output in this run"
                    )
                missing.append(str(step_id if step_id is not None else key))
                continue

            alias = alias or str(step_id if step_id is not None else key)
            if isinstance(value, dict):
                TransformExecutor._deep_merge(joined.setdefault(alias, {}), value)
            else:
                joined[alias] = value
            resolved.append({
                "step_id": step_id,
                "key": key if step_id is None else None,
                "as": alias,
                "status": "resolved",
            })

        if not sources:
            for key, value in (input_data or {}).items():
                if key not in self.META_KEYS:
                    joined[key] = value

        return {
            output_key: joined,
            "sources": resolved,
            "source_count": len(resolved),
            "missing_sources": missing,
            "executed_at": datetime.utcnow().isoformat(),
        }

    def _parse_source(self, source: Any, index: int):
        """Return ``(step_id, input_key, alias)`` for one source declaration."""
        if isinstance(source, dict):
            step_id = source.get("step_id")
            key = source.get("key")
            alias = source.get("as")
        else:
            step_id = None
            key = source
            alias = None

        if step_id is not None:
            try:
                step_id = int(step_id)
            except (TypeError, ValueError) as e:
                raise ValueError(f"Join source #{index} has invalid step_id: {step_id!r}") from e
        elif key is None or not str(key):
            raise ValueError(f"Join source #{index} needs a 'step_id' or 'key'")

        if alias is not None and (not isinstance(alias, str) or not alias.strip()):
            raise ValueError(f"Join source #{index} has an invalid alias: {alias!r}")
        return step_id, key, alias

    async def _load_step_outputs(self, sources, input_data: Dict[str, Any], db):
        """Fetch latest completed/skipped outputs for all step_id sources at once."""
        if db is None:
            raise ValueError(
                "Join sources with 'step_id' require a database session "
                "(use 'key' sources for flat $input values)"
            )
        run_id = input_data.get("_workflow_run_id")
        if run_id is None:
            raise ValueError("Join 'step_id' sources require the current workflow run id")

        step_ids = []
        for source in sources:
            if isinstance(source, dict) and source.get("step_id") is not None:
                try:
                    step_ids.append(int(source["step_id"]))
                except (TypeError, ValueError):
                    continue
        if not step_ids:
            return {}

        from app.models.schemas import StepInstance  # local import avoids engine cycles

        stmt = (
            select(StepInstance)
            .where(
                StepInstance.workflow_run_id == run_id,
                StepInstance.step_id.in_(step_ids),
                StepInstance.status.in_(["completed", "skipped"]),
            )
            .order_by(StepInstance.id.desc())
        )
        result = await db.execute(stmt)
        outputs = {}
        for instance in result.scalars().all():
            marker = ("step_id", instance.step_id)
            if marker not in outputs:  # first row is the latest attempt
                outputs[marker] = dict(instance.output_data or {})
        return outputs


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
        owned_session = False
        if not session:
            session = async_session_factory()
            if hasattr(session, '__aenter__'):
                session = await session.__aenter__()
            owned_session = True

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
        finally:
            # Release a session we opened ourselves; the caller's session is
            # owned by the engine.
            if owned_session and hasattr(session, 'close'):
                await session.close()

        # L2: let execution errors propagate so the engine marks the step failed
        # instead of silently returning an error dict. The engine treats a
        # returned dict as success and spreads it into run.input_data, so a
        # failing visual-query report was previously swallowed.
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


class LoopExecutor(BaseExecutor):
    """M1: Iterate over a collection, running an inner step once per item.

    This is the missing loop/foreach primitive. It lets a workflow "send an email
    per recipient", "process each row of a query result", or "run the same approval
    against a list of items" without hand-rolled ``custom_code`` or manual unrolling.

    Configuration (step_definition):
      collection:  How to obtain the list to iterate. One of:
        - a literal Python list                 (collection_source="explicit")
        - a key name whose value in input_data is a list   (collection_source="input")
        - a "$input.<key>" reference resolving to a list    (collection_source="input")
        - an inner query definition (visual_query, or type+table) whose output has a
          "rows" key                            (collection_source="query")
      inner_step:  {"step_type": ..., "definition": {...}} — any registered executor
                    runs once per item. Unknown step_type fails the step (fail closed).
      item_key:    Key under which each item is injected into the inner step's input
                   (default "item"). The inner step sees input_data["<item_key>"].
      index_key:   Key for the 0-based iteration index (default "index").
      max_items:   Optional cap on how many items to process.
      break_condition: Optional expression (same safe syntax as a condition step,
                   scoped to "data" = the per-item input). When it evaluates truthy,
                   iteration stops early.
      concurrent:  If true, run inner steps with a bounded async pool (default false;
                   sequential is deterministic and safer for shared side effects).
      max_workers: Pool size when concurrent=true (default 5).
      collect:     If true (default), collect per-item results into the output.

    Output (merged into run.input_data by the engine):
      loop_count:         number of items actually processed
      loop_requested:     number of items in the resolved collection (before cap/break)
      loop_results:       [{"index", "item", "output"}, ...] for processed items
      loop_items:         [item, ...] — the processed items themselves (convenient for
                          downstream steps that only need the values)
      executed_at
    """

    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any],
                        db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        item_key = step_definition.get("item_key", "item")
        index_key = step_definition.get("index_key", "index")
        max_items = step_definition.get("max_items")
        break_condition = step_definition.get("break_condition")
        concurrent = bool(step_definition.get("concurrent", False))
        max_workers = int(step_definition.get("max_workers", 5))
        collect = bool(step_definition.get("collect", True))

        inner_step = step_definition.get("inner_step")
        if not isinstance(inner_step, dict) or "step_type" not in inner_step:
            raise ValueError("loop step requires an 'inner_step' with a 'step_type'")
        inner_def = dict(inner_step.get("definition") or {})

        # --- Resolve the collection -------------------------------------------------
        collection = await self._resolve_collection(input_data, step_definition, db)
        if not isinstance(collection, list):
            raise ValueError(
                f"loop collection resolved to {type(collection).__name__}, expected a list"
            )
        requested = len(collection)
        if max_items is not None:
            collection = collection[: int(max_items)]

        # --- Grab the inner executor from the engine's registry ---------------------
        from app.services.workflow_engine import workflow_engine
        inner_exec = workflow_engine.step_executors.get(inner_step["step_type"])
        if inner_exec is None:
            raise ValueError(
                f"loop inner_step has unknown step_type {inner_step['step_type']!r}; "
                f"registered executors: {sorted(workflow_engine.step_executors)}"
            )

        # --- Run one item -----------------------------------------------------------
        async def run_one(i: int) -> Dict[str, Any]:
            item = collection[i]
            item_input = {**(input_data or {}), item_key: item, index_key: i}
            if break_condition:
                if workflow_engine._evaluate_condition(break_condition, item_input):
                    return {"index": i, "item": item, "output": None, "broken": True}
            output = await inner_exec.execute(item_input, inner_def, db=db)
            entry = {"index": i, "item": item, "output": output}
            if output and isinstance(output, dict):
                entry["output"] = _unwrap(output)
            return entry

        results: List[Dict[str, Any]] = []
        if concurrent and len(collection) > 1:
            from asyncio import gather
            gathered = await gather(*(run_one(i) for i in range(len(collection))))
            for entry in gathered:
                results.append(entry)
                if entry.get("broken"):
                    break
        else:
            for i in range(len(collection)):
                entry = await run_one(i)
                results.append(entry)
                if entry.get("broken"):
                    break

        processed_items = [e["item"] for e in results]
        output: Dict[str, Any] = {
            "loop_count": len(results),
            "loop_requested": requested,
            "loop_items": processed_items,
        }
        if collect:
            output["loop_results"] = results
        output["executed_at"] = datetime.utcnow().isoformat()
        return output

    async def _resolve_collection(self, input_data: Dict[str, Any],
                                  step_definition: Dict[str, Any],
                                  db: Optional[AsyncSession]) -> Any:
        """Resolve the loop collection from its configured source.

        Sources:
          - explicit: a literal list (or an inline query dict) in ``collection``.
          - input: a key name or ``$input.<key>`` reference into step input data.
          - query: rows from a database query, configured via the flat ``query_*``
            fields the designer emits (query_table, query_query, query_conditions,
            query_limit). Delegates to the registered database_query executor, whose
            visual-query path returns ``rows``.
        """
        source = step_definition.get("collection_source", "explicit")
        raw = step_definition.get("collection")

        # --- query source -------------------------------------------------------
        is_inline_query = isinstance(raw, dict) and (
            "visual_query" in raw or "table" in raw or "type" in raw
        )
        if source == "query" or is_inline_query:
            from app.services.workflow_engine import workflow_engine
            query_exec = workflow_engine.step_executors.get("database_query")
            if query_exec is None:
                raise ValueError("loop query source requires the database_query executor")

            if is_inline_query:
                # caller passed a ready-made database_query definition under `collection`
                query_def = raw
            else:
                # designer emits flat query_* fields; build a visual_query so we get rows
                table = step_definition.get("query_table") or ""
                limit = int(step_definition.get("query_limit") or 100 or 100)
                if step_definition.get("query_visual") and isinstance(
                        step_definition.get("query_query"), dict):
                    vq = dict(step_definition["query_query"])
                    vq.setdefault("table", table)
                    vq.setdefault("limit", limit)
                else:
                    conds = step_definition.get("query_conditions") or {}
                    vq = {
                        "table": table,
                        "filters": [
                            {"field": k, "operator": "=", "value": v}
                            for k, v in conds.items()
                        ],
                        "logic": "AND",
                        "limit": limit,
                    }
                query_def = {"visual_query": vq, "type": "select"}

            q_out = await query_exec.execute(input_data, query_def, db=db)
            rows = q_out.get("rows") if isinstance(q_out, dict) else None
            return rows if isinstance(rows, list) else []

        # explicit or input: both ultimately need a list from `raw` / input_data
        value = raw
        if source == "input":
            if isinstance(value, str) and value.startswith("$input."):
                return input_data.get(value[len("$input."):])
            if isinstance(value, str):
                # treat as a key name whose value in input_data is the list
                return input_data.get(value)
        return value


class TryCatchExecutor(BaseExecutor):
    """M6: a try/catch boundary around a group of nested steps.

    Unlike a single-step ``on_failure_target_step_id`` edge, this executor
    provides a subgraph-level boundary. Configuration (step_definition):

      try_steps:    non-empty list of ``{"step_type", "definition"}`` steps run
                    in order. Any exception enters the catch path.
      catch_steps:  list of nested steps run (in order) after an exception. Each
                    catch step receives the original step input plus error
                    context: ``error``, ``error_type``, ``_last_error``,
                    ``_failed_step_id`` / ``_failed_step_type``.
      error_filter: optional safe expression (same syntax as condition steps,
                    evaluated with ``data`` = step input + error context). A
                    false result re-raises the original error instead of
                    catching it. A malformed expression fails closed.
      compensate_try_steps: default true — successfully completed try steps are
                    compensated in reverse order (via their executor's
                    ``compensate()`` hook) before catch steps run.

    Output is merged into run input by the engine:
      success, caught, error, error_type, try_results, catch_results,
      compensations, executed_at.

    Nested steps are ordinary registered executors, but they are *not* separate
    StepInstances: they have no per-step retries, route_taken, or compensation
    audit at the run level. Use graph-mode ``on_failure_target_step_id`` when
    those are required.
    """

    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any],
                      db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        try_steps = step_definition.get("try_steps") or []
        catch_steps = step_definition.get("catch_steps") or []
        if not isinstance(try_steps, list) or not try_steps:
            raise ValueError("try_catch step requires a non-empty 'try_steps' list")
        if not isinstance(catch_steps, list):
            raise ValueError("try_catch 'catch_steps' must be a list")

        # Validate nested step specs up front: a malformed configuration is a
        # definition error, not an exception that the catch path should swallow.
        self._validate_steps(try_steps, "try_steps")
        self._validate_steps(catch_steps, "catch_steps")

        compensate_try_steps = step_definition.get("compensate_try_steps", True) is not False
        completed: List[Dict[str, Any]] = []
        result: Dict[str, Any] = {"try_results": [], "catch_results": [], "compensations": []}

        try:
            await self._run_steps(
                try_steps, input_data, db, completed=completed,
                results=result["try_results"],
            )
        except Exception as e:
            error_msg = str(e)
            failed_step = result["try_results"][-1] if result["try_results"] else {}
            error_context = self._error_context(
                input_data, e, error_msg, failed_step.get("step_type")
            )
            error_filter = step_definition.get("error_filter")
            if error_filter:
                from app.services.workflow_engine import workflow_engine

                if not workflow_engine._evaluate_condition(
                    error_filter, {**(input_data or {}), **error_context}
                ):
                    # Not our exception to catch — preserve the original failure.
                    raise

            if compensate_try_steps:
                result["compensations"] = await self._compensate(completed, db)

            catch_input = {**(input_data or {}), **error_context}
            await self._run_steps(
                catch_steps, catch_input, db, completed=None,
                results=result["catch_results"],
            )
            result.update({
                "success": True,
                "caught": True,
                "error": error_msg,
                "error_type": type(e).__name__,
                "executed_at": datetime.utcnow().isoformat(),
            })
            return result

        result.update({
            "success": True,
            "caught": False,
            "error": None,
            "error_type": None,
            "executed_at": datetime.utcnow().isoformat(),
        })
        return result

    @staticmethod
    def _error_context(
        input_data, error: Exception, error_msg: str, failed_step_type=None
    ) -> Dict[str, Any]:
        """Error fields injected into every catch step's input."""
        return {
            "error": error_msg,
            "error_type": type(error).__name__,
            "_last_error": error_msg,
            "_last_error_type": type(error).__name__,
            "_failed_step_id": (input_data or {}).get("_workflow_step_id"),
            "_failed_step_type": failed_step_type
            or (input_data or {}).get("_failed_step_type"),
        }

    @staticmethod
    def _validate_steps(steps, field: str) -> None:
        """Reject malformed nested step definitions before entering the try block."""
        from app.services.workflow_engine import workflow_engine

        for index, spec in enumerate(steps):
            if not isinstance(spec, dict) or not spec.get("step_type"):
                raise ValueError(
                    f"try_catch {field} step #{index} requires a 'step_type'"
                )
            if spec["step_type"] not in workflow_engine.step_executors:
                raise ValueError(
                    f"try_catch {field} step #{index} has unknown step_type "
                    f"{spec['step_type']!r}"
                )

    async def _run_steps(self, steps, input_data, db, completed, results) -> List[Dict[str, Any]]:
        """Run nested steps sequentially through the shared executor registry.

        ``results`` is supplied by the caller so a failing step is still visible
        in the audit list when the exception propagates to the catch boundary.
        """
        from app.services.workflow_engine import workflow_engine

        for index, spec in enumerate(steps):
            if not isinstance(spec, dict) or not spec.get("step_type"):
                raise ValueError(
                    f"try_catch nested step #{index} requires a 'step_type'"
                )
            executor = workflow_engine.step_executors.get(spec["step_type"])
            if executor is None:
                raise ValueError(
                    f"try_catch nested step #{index} has unknown step_type "
                    f"{spec['step_type']!r}"
                )
            definition = dict(spec.get("definition") or {})
            try:
                output = await executor.execute(input_data, definition, db=db)
            except Exception as e:
                # Keep the failing step in the audit list, then let the outer
                # try/catch boundary decide whether to catch or re-raise.
                results.append({
                    "index": index,
                    "step_type": spec["step_type"],
                    "output": {},
                    "error": str(e),
                    "error_type": type(e).__name__,
                })
                raise
            results.append({
                "index": index,
                "step_type": spec["step_type"],
                "output": _unwrap(output),
            })
            if completed is not None:
                completed.append({
                    "executor": executor,
                    "step_type": spec["step_type"],
                    "input_data": dict(input_data or {}),
                    "step_definition": definition,
                    "output_data": output,
                })
        return results

    async def _compensate(self, completed, db) -> List[Dict[str, Any]]:
        """Undo completed try steps in reverse order; never abort on one failure."""
        results: List[Dict[str, Any]] = []
        for rec in reversed(completed):
            try:
                detail = await rec["executor"].compensate(
                    rec["input_data"], rec["step_definition"], rec["output_data"], db=db
                )
                results.append({
                    "step_type": rec["step_type"],
                    "status": "compensated",
                    "detail": detail,
                })
            except Exception as e:
                results.append({
                    "step_type": rec["step_type"],
                    "status": "failed",
                    "detail": f"{type(e).__name__}: {e}",
                })
        return results


class SubWorkflowExecutor(BaseExecutor):
    """B3/G8: sub-workflow invocation (call/wait/merge, or fire-and-forget).

    Configuration:
      - workflow_id: int — target workflow to invoke
      - input_data: dict — data to pass to sub-workflow (supports $input.* interpolation)
      - execution_mode: "sync" (default) or "async". Sync waits for the child
        and merges its result; async returns immediately with the child run id.
      - timeout_seconds: int — max wait for a *sync* sub-run (default 300).
        Ignored in async mode.

    Launch errors always fail the parent step (so retries / on-failure routing /
    try_catch can handle them). In async mode, later child failures do not fail
    the parent — the child run owns its own outcome and error hooks.
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
        """Execute a sub-workflow synchronously, or launch it in the background."""
        from app.services.workflow_engine import workflow_engine

        workflow_id = step_definition.get("workflow_id")
        if not workflow_id:
            raise ValueError("sub_workflow step requires 'workflow_id'")

        # G8: default to sync so existing workflows are unchanged. Fail closed on
        # a typo rather than silently waiting forever or dropping the child run.
        execution_mode = str(step_definition.get("execution_mode", "sync")).lower()
        if execution_mode not in ("sync", "async"):
            raise ValueError(
                f"sub_workflow execution_mode must be 'sync' or 'async', got {execution_mode!r}"
            )

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

        # M16/G8: record lineage on the sub-run for audit trail. This is a
        # secondary write after the child was created; if it fails we must not
        # raise, because a parent retry would launch a duplicate child run.
        if parent_run_id is not None:
            try:
                sub_run.custom_data = dict(sub_run.custom_data or {})
                sub_run.custom_data["parent_run_id"] = int(parent_run_id)
                sub_run.custom_data["parent_step_id"] = input_data.get("_workflow_step_id")
                sub_run.custom_data["execution_mode"] = execution_mode
                await db.commit()
            except Exception:
                logger.warning(
                    "Could not attach parent lineage to sub-workflow run %s",
                    sub_run.id,
                    exc_info=True,
                )

        if execution_mode == "async":
            # G8: fire-and-forget. The child run is already committed and its
            # execution detaches inside trigger_workflow(); return a handle the
            # parent can pass downstream via $input.run_id without waiting.
            return {
                "success": True,
                "execution_mode": "async",
                "run_id": sub_run.id,
                "status": sub_run.status or "pending",
                "result_data": {},
                "duration_seconds": None,
            }

        # Wait for completion (synchronous)
        timeout = step_definition.get("timeout_seconds", 300)
        import asyncio
        try:
            await asyncio.wait_for(
                self._wait_for_run_completion(db, sub_run.id, timeout),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            # M6: surface a timed-out child as a failed *step* so on-failure
            # routing and try_catch boundaries can handle it. Returning a dict
            # here would make the parent step look successful.
            raise TimeoutError(
                f"Sub-workflow run {sub_run.id} timed out after {timeout}s"
            ) from None
        
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
                # WorkflowRun stores a run's final output in ``output_data`` (not
                # ``result_data`` -- that column belongs to the Task model). Reading
                # ``result_data`` here raised AttributeError on every successful
                # sub-workflow. See Feature-Plan §2.1.
                "result_data": final_run.output_data or {},
                "duration_seconds": final_run.duration_seconds
            }
        if final_run.status == "waiting":
            # A child paused at a human step is not a failure. Preserve the
            # historical status-only result; the parent can decide what to do.
            return {
                "success": False,
                "run_id": final_run.id,
                "status": final_run.status,
                "error_message": final_run.error_message or "Sub-workflow is waiting on a human task",
            }

        # M6: failed / timeout / cancelled children are step failures, not a
        # successful step with a misleading ``success: False`` payload. Raising
        # lets the engine's retries, on-failure routing and try_catch boundaries
        # see the real outcome.
        detail = final_run.error_message or f"Sub-workflow ended with status: {final_run.status}"
        raise RuntimeError(
            f"Sub-workflow run {final_run.id} failed with status "
            f"{final_run.status}: {detail}"
        )
    
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
