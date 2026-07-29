"""
AI integration service for generating workflow steps using llama.cpp
"""
import json
import logging
from typing import Dict, Any, Optional
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


class AIService:
    """Service for AI-powered workflow step generation"""
    
    def __init__(self):
        self.base_url = settings.llama_cpp_url
        self.model = settings.llama_cpp_model
    
    async def generate_step(self, description: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate a workflow step from natural language description"""
        
        prompt = self._build_step_generation_prompt(description, context)
        
        try:
            response = await self._call_llama_cpp(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"AI step generation failed: {str(e)}")
            raise ValueError(f"Failed to generate step: {str(e)}")
    
    async def generate_form_schema(self, description: str) -> Dict[str, Any]:
        """Generate a JSON schema for a form from description"""
        
        prompt = self._build_form_generation_prompt(description)
        
        try:
            response = await self._call_llama_cpp(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"AI form generation failed: {str(e)}")
            raise ValueError(f"Failed to generate form schema: {str(e)}")
    
    def _build_step_generation_prompt(self, description: str, context: Optional[Dict] = None) -> str:
        """Build prompt for step generation"""
        
        system_prompt = """You are a workflow step generator. Generate a single workflow step based on the user's description.

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
  "step_type": "<type>",
  "definition": {
    // type-specific configuration
  },
  "condition_expr": "<optional condition expression>"
}

Rules:
1. Choose the most appropriate step type
2. Provide sensible defaults for all fields
3. Use $input.variable syntax to reference workflow data
4. Keep condition expressions simple (Python syntax)"""

        user_prompt = f"Generate a workflow step for this description:\n{description}"
        
        if context:
            user_prompt += f"\n\nContext: {json.dumps(context)}"
        
        return f"{system_prompt}\n\n{user_prompt}"
    
    def _build_form_generation_prompt(self, description: str) -> str:
        """Build prompt for form schema generation"""
        
        system_prompt = """You are a form schema generator. Generate a JSON Schema for a form based on the user's description.

Output must be valid JSON with this structure:
{
  "type": "object",
  "properties": {
    "<field_name>": {
      "type": "<string|number|boolean|integer>",
      "title": "<Human readable title>",
      "description": "<Field description>",
      "required": <true|false>
    }
  },
  "required": ["<list of required field names>"]
}

Rules:
1. Use appropriate field types
2. Provide clear titles and descriptions
3. Mark essential fields as required
4. Keep the form simple and focused"""

        user_prompt = f"Generate a form schema for this description:\n{description}"
        
        return f"{system_prompt}\n\n{user_prompt}"
    
    async def _call_llama_cpp(self, prompt: str) -> str:
        """Call llama.cpp server"""
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "max_tokens": 1000,
            "temperature": 0.3,  # Lower temperature for more deterministic output
            "stop": ["```"],
            "stream": False
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v1/completions",
                json=payload,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()["choices"][0]["text"]
    
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
            raise ValueError(f"Invalid JSON response from AI: {str(e)}")


# Singleton instance
ai_service = AIService()
