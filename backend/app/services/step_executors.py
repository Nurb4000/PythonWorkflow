"""
Step executors for different workflow step types
"""
import asyncio
import logging
from typing import Dict, Any
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)


class BaseExecutor:
    """Base class for step executors"""
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class APICallExecutor(BaseExecutor):
    """Execute HTTP API calls"""
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any]) -> Dict[str, Any]:
        method = step_definition.get("method", "GET").upper()
        url = step_definition.get("url", "")
        headers = step_definition.get("headers", {})
        body = step_definition.get("body")
        
        # Merge input data into request
        if "$input" in headers:
            headers.update(input_data)
        if "$input" in body:
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
    """Execute database queries (placeholder for now)"""
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any]) -> Dict[str, Any]:
        # This would be implemented with actual database connection pooling
        query_type = step_definition.get("type", "select")
        
        return {
            "query_type": query_type,
            "executed_at": datetime.utcnow().isoformat(),
            "message": "Database query executor - implement actual DB operations"
        }


class EmailExecutor(BaseExecutor):
    """Send email notifications (placeholder)"""
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any]) -> Dict[str, Any]:
        to = step_definition.get("to", "")
        subject = step_definition.get("subject", "")
        body = step_definition.get("body", "")
        
        # Merge input data into email
        if "$input" in to:
            to = str(input_data.get(to.replace("$input.", ""), to))
        if "$input" in subject:
            subject = str(input_data.get(subject.replace("$input.", ""), subject))
        if "$input" in body:
            body = str(input_data.get(body.replace("$input.", ""), body))
        
        logger.info(f"Email would be sent to {to}: {subject}")
        
        return {
            "to": to,
            "subject": subject,
            "sent": True,
            "executed_at": datetime.utcnow().isoformat()
        }


class ConditionExecutor(BaseExecutor):
    """Evaluate conditions for branching"""
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any]) -> Dict[str, Any]:
        expression = step_definition.get("expression", "True")
        
        try:
            result = eval(expression, {"__builtins__": {}}, {"data": input_data})
            return {
                "condition_met": bool(result),
                "executed_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            raise ValueError(f"Condition evaluation failed: {str(e)}")


class DelayExecutor(BaseExecutor):
    """Add a delay/sleep"""
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any]) -> Dict[str, Any]:
        seconds = step_definition.get("seconds", 0)
        
        if seconds > 0:
            await asyncio.sleep(seconds)
        
        return {
            "delayed_by": seconds,
            "executed_at": datetime.utcnow().isoformat()
        }


class FormExecutor(BaseExecutor):
    """Handle form collection steps"""
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any]) -> Dict[str, Any]:
        form_id = step_definition.get("form_id")
        
        return {
            "form_id": form_id,
            "status": "form_step_executed",
            "executed_at": datetime.utcnow().isoformat()
        }


class WebhookExecutor(BaseExecutor):
    """Handle webhook callbacks (placeholder)"""
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "webhook_url": step_definition.get("url"),
            "status": "webhook_step_executed",
            "executed_at": datetime.utcnow().isoformat()
        }


class CustomCodeExecutor(BaseExecutor):
    """Execute custom Python code (sandboxed)"""
    
    async def execute(self, input_data: Dict[str, Any], step_definition: Dict[str, Any]) -> Dict[str, Any]:
        code = step_definition.get("code", "")
        
        # Execute in restricted environment
        try:
            local_vars = {"input_data": input_data, "output": {}}
            exec(code, {"__builtins__": {}}, local_vars)
            
            return {
                **local_vars.get("output", {}),
                "executed_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            raise ValueError(f"Custom code execution failed: {str(e)}")
