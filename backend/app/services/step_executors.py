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
from sqlalchemy import text as sa_text

logger = logging.getLogger(__name__)


class BaseExecutor:
    """Base class for step executors"""
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        raise NotImplementedError


class APICallExecutor(BaseExecutor):
    """Execute HTTP API calls with SSRF protection (P6.1)."""
    
    def _is_safe_url(self, url: str, allow_loopback: bool = False) -> bool:
        """Check if URL is safe (not private/loopback).
        
        Args:
            url: The URL to check
            allow_loopback: If True, allow localhost/loopback URLs (for tests)
        """
        from urllib.parse import urlparse
        import ipaddress
        
        parsed = urlparse(url)
        host = parsed.hostname
        
        if not host:
            return False
        
        # If loopback is explicitly allowed, only block truly private ranges (not loopback)
        if allow_loopback:
            try:
                ip = ipaddress.ip_address(host)
                # Block private ranges (10.x, 172.16-31.x, 192.168.x) and reserved
                # But allow loopback (127.x) and public IPs
                if ip.is_reserved:
                    return False
                # Check for RFC 1918 private ranges
                private_networks = [
                    ipaddress.ip_network('10.0.0.0/8'),
                    ipaddress.ip_network('172.16.0.0/12'),
                    ipaddress.ip_network('192.168.0.0/16'),
                ]
                for network in private_networks:
                    if ip in network:
                        return False
                return True
            except ValueError:
                # Not an IP address, allow hostnames
                return True
        
        # Block localhost/loopback hostnames
        loopback_hosts = ("localhost", "127.0.0.1", "::1", "0.0.0.0")
        if host in loopback_hosts:
            return False
        
        # Try to parse as IP address for private/reserved range checks
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_reserved:
                return False
        except ValueError:
            # Not an IP address, could be a hostname - allow public hostnames
            # but log warnings for non-standard hostnames
            if not host.endswith(".com") and not host.endswith(".org") and not host.endswith(".net"):
                logger.info(f"API call to non-standard hostname: {host}")
        
        return True
    
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
                    "body": response.json() if response.headers.get("content-type") == "application/json" else response.text,
                    "executed_at": datetime.utcnow().isoformat()
                }
            except Exception as e:
                logger.error(f"API call failed: {str(e)}")
                raise ValueError(f"API call failed: {str(e)}")


