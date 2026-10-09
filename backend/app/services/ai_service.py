"""
AI integration service for generating workflow steps, node assistance, and error diagnosis.
Supports llama.cpp (local) and OpenAI (cloud) providers.
"""
import json
import logging
from typing import Dict, Any, Optional, List
import httpx
from app.api.system_settings import settings as system_settings
from app.core.config import resolve_project_root

logger = logging.getLogger(__name__)


class AIService:
    """Service for AI-powered workflow assistance"""

    VALID_STEP_TYPES = {
        "api_call": ["method", "url"],
        "database_query": ["type", "table"],
        "email": ["to", "subject"],
        "form": ["form_id"],
        "condition": ["routes"],
        "delay": ["seconds"],
        "webhook": ["url"],
        "custom_code": ["code"],
        "human_task": [],
        "approval": [],
        "calculation": ["expression"],
        "report": ["report_type", "title"],
    }

    KB_DOMAIN_MAP = {
        "api_call": "nodes.api_call",
        "database_query": "nodes.sql",
        "email": "nodes.email",
        "condition": "nodes.condition",
        "custom_code": "nodes.custom_code",
        "webhook": "nodes.webhook",
        "report": "nodes.report",
        "delay": "nodes.delay",
        "programmable_delay": "nodes.delay",
        "calculation": "nodes.custom_code",
    }

    def __init__(self):
        self.kb = self._load_knowledge_base()

    @property
    def base_url(self):
        return system_settings.llama_cpp_url

    @property
    def model(self):
        return system_settings.llama_cpp_model

    def _load_knowledge_base(self) -> Dict[str, str]:
        """Load knowledge base files into a dict keyed by domain path"""
        kb = {}
        kb_root = resolve_project_root() / "knowledge-base"

        for directory in ["steering", "nodes", "queries", "forms", "debugging", "admin"]:
            dir_path = kb_root / directory
            if dir_path.exists():
                for file in dir_path.glob("*.md"):
                    domain_key = f"{directory}.{file.stem}"
                    try:
                        kb[domain_key] = file.read_text()
                    except Exception as e:
                        logger.warning(f"Failed to load KB file {file}: {e}")

        return kb

    def _get_relevant_kb(self, domains: List[str]) -> str:
        """Assemble only the KB sections needed for the given domains"""
        parts = []
        if "steering.master" in self.kb:
            parts.append(self.kb["steering.master"])
        for domain in domains:
            if domain in self.kb:
                parts.append(self.kb[domain])
        return "\n\n".join(parts) if parts else ""

    def _get_node_kb_domain(self, step_type: str) -> str:
        """Map a step type to its KB domain key"""
        return self.KB_DOMAIN_MAP.get(step_type, f"nodes.{step_type}")

    # ------------------------------------------------------------------
    # Existing public methods (updated to use per-domain KB)
    # ------------------------------------------------------------------

    async def generate_step(self, description: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate a workflow step from natural language description"""
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(description, context)
        kb_context = self._get_relevant_kb(["steering.master"])

        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"

        try:
            response = await self._call_ai(full_prompt)
            step = self._parse_response(response)
            self._validate_step(step)
            return step
        except Exception as e:
            logger.error(f"AI step generation failed: {str(e)}")
            raise ValueError(f"Failed to generate step: {str(e)}")

    async def generate_workflow(self, description: str, template_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Generate a complete workflow from description"""
        template = None
        if template_name:
            project_root = resolve_project_root()
            templates_path = project_root / "knowledge-base" / "templates"
            if templates_path.exists():
                for file in templates_path.glob("*.json"):
                    try:
                        t = json.loads(file.read_text())
                        if t.get("name") == template_name:
                            template = t
                            break
                    except Exception:
                        pass

        system_prompt = """You are a workflow designer. Generate a complete workflow with multiple steps based on the user's description.

Available step types:
- api_call: Make HTTP requests (GET, POST, PUT, DELETE)
- database_query: Query or modify database
- email: Send email notifications
- form: Collect data via forms
- condition: Branch based on conditions
- delay: Wait for a specified duration
- webhook: Handle webhook callbacks
- custom_code: Execute custom Python code

Output must be valid JSON with this structure:
{
  "name": "Workflow Name",
  "description": "Workflow description",
  "steps": [
    {
      "step_type": "<type>",
      "definition": { /* type-specific config */ },
      "condition_expr": "<optional linear-skip expression>"
    }
  ]
}

Condition steps use branching routes. Their "definition" must be:
{
  "routes": [
    {"expression": "data['field'] > 5", "target_step_id": null}
  ],
  "default_target_step_id": null
}

Rules:
1. Choose appropriate step types for each step
2. Steps should flow logically (API -> DB -> Email, etc.)
3. Condition expressions are Python expressions over "data" using data['field'] syntax
4. For condition steps, put the expression inside "routes", never in "condition_expr"
5. Add conditions for error handling and branching
6. Include delay steps where appropriate"""

        user_prompt = f"Generate a workflow for this description:\n{description}"
        if template:
            user_prompt += f"\n\nUse this template as reference:\n{json.dumps(template, indent=2)}"

        kb_context = self._get_relevant_kb(["steering.master"])
        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"

        try:
            response = await self._call_ai(full_prompt)
            workflow = self._parse_response(response)
            self._validate_workflow(workflow)
            return workflow.get("steps", [])
        except Exception as e:
            logger.error(f"AI workflow generation failed: {str(e)}")
            raise ValueError(f"Failed to generate workflow: {str(e)}")

    async def generate_form_schema(self, description: str) -> Dict[str, Any]:
        """Generate a JSON schema for a form from description"""
        system_prompt = """You are a form schema generator. Generate a JSON Schema for a form based on the user's description.

Output must be valid JSON with this structure:
{
  "type": "object",
  "properties": {
    "<field_name>": {
      "type": "<string|number|boolean|integer|email|textarea|select|info|date|date-time|file>",
      "title": "<Human readable title>",
      "description": "<Field description>",
      "required": <true|false>,
      "minLength": <optional>,
      "maxLength": <optional>,
      "pattern": "<optional regex>"
    }
  },
  "required": ["<list of required field names>"]
}

Rules:
1. Use appropriate field types from the allowed list
2. Provide clear titles and descriptions
3. Mark essential fields as required
4. Add validation (minLength, pattern, etc.) where needed
5. Keep the form simple and focused"""

        user_prompt = f"Generate a form schema for this description:\n{description}"
        kb_context = self._get_relevant_kb(["steering.master", "forms.form_schema"])
        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"

        try:
            response = await self._call_ai(full_prompt)
            schema = self._parse_response(response)
            self._validate_form_schema(schema)
            return schema
        except Exception as e:
            logger.error(f"AI form generation failed: {str(e)}")
            raise ValueError(f"Failed to generate form schema: {str(e)}")

    # ------------------------------------------------------------------
    # New assist methods
    # ------------------------------------------------------------------

    async def assist_node(
        self,
        action: str,
        step_type: str,
        description: Optional[str] = None,
        current_config: Optional[Dict] = None,
        upstream_data_shapes: Optional[Dict] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate, explain, fix, or optimize a workflow node configuration"""
        kb_domain = self._get_node_kb_domain(step_type)
        kb_context = self._get_relevant_kb(["steering.master", kb_domain])

        if action == "generate":
            return await self._node_generate(kb_context, step_type, description, upstream_data_shapes)
        elif action == "explain":
            return await self._node_explain(kb_context, step_type, current_config)
        elif action == "fix":
            return await self._node_fix(kb_context, step_type, current_config, error_message)
        elif action == "optimize":
            return await self._node_optimize(kb_context, step_type, current_config)
        else:
            raise ValueError(f"Unknown action: {action}")

    async def _node_generate(self, kb_context: str, step_type: str, description: str, upstream_data_shapes: Optional[Dict]) -> Dict[str, Any]:
        system_prompt = f"""Generate a workflow node configuration for step type "{step_type}".

Output must be valid JSON with this structure:
{{
  "step_type": "{step_type}",
  "title": "<Descriptive title>",
  "definition": {{ /* type-specific config */ }}
}}

Use the knowledge base patterns for guidance. If upstream data shapes are provided, reference them with $input.field_name syntax."""

        user_prompt = f"Generate a {step_type} step: {description}"
        if upstream_data_shapes:
            user_prompt += f"\n\nAvailable upstream data fields: {json.dumps(upstream_data_shapes)}"

        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"
        response = await self._call_ai(full_prompt)
        result = self._parse_response(response)
        return {"action": "generate", "config": result}

    async def _node_explain(self, kb_context: str, step_type: str, current_config: Dict) -> Dict[str, Any]:
        system_prompt = f"""Explain the following {step_type} node configuration in plain English.

Output must be valid JSON:
{{
  "explanation": "Clear description of what this node does",
  "variables_used": ["list", "of", "$input", "references"],
  "notes": "Any observations about the configuration"
}}"""

        user_prompt = f"Explain this {step_type} configuration:\n{json.dumps(current_config, indent=2)}"
        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"
        response = await self._call_ai(full_prompt)
        result = self._parse_response(response)
        return {"action": "explain", "result": result}

    async def _node_fix(self, kb_context: str, step_type: str, current_config: Dict, error_message: str) -> Dict[str, Any]:
        system_prompt = f"""Fix the following {step_type} node configuration that produced an error.

Output must be valid JSON:
{{
  "explanation": "What went wrong",
  "fixed_config": {{ /* corrected definition */ }},
  "changes_made": "Description of what was changed"
}}"""

        user_prompt = f"Fix this {step_type} configuration:\n{json.dumps(current_config, indent=2)}\n\nError: {error_message}"
        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"
        response = await self._call_ai(full_prompt)
        result = self._parse_response(response)
        return {"action": "fix", "result": result}

    async def _node_optimize(self, kb_context: str, step_type: str, current_config: Dict) -> Dict[str, Any]:
        system_prompt = f"""Suggest optimizations for the following {step_type} node configuration.

Output must be valid JSON:
{{
  "suggestions": ["list", "of", "improvements"],
  "optimized_config": {{ /* improved definition */ }},
  "benefits": "What these changes improve"
}}"""

        user_prompt = f"Optimize this {step_type} configuration:\n{json.dumps(current_config, indent=2)}"
        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"
        response = await self._call_ai(full_prompt)
        result = self._parse_response(response)
        return {"action": "optimize", "result": result}

    async def assist_query(
        self,
        action: str,
        description: Optional[str] = None,
        table: Optional[str] = None,
        sql: Optional[str] = None,
        error_message: Optional[str] = None,
        available_columns: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Generate, explain, or fix SQL queries for the data explorer"""
        kb_context = self._get_relevant_kb(["steering.master", "queries.query_builder"])

        if action == "generate":
            return await self._query_generate(kb_context, description, table, available_columns)
        elif action == "explain":
            return await self._query_explain(kb_context, sql)
        elif action == "fix":
            return await self._query_fix(kb_context, sql, error_message)
        else:
            raise ValueError(f"Unknown action: {action}")

    async def _query_generate(self, kb_context: str, description: str, table: Optional[str], available_columns: Optional[List[Dict]]) -> Dict[str, Any]:
        system_prompt = """Generate a SQL SELECT query from the natural language description.

Output must be valid JSON:
{
  "sql": "The generated SELECT query",
  "explanation": "Brief description of what the query does"
}

Rules:
1. Only generate SELECT queries
2. Use proper PostgreSQL syntax
3. Add LIMIT 100 if not specified
4. Reference available columns when provided"""

        user_prompt = f"Generate SQL for: {description}"
        if table:
            user_prompt += f"\nTable: {table}"
        if available_columns:
            user_prompt += f"\nAvailable columns: {json.dumps(available_columns)}"

        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"
        response = await self._call_ai(full_prompt)
        result = self._parse_response(response)
        return {"action": "generate", "result": result}

    async def _query_explain(self, kb_context: str, sql: str) -> Dict[str, Any]:
        system_prompt = """Explain the following SQL query in plain English.

Output must be valid JSON:
{
  "explanation": "Clear description of what this query does",
  "tables_used": ["list", "of", "tables"],
  "filters_applied": "Description of WHERE conditions",
  "notes": "Any observations about performance or correctness"
}"""

        user_prompt = f"Explain this SQL query:\n{sql}"
        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"
        response = await self._call_ai(full_prompt)
        result = self._parse_response(response)
        return {"action": "explain", "result": result}

    async def _query_fix(self, kb_context: str, sql: str, error_message: str) -> Dict[str, Any]:
        system_prompt = """Fix the following SQL query that produced an error.

Output must be valid JSON:
{
  "explanation": "What went wrong",
  "fixed_sql": "The corrected SELECT query",
  "changes_made": "Description of what was changed"
}

Rules:
1. Only generate SELECT queries
2. Preserve the user's intent
3. Use proper PostgreSQL syntax"""

        user_prompt = f"Fix this SQL query:\n{sql}\n\nError: {error_message}"
        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"
        response = await self._call_ai(full_prompt)
        result = self._parse_response(response)
        return {"action": "fix", "result": result}

    async def assist_form(
        self,
        action: str,
        description: Optional[str] = None,
        current_schema: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Suggest or improve form fields"""
        kb_context = self._get_relevant_kb(["steering.master", "forms.form_schema"])

        if action == "suggest_fields":
            system_prompt = """Suggest form fields based on the description.

Output must be valid JSON:
{
  "fields": [
    {
      "name": "field_key",
      "type": "string|number|integer|boolean|email|textarea|select|date|date-time|file",
      "title": "Human Readable Title",
      "description": "Field description",
      "required": true,
      "validation": {}
    }
  ]
}"""
            user_prompt = f"Suggest form fields for: {description}"
        elif action == "improve_schema":
            system_prompt = """Review and improve the following form schema. Suggest additional fields, better validation, or improved descriptions.

Output must be valid JSON:
{
  "suggestions": ["list", "of", "improvements"],
  "improved_properties": { /* updated field definitions */ },
  "improved_required": ["updated", "required", "fields"]
}"""
            user_prompt = f"Improve this form schema:\n{json.dumps(current_schema, indent=2)}"
        else:
            raise ValueError(f"Unknown action: {action}")

        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"
        response = await self._call_ai(full_prompt)
        result = self._parse_response(response)
        return {"action": action, "result": result}

    async def assist_report(
        self,
        action: str,
        description: Optional[str] = None,
        current_report: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Assist with report definition creation and improvement"""
        kb_context = self._get_relevant_kb(["steering.master", "reporting.report_def"])

        if action == "generate":
            system_prompt = """Generate a report definition from the description.

Output must be valid JSON:
{
  "name": "Report Name",
  "description": "Report purpose",
  "source": "sql_view|custom_query|form_submission",
  "columns": [
    {"field": "column_name", "label": "Display Label"}
  ],
  "filters": [
    {"column": "field", "operator": "=", "value": "condition"}
  ],
  "sort": [{"column": "field", "direction": "asc|desc"}],
  "limit": 100
}

Rules:
1. Use descriptive names and descriptions
2. Include sensible defaults for optional fields
3. Set reasonable limits (default 100, max 10000)
4. Sort by most useful column first
5. Filter to relevant data subset"""

            user_prompt = f"Generate a report: {description}"
        elif action == "improve":
            system_prompt = """Improve the following report definition. Suggest better columns, filters, or sorting.

Output must be valid JSON with structure:
{
  "suggestions": ["list", "of", "improvements"],
  "improved_report": { /* improved report definition */ }
}"""

            user_prompt = f"Improve this report:\n{json.dumps(current_report, indent=2)}"
        else:
            raise ValueError(f"Unknown action: {action}")

        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"
        response = await self._call_ai(full_prompt)
        result = self._parse_response(response)
        return {"action": action, "result": result}

    async def assist_cron(
        self,
        description: str,
    ) -> Dict[str, Any]:
        """Generate cron expression from natural language description"""
        kb_context = self._get_relevant_kb(["steering.master", "scheduler.cron"])

        system_prompt = """Generate a valid cron expression from the description.

Output must be valid JSON:
{
  "cron_expression": "0 9 * * *",
  "timezone": "UTC",
  "description": "Human-readable description",
  "next_runs": ["2026-08-26 09:00:00", "2026-08-27 09:00:00"]
}

Rules:
1. Use standard 5-field cron format
2. Include timezone (default UTC)
3. Provide human-readable description
4. Calculate next 2-3 run times
5. Validate expression is syntactically correct"""

        user_prompt = f"Generate cron expression for: {description}"

        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"
        response = await self._call_ai(full_prompt)
        result = self._parse_response(response)
        return result

    async def assist_webhook(
        self,
        action: str,
        description: Optional[str] = None,
        current_config: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Assist with webhook configuration"""
        kb_context = self._get_relevant_kb(["steering.master", "webhooks.config"])

        if action == "generate":
            system_prompt = """Generate webhook configuration from description.

Output must be valid JSON:
{
  "url": "https://example.com/webhook",
  "method": "POST",
  "headers": {"Content-Type": "application/json"},
  "body": "{\"data\": $input}",
  "timeout": 30,
  "retry_count": 3,
  "secret": "auto-generated-secret"
}

Rules:
1. Use HTTPS URLs when possible
2. Include proper headers
3. Set reasonable timeouts (default 30s)
4. Enable retry logic (default 3 retries)
5. Generate secure secret for incoming webhooks"""

            user_prompt = f"Generate webhook config: {description}"
        elif action == "validate":
            system_prompt = """Validate the following webhook configuration. Check for security issues, best practices, and correctness.

Output must be valid JSON:
{
  "valid": true|false,
  "issues": ["list", "of", "issues"],
  "suggestions": ["improvement", "ideas"],
  "security_rating": "high|medium|low"
}"""

            user_prompt = f"Validate this webhook config:\n{json.dumps(current_config, indent=2)}"
        else:
            raise ValueError(f"Unknown action: {action}")

        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"
        response = await self._call_ai(full_prompt)
        result = self._parse_response(response)
        return {"action": action, "result": result}

    async def explain_error(
        self,
        step_type: str,
        step_config: Dict,
        error_message: str,
        input_data_sample: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Diagnose a workflow run failure"""
        kb_domains = ["steering.master", "debugging.error_analysis"]
        node_kb = self._get_node_kb_domain(step_type)
        if node_kb != f"nodes.{step_type}":
            kb_domains.append(node_kb)

        kb_context = self._get_relevant_kb(kb_domains)

        system_prompt = """Diagnose a workflow step failure and suggest a fix.

Output must be valid JSON:
{
  "explanation": "Plain English explanation of what went wrong",
  "root_cause": "Specific cause identified",
  "suggested_fix": "Description of how to fix it",
  "fixed_config": { /* corrected step configuration if applicable */ }
}"""

        user_prompt = f"Step type: {step_type}\nConfig: {json.dumps(step_config, indent=2)}\nError: {error_message}"
        if input_data_sample:
            user_prompt += f"\nInput data sample: {json.dumps(input_data_sample, indent=2)}"

        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"
        response = await self._call_ai(full_prompt)
        result = self._parse_response(response)
        return result

    async def generate_condition_expression(self, description: str, input_data: Optional[Dict] = None) -> str:
        """Generate a Python condition expression from natural language description.

        This is called by AIConditionExecutor at runtime to evaluate conditions dynamically.
        """
        kb_context = self._get_relevant_kb(["steering.master", "nodes.condition"])

        system_prompt = """Generate a Python condition expression that evaluates to True or False.

The expression will be evaluated against a "data" dictionary containing the step's input data.

Output must be ONLY the expression string, valid JSON:
{
  "expression": "data['field'] > 5 and data['status'] == 'active'"
}

Rules:
1. Use data['field_name'] syntax to access values
2. Use data.get('field_name', default) for optional fields
3. Keep expressions simple and readable
4. The expression must evaluate to a boolean"""

        user_prompt = f"Generate a condition expression for: {description}"
        if input_data:
            sample_keys = list(str(k) for k in list(input_data.keys())[:10])
            user_prompt += f"\nAvailable data keys: {sample_keys}"

        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"
        response = await self._call_ai(full_prompt)
        result = self._parse_response(response)
        return result.get("expression", "True")

    # ------------------------------------------------------------------
    # Internal helpers (preserved from original)
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """Build system prompt with knowledge base context"""
        return """You are an expert workflow step generator. Generate a single workflow step based on the user's description.

Available step types:
- api_call: Make HTTP requests (GET, POST, PUT, DELETE, PATCH)
- database_query: Query or modify database (SELECT, INSERT, UPDATE, DELETE, UPSERT)
- email: Send email notifications with templates
- form: Collect data via forms with validation
- condition: Branch based on conditions using Python expressions
- delay: Wait for a specified duration
- webhook: Handle webhook callbacks
- custom_code: Execute custom Python code (sandboxed)

Output must be valid JSON with this structure:
{
  "step_type": "<type>",
  "definition": {
    // type-specific configuration
  },
  "condition_expr": "<optional linear-skip expression>"
}

Condition steps use branching routes. Their "definition" must be:
{
  "routes": [
    {"expression": "data['field'] > 5", "target_step_id": null}
  ],
  "default_target_step_id": null
}

Rules:
1. Choose the most appropriate step type for the task
2. Provide sensible defaults for all fields
3. Condition expressions are Python expressions over "data" (the current step input) using data['field'] syntax
4. For condition steps, put the expression inside "routes", never in "condition_expr"
5. Keep condition expressions simple (Python syntax)
6. Include error handling where appropriate"""

    def _build_user_prompt(self, description: str, context: Optional[Dict] = None) -> str:
        """Build user prompt with context"""
        prompt = f"Generate a workflow step for this description:\n{description}"
        if context:
            prompt += f"\n\nContext:\n{json.dumps(context, indent=2)}"
        return prompt

    def _validate_step(self, step: Dict[str, Any]) -> None:
        """Validate a generated step"""
        if "step_type" not in step:
            raise ValueError("Step must have 'step_type'")
        if step["step_type"] not in self.VALID_STEP_TYPES:
            raise ValueError(f"Invalid step type: {step['step_type']}. Valid types: {list(self.VALID_STEP_TYPES.keys())}")
        required_fields = self.VALID_STEP_TYPES[step["step_type"]]
        for field in required_fields:
            if field not in step.get("definition", {}):
                raise ValueError(f"Missing required field '{field}' for step type '{step['step_type']}'")

    def _validate_workflow(self, workflow: Dict[str, Any]) -> None:
        """Validate a generated workflow"""
        if "name" not in workflow:
            raise ValueError("Workflow must have a 'name'")
        if "steps" not in workflow:
            raise ValueError("Workflow must have 'steps'")
        for i, step in enumerate(workflow["steps"]):
            try:
                self._validate_step(step)
            except ValueError as e:
                raise ValueError(f"Invalid step {i}: {str(e)}")

    def _validate_form_schema(self, schema: Dict[str, Any]) -> None:
        """Validate a generated form schema"""
        if schema.get("type") != "object":
            raise ValueError("Form schema must have type 'object'")
        if "properties" not in schema:
            raise ValueError("Form schema must have 'properties'")
        for field_name, field_def in schema["properties"].items():
            if "type" not in field_def:
                raise ValueError(f"Field '{field_name}' must have a 'type'")
            if field_def["type"] not in ["string", "number", "integer", "boolean", "object", "array",
                                          "email", "textarea", "select", "info", "date", "date-time", "file"]:
                raise ValueError(f"Field '{field_name}' has invalid type: {field_def['type']}")

    async def _call_llama_cpp(self, prompt: str) -> str:
        """Call llama.cpp server with retry logic"""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "max_tokens": 2000,
            "temperature": 0.2,
            "stop": ["```"],
            "stream": False
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v1/completions",
                    json=payload,
                    timeout=60.0
                )
                response.raise_for_status()
                return response.json()["choices"][0]["text"]
            except httpx.TimeoutException:
                raise ValueError("AI service request timed out")
            except httpx.HTTPError as e:
                raise ValueError(f"AI service error: {str(e)}")

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API with retry logic"""
        if not system_settings.openai_api_key:
            raise ValueError("OpenAI API key not configured")

        headers = {
            "Authorization": f"Bearer {system_settings.openai_api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": system_settings.openai_model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that generates JSON responses."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 2000,
            "temperature": 0.2
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{system_settings.openai_base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60.0
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
            except httpx.TimeoutException:
                raise ValueError("OpenAI request timed out")
            except httpx.HTTPError as e:
                raise ValueError(f"OpenAI error: {str(e)}")

    async def _call_ai(self, prompt: str) -> str:
        """Call AI service based on configured provider"""
        if system_settings.ai_provider == "openai":
            return await self._call_openai(prompt)
        else:
            return await self._call_llama_cpp(prompt)

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse AI response into structured data"""
        try:
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            return json.loads(response_text.strip())
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response from AI: {str(e)}\nResponse: {response_text[:500]}")


# Singleton instance
    async def assist_ci_type_schema(
        self,
        action: str,
        description: Optional[str] = None,
        current_schema: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Assist with CI type schema generation and validation"""
        kb_context = self._get_relevant_kb(["steering.master", "cmdb.ci_type_schema"])

        if action == "generate":
            system_prompt = """Generate a CI type field schema from the description.


ai_service = AIService()

Output must be valid JSON:
{
  "key": "type_key",
  "name": "Type Name",
  "description": "Description",
  "icon": "emoji",
  "fields": [
    {
      "key": "field_key",
      "label": "Field Label",
      "type": "string|number|select|...",
      "required": true,
      "help_text": "Optional help text",
      "options": ["opt1", "opt2"]  // For select type
    }
  ]
}

Rules:
1. Use snake_case for field keys
2. Include common fields like name, status, owner
3. Use lookup type for references to users or other CIs
4. Add help_text for complex fields
5. Keep required fields to a minimum"""

            user_prompt = f"Generate CI type schema: {description}"
        elif action == "validate":
            system_prompt = """Validate the following CI type schema. Check for:
- Valid field types
- Required fields marked appropriately
- Consistent naming conventions
- Missing help text for complex fields

Output must be valid JSON:
{
  "valid": true,
  "issues": ["list", "of", "issues"],
  "suggestions": ["improvement", "ideas"]
}"""

            user_prompt = f"Validate this CI type schema:\n{json.dumps(current_schema, indent=2)}"
        else:
            raise ValueError(f"Unknown action: {action}")

        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"
        response = await self._call_ai(full_prompt)
        result = self._parse_response(response)
        return {"action": action, "result": result}

    async def assist_task_assignment(
        self,
        action: str,
        description: Optional[str] = None,
        current_config: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Assist with task assignment and priority configuration"""
        kb_context = self._get_relevant_kb(["steering.master", "tasks.assignment"])

        if action == "suggest":
            system_prompt = """Suggest task assignment configuration.

Output must be valid JSON:
{
  "assigned_to_user_id": "user_id or expression",
  "assignment_type": "direct|group|dynamic|round_robin",
  "priority": 1-5,
  "escalation_rules": [{"after_hours": 2, "notify": ["admin"]}]
}"""
            user_prompt = f"Suggest task assignment: {description}"
        elif action == "improve":
            system_prompt = """Improve task assignment configuration.

Output must be valid JSON:
{
  "suggestions": ["list", "of", "improvements"],
  "improved_config": { /* improved config */ }
}"""
            user_prompt = f"Improve this task assignment:\n{json.dumps(current_config, indent=2)}"
        else:
            raise ValueError(f"Unknown action: {action}")

        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"
        response = await self._call_ai(full_prompt)
        result = self._parse_response(response)
        return {"action": action, "result": result}

    async def assist_ldap_filter(
        self,
        action: str,
        description: Optional[str] = None,
        current_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Assist with LDAP filter generation and validation"""
        kb_context = self._get_relevant_kb(["steering.master", "ldap.filter"])

        if action == "generate":
            system_prompt = """Generate an LDAP filter.

Output must be valid JSON:
{
  "filter": "(uid=*)",
  "description": "What this filter does",
  "search_command": "ldapsearch ...",
  "expected_results": "Description of matches"
}"""
            user_prompt = f"Generate LDAP filter: {description}"
        elif action == "validate":
            system_prompt = """Validate an LDAP filter.

Output must be valid JSON:
{
  "valid": true,
  "issues": ["list", "of", "issues"],
  "suggestions": ["improvement", "ideas"]
}"""
            user_prompt = f"Validate this LDAP filter:\n{current_filter}"
        else:
            raise ValueError(f"Unknown action: {action}")

        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"
        response = await self._call_ai(full_prompt)
        result = self._parse_response(response)
        return {"action": action, "result": result}

    async def assist_marketplace(
        self,
        action: str,
        description: Optional[str] = None,
        current_item: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Assist with marketplace item descriptions"""
        kb_context = self._get_relevant_kb(["steering.master", "marketplace.description"])

        if action == "generate":
            system_prompt = """Generate marketplace item metadata.

Output must be valid JSON:
{
  "name": "Item Name",
  "description": "3-5 sentence description",
  "category": "hr|it|finance|...",
  "tags": ["tag1", "tag2"],
  "version": "1.0"
}"""
            user_prompt = f"Generate marketplace item: {description}"
        elif action == "improve":
            system_prompt = """Improve marketplace item metadata.

Output must be valid JSON:
{
  "suggestions": ["improvement", "ideas"],
  "improved_item": { /* improved metadata */ }
}"""
            user_prompt = f"Improve this marketplace item:\n{json.dumps(current_item, indent=2)}"
        else:
            raise ValueError(f"Unknown action: {action}")

        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"
        response = await self._call_ai(full_prompt)
        result = self._parse_response(response)
        return {"action": action, "result": result}

    async def assist_email_template(
        self,
        action: str,
        description: Optional[str] = None,
        current_template: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Assist with email template generation"""
        kb_context = self._get_relevant_kb(["steering.master", "email.template"])

        if action == "generate":
            system_prompt = """Generate an email template.

Output must be valid JSON:
{
  "name": "Template Name",
  "subject": "Email subject",
  "body_html": "<html>...</html>",
  "body_text": "Plain text version",
  "variables": ["var1", "var2"]
}"""
            user_prompt = f"Generate email template: {description}"
        elif action == "improve":
            system_prompt = """Improve an email template.

Output must be valid JSON:
{
  "suggestions": ["improvement", "ideas"],
  "improved_template": { /* improved template */ }
}"""
            user_prompt = f"Improve this email template:\n{json.dumps(current_template, indent=2)}"
        else:
            raise ValueError(f"Unknown action: {action}")

        full_prompt = f"{kb_context}\n\n{system_prompt}\n\n{user_prompt}"
        response = await self._call_ai(full_prompt)
        result = self._parse_response(response)
        return {"action": action, "result": result}


# Singleton instance
ai_service = AIService()
