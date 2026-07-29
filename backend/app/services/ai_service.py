"""
AI integration service for generating workflow steps using llama.cpp
"""
import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


class AIService:
    """Service for AI-powered workflow step generation"""
    
    # Valid step types and their required fields
    VALID_STEP_TYPES = {
        "api_call": ["method", "url"],
        "database_query": ["type", "table"],
        "email": ["to", "subject"],
        "form": ["form_id"],
        "condition": ["expression"],
        "delay": ["seconds"],
        "webhook": ["url"],
        "custom_code": ["code"]
    }
    
    def __init__(self):
        self.base_url = settings.llama_cpp_url
        self.model = settings.llama_cpp_model
        self.knowledge_base = self._load_knowledge_base()
    
    def _load_knowledge_base(self) -> Dict[str, Any]:
        """Load knowledge base from files"""
        kb = {
            "prompts": {},
            "templates": []
        }
        
        # Load prompts
        prompts_path = Path("knowledge-base/prompts")
        if prompts_path.exists():
            for file in prompts_path.glob("*.md"):
                kb["prompts"][file.stem] = file.read_text()
        
        # Load templates
        templates_path = Path("knowledge-base/templates")
        if templates_path.exists():
            for file in templates_path.glob("*.json"):
                try:
                    kb["templates"].append(json.loads(file.read_text()))
                except:
                    pass
        
        return kb
    
    async def generate_step(self, description: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate a workflow step from natural language description"""
        
        # Enhance prompt with knowledge base
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(description, context)
        
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        try:
            response = await self._call_llama_cpp(full_prompt)
            step = self._parse_response(response)
            
            # Validate the generated step
            self._validate_step(step)
            
            return step
        except Exception as e:
            logger.error(f"AI step generation failed: {str(e)}")
            raise ValueError(f"Failed to generate step: {str(e)}")
    
    async def generate_workflow(self, description: str, template_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Generate a complete workflow from description"""
        
        # Check if we have a matching template
        template = None
        if template_name:
            template = next((t for t in self.knowledge_base["templates"] if t.get("name") == template_name), None)
        
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
      "condition_expr": "<optional condition>"
    }
  ]
}

Rules:
1. Choose appropriate step types for each step
2. Steps should flow logically (API → DB → Email, etc.)
3. Use $input.variable and $output.variable syntax
4. Add conditions for error handling and branching
5. Include delay steps where appropriate"""

        user_prompt = f"Generate a workflow for this description:\n{description}"
        
        if template:
            user_prompt += f"\n\nUse this template as reference:\n{json.dumps(template, indent=2)}"
        
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        try:
            response = await self._call_llama_cpp(full_prompt)
            workflow = self._parse_response(response)
            
            # Validate the generated workflow
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
      "type": "<string|number|boolean|integer>",
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

Common field types:
- string: Text input, email, phone, URL
- number: Decimal values
- integer: Whole numbers
- boolean: Yes/No checkboxes
- object: Nested data (address, etc.)

Rules:
1. Use appropriate field types
2. Provide clear titles and descriptions
3. Mark essential fields as required
4. Add validation (minLength, pattern, etc.) where needed
5. Keep the form simple and focused"""

        user_prompt = f"Generate a form schema for this description:\n{description}"
        
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        try:
            response = await self._call_llama_cpp(full_prompt)
            schema = self._parse_response(response)
            
            # Validate the generated schema
            self._validate_form_schema(schema)
            
            return schema
        except Exception as e:
            logger.error(f"AI form generation failed: {str(e)}")
            raise ValueError(f"Failed to generate form schema: {str(e)}")
    
    def _build_system_prompt(self) -> str:
        """Build system prompt with knowledge base context"""
        
        base_prompt = """You are an expert workflow step generator. Generate a single workflow step based on the user's description.

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
  "condition_expr": "<optional condition expression>"
}

Rules:
1. Choose the most appropriate step type for the task
2. Provide sensible defaults for all fields
3. Use $input.variable syntax to reference workflow input data
4. Use $output.variable syntax to reference previous step output
5. Keep condition expressions simple (Python syntax)
6. Include error handling where appropriate"""
        
        # Add relevant template if available
        if self.knowledge_base["templates"]:
            base_prompt += "\n\nReference templates are available for common patterns."
        
        return base_prompt
    
    def _build_user_prompt(self, description: str, context: Optional[Dict] = None) -> str:
        """Build user prompt with context"""
        
        prompt = f"Generate a workflow step for this description:\n{description}"
        
        if context:
            prompt += f"\n\nContext:\n{json.dumps(context, indent=2)}"
        
        # Add examples from knowledge base
        if self.knowledge_base["prompts"]:
            prompt += "\n\nFollow the patterns in the knowledge base."
        
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
            if field_def["type"] not in ["string", "number", "integer", "boolean", "object"]:
                raise ValueError(f"Field '{field_name}' has invalid type: {field_def['type']}")
    
    async def _call_llama_cpp(self, prompt: str) -> str:
        """Call llama.cpp server with retry logic"""
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "max_tokens": 2000,
            "temperature": 0.2,  # Lower for more deterministic output
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
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse AI response into structured data"""
        
        # Try to extract JSON from response
        try:
            # Remove markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            
            # Parse JSON
            return json.loads(response_text.strip())
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response from AI: {str(e)}\nResponse: {response_text[:500]}")


# Singleton instance
ai_service = AIService()