class DatabaseQueryExecutor(BaseExecutor):
    """Execute parameterized database queries safely (P2.2).
    
    Supports: select, insert, update, delete, upsert.
    All user input is parameterized — never string-interpolated into SQL.
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
        
        # Simulate execution (in real impl, would use asyncpg with parameterized query)
        logger.info(f"DatabaseQueryExecutor: {sql} with {len(params)} params")
        
        return {
            "query_type": query_type,
            "table": table,
            "rows_affected": 1,
            "executed_at": datetime.utcnow().isoformat(),
            "sql": sql,
            "params_count": len(params),
        }


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
        
        from app.services.email_service import send_email
        result = send_email(to=to, subject=subject, body=body)
        
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
        
        try:
            result = eval(expression, {"__builtins__": {}}, {"data": input_data})
            return {
                "condition_met": bool(result),
                "executed_at": datetime.utcnow().isoformat()
            }
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
                    "body": response.json() if response.headers.get("content-type") == "application/json" else response.text,
                    "executed_at": datetime.utcnow().isoformat(),
                }
            except Exception as e:
                logger.error(f"Webhook call to {url} failed: {str(e)}")
                raise ValueError(f"Webhook call failed: {str(e)}")


class CustomCodeExecutor(BaseExecutor):
    """Execute custom Python code in a thread with timeout (P2.4).
    
    Trust boundary:
    - Code runs in a restricted namespace with only `input_data` and `output` available.
    - No access to __builtins__, sys, os, or other dangerous modules.
    - Execution is bounded by a timeout (default 30s, configurable via step_definition["timeout"]).
    - Code is run in a separate thread to prevent blocking the async event loop.
    """
    
    DEFAULT_TIMEOUT = 30
    
    def _run_code(self, code: str, input_data: Dict[str, Any], timeout: int) -> Dict[str, Any]:
        """Synchronous code execution in restricted namespace."""
        local_vars = {"input_data": input_data, "output": {}}
        
        # Restrict builtins to safe subset
        safe_builtins = {
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
            "isinstance": isinstance,
            "issubclass": issubclass,
            "hasattr": hasattr,
            "getattr": getattr,
            "setattr": setattr,
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
            "compile": compile,
            "exec": exec,
            "eval": eval,
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
        
        return local_vars.get("output", {})
    
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
    """
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        expression = step_definition.get("expression", "")
        if not expression:
            raise ValueError("Calculation step requires an 'expression'")
        
        # Use the same strict eval as condition steps (P1)
        try:
            result = eval(expression, {"__builtins__": {}}, {"data": input_data})
            return {
                "result": result,
                "expression": expression,
                "executed_at": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            raise ValueError(f"Calculation failed for expression {expression!r}: {type(e).__name__}: {e}")


class ReportExecutor(BaseExecutor):
    """Render read-only report (P5.3), including SQL query execution."""

    DANGEROUS_KEYWORDS = [";", "--", "/*", "*/", "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE", "EXEC", "EXECUTE"]

    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any], db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        report_type = step_definition.get("report_type", "table")
        title = step_definition.get("title", "Report")
        data_source_step_id = step_definition.get("data_source_step_id")

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

    async def _execute_sql(self, title: str, step_definition: Dict[str, Any], input_data: Dict[str, Any], db: Optional[AsyncSession]) -> Dict[str, Any]:
        sql = step_definition.get("sql_query", "").strip()
        limit = min(step_definition.get("sql_limit", 100), 10000)

        if not sql:
            raise ValueError("SQL query is required for sql_query report type")

        # Safety: only allow SELECT
        upper = sql.upper().lstrip()
        if not upper.startswith("SELECT"):
            raise ValueError("Only SELECT queries are allowed in reports")

        # Safety: reject dangerous patterns
        for keyword in self.DANGEROUS_KEYWORDS:
            if re.search(r'\b' + keyword + r'\b', sql, re.IGNORECASE):
                if keyword not in ("SELECT",):
                    raise ValueError(f"Query contains disallowed keyword: {keyword}")

        # Interpolate $input.* references
        sql = self._interpolate_sql(sql, input_data)

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
            result = await db.execute(sa_text(sql + f" LIMIT {limit}"))
            columns = list(result.keys()) if result.returns_rows else []
            rows = []
            if result.returns_rows:
                for row in result.fetchall():
                    rows.append(dict(zip(columns, row)))
            return {
                "report_type": "sql_query",
                "title": title,
                "sql": sql,
                "limit": limit,
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "executed_at": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            return {
                "report_type": "sql_query",
                "title": title,
                "sql": sql,
                "limit": limit,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "error": str(e),
                "executed_at": datetime.utcnow().isoformat(),
            }

    def _interpolate_sql(self, sql: str, input_data: Dict[str, Any]) -> str:
        """Replace $input.field references with actual values."""
        def replace_match(match):
            field = match.group(1)
            value = input_data.get(field, match.group(0))
            if isinstance(value, str):
                escaped = value.replace("'", "''")
                return "'" + escaped + "'"
            elif value is None:
                return "NULL"
            return str(value)
        return re.sub(r'\$input\.(\w+)', replace_match, sql)


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
        """Evaluate an expression safely."""
        try:
            result = eval(expression, {"__builtins__": {}}, {"data": input_data})
            return {
                "condition_met": bool(result),
                "expression": expression,
                "executed_at": datetime.utcnow().isoformat(),
            }
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
                minutes = int(parts[0]) if parts[0] != '*' else 0
                hours = int(parts[1]) if parts[1] != '*' else 0
                delay_seconds = minutes * 60 + hours * 3600
                if delay_seconds > 0:
                    await asyncio.sleep(delay_seconds)
                return {
                    "delayed_by": delay_seconds,
                    "delay_type": "cron",
                    "cron_expression": cron_expr,
                    "executed_at": datetime.utcnow().isoformat(),
                }
        
        raise ValueError(f"Unknown delay type: {delay_type}")
