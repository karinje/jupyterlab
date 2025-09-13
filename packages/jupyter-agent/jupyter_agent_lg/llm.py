"""
LLM Router and Provider implementations for LangGraph Agent

Provides unified interface for multiple LLM providers (OpenAI, Anthropic, Google)
with structured output support for decision making.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Type
from pydantic import BaseModel, Field

# LangGraph/LangChain imports for proper LLM integration
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from .state import Decision

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    @abstractmethod
    async def generate_with_structured_output(
        self,
        prompt: str,
        output_schema: Type[BaseModel],
        system_prompt: Optional[str] = None,
    ) -> BaseModel:
        """Generate response with structured output"""
        pass

    @abstractmethod
    async def generate_text(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> str:
        """Generate plain text response"""
        pass


class DecisionSchema(BaseModel):
    """Pydantic schema for LLM decision output"""

    action: str = Field(description="The action to take")
    params: Dict[str, Any] = Field(
        default_factory=dict, description="Action parameters as key-value pairs"
    )
    reasoning: str = Field(description="Explanation of why this action was chosen")
    status_message: str = Field(description="Status message to show the user")
    confidence: float = Field(
        default=0.8, ge=0.0, le=1.0, description="Confidence in this decision"
    )


class PlanStepSchema(BaseModel):
    """Schema for individual plan steps"""

    title: str = Field(description="Title of this step")
    description: str = Field(description="Detailed description of what this step does")


class PlanSchema(BaseModel):
    """Pydantic schema for analysis plan output"""

    title: str = Field(description="Overall title of the analysis plan")
    description: str = Field(description="Description of what the plan will accomplish")
    steps: List[PlanStepSchema] = Field(description="List of steps to execute")


class OpenAILLM(LLMProvider):
    """OpenAI LLM provider using LangChain integration"""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        super().__init__(api_key, model)
        self.llm = ChatOpenAI(api_key=api_key, model=model, temperature=0.1)
        logger.info(f"🤖 Initialized OpenAI LLM with model: {model}")

    async def generate_with_structured_output(
        self,
        prompt: str,
        output_schema: Type[BaseModel],
        system_prompt: Optional[str] = None,
    ) -> BaseModel:
        """Generate response with structured output using LangChain"""
        try:
            # Create parser for the output schema
            parser = PydanticOutputParser(pydantic_object=output_schema)

            # Create prompt template with format instructions
            prompt_template = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt or "You are a helpful assistant."),
                    ("human", "{query}\n\n{format_instructions}"),
                ]
            )

            # Create the chain
            chain = prompt_template | self.llm | parser

            logger.info(f"🤖 OpenAI Request - Model: {self.model}")
            logger.info(f"📤 Prompt: {prompt[:500]}...")
            logger.info(f"📋 Schema: {output_schema.__name__}")

            # Generate and parse response
            parsed_response = await chain.ainvoke(
                {
                    "query": prompt,
                    "format_instructions": parser.get_format_instructions(),
                }
            )

            logger.info(f"📥 OpenAI Parsed Response: {parsed_response}")

            return parsed_response

        except Exception as e:
            logger.error(f"❌ OpenAI structured output error: {e}")
            # Fallback to basic JSON parsing
            return await self._fallback_structured_output(
                prompt, output_schema, system_prompt
            )

    async def generate_text(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> str:
        """Generate plain text response"""
        try:
            # Create prompt template
            prompt_template = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt or "You are a helpful assistant."),
                    ("human", "{query}"),
                ]
            )

            # Create the chain
            chain = prompt_template | self.llm

            # Generate response
            response = await chain.ainvoke({"query": prompt})
            return response.content

        except Exception as e:
            logger.error(f"❌ OpenAI text generation error: {e}")
            raise

    async def _fallback_structured_output(
        self,
        prompt: str,
        output_schema: Type[BaseModel],
        system_prompt: Optional[str] = None,
    ) -> BaseModel:
        """Fallback structured output using JSON parsing"""
        try:
            schema_json = output_schema.model_json_schema()
            structured_prompt = f"""
{prompt}

Please respond with a valid JSON object that matches this schema:
{json.dumps(schema_json, indent=2)}

Response (JSON only):
"""

            text_response = await self.generate_text(structured_prompt, system_prompt)

            # Extract JSON from response
            json_start = text_response.find("{")
            json_end = text_response.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                json_str = text_response[json_start:json_end]
                data = json.loads(json_str)
                return output_schema(**data)
            else:
                raise ValueError("No valid JSON found in response")

        except Exception as e:
            logger.error(f"❌ Fallback structured output failed: {e}")
            # Return minimal valid response
            if output_schema == DecisionSchema:
                return DecisionSchema(
                    action="complete_analysis",
                    params={},
                    reasoning="Error occurred, completing analysis",
                    status_message="Error in LLM processing",
                )
            else:
                raise


class AnthropicLLM(LLMProvider):
    """Anthropic Claude LLM provider"""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        super().__init__(api_key, model)
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        logger.info(f"🤖 Initialized Anthropic LLM with model: {model}")

    async def generate_with_structured_output(
        self,
        prompt: str,
        output_schema: Type[BaseModel],
        system_prompt: Optional[str] = None,
    ) -> BaseModel:
        """Generate response with structured output using JSON parsing"""
        try:
            schema_json = output_schema.model_json_schema()
            structured_prompt = f"""
{prompt}

Please respond with a valid JSON object that matches this schema:
{json.dumps(schema_json, indent=2)}

Response (JSON only):
"""

            text_response = await self.generate_text(structured_prompt, system_prompt)

            # Extract JSON from response
            json_start = text_response.find("{")
            json_end = text_response.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                json_str = text_response[json_start:json_end]
                data = json.loads(json_str)
                return output_schema(**data)
            else:
                raise ValueError("No valid JSON found in response")

        except Exception as e:
            logger.error(f"❌ Anthropic structured output error: {e}")
            # Return minimal valid response
            if output_schema == DecisionSchema:
                return DecisionSchema(
                    action="complete_analysis",
                    params={},
                    reasoning="Error occurred, completing analysis",
                    status_message="Error in LLM processing",
                )
            else:
                raise

    async def generate_text(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> str:
        """Generate plain text response"""
        try:
            message = await self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                system=system_prompt or "You are a helpful data analysis assistant.",
                messages=[{"role": "user", "content": prompt}],
            )

            return message.content[0].text

        except Exception as e:
            logger.error(f"❌ Anthropic text generation error: {e}")
            raise


class GoogleLLM(LLMProvider):
    """Google Gemini LLM provider"""

    def __init__(self, api_key: str, model: str = "gemini-1.5-pro"):
        super().__init__(api_key, model)
        # TODO: Initialize Google Gemini client when available
        logger.info(f"🤖 Initialized Google LLM with model: {model} (placeholder)")

    async def generate_with_structured_output(
        self,
        prompt: str,
        output_schema: Type[BaseModel],
        system_prompt: Optional[str] = None,
    ) -> BaseModel:
        """Generate response with structured output"""
        # TODO: Implement Google Gemini structured output
        raise NotImplementedError("Google LLM not yet implemented")

    async def generate_text(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> str:
        """Generate plain text response"""
        # TODO: Implement Google Gemini text generation
        raise NotImplementedError("Google LLM not yet implemented")


class LLMRouter:
    """Routes requests to appropriate LLM provider"""

    def __init__(self):
        self.providers: Dict[str, LLMProvider] = {}
        logger.info("🎯 Initialized LLM Router")

    def register_provider(self, provider_name: str, provider: LLMProvider):
        """Register an LLM provider"""
        self.providers[provider_name] = provider
        logger.info(f"✅ Registered {provider_name} provider")

    def get_provider(self, provider_name: str) -> LLMProvider:
        """Get provider by name"""
        if provider_name not in self.providers:
            raise ValueError(f"Provider {provider_name} not registered")
        return self.providers[provider_name]

    def get_available_providers(self) -> List[str]:
        """Get list of available provider names"""
        return list(self.providers.keys())

    async def generate_decision(
        self, context: Dict[str, Any], provider: str = "openai"
    ) -> Decision:
        """Generate analysis decision using specified provider"""
        try:
            llm = self.get_provider(provider)

            # Create comprehensive prompt for decision making
            prompt = self._create_decision_prompt(context)
            system_prompt = self._create_system_prompt()

            logger.info(f"🧠 Decision Prompt: {prompt[:500]}...")
            logger.info(f"⚙️ System Prompt: {system_prompt[:200]}...")

            # Get structured decision from LLM
            decision_schema = await llm.generate_with_structured_output(
                prompt, DecisionSchema, system_prompt
            )

            # Convert to Decision object
            decision = Decision(
                action=decision_schema.action,
                params=decision_schema.params,
                reasoning=decision_schema.reasoning,
                status_message=decision_schema.status_message,
                confidence=decision_schema.confidence,
            )

            logger.info(
                f"🎯 LLM Decision: {decision.action} - {decision.status_message}"
            )
            return decision

        except Exception as e:
            logger.error(f"❌ Decision generation failed: {e}")
            # Return safe fallback decision
            return Decision(
                action="complete_analysis",
                params={},
                reasoning=f"Error in decision making: {e}",
                status_message="Completing due to error",
            )

    def _create_decision_prompt(self, context: Dict[str, Any]) -> str:
        """Create comprehensive prompt for LLM decision making"""
        user_request = context.get("original_request", "No request")

        return f"""
Analyze this user message and decide what to do: "{user_request}"

CURRENT CONTEXT:
- User Request: {user_request}
- Notebook Path: {context.get("notebook_path", "Unknown")}
- Current Iteration: {context.get("current_iteration", 0)}
- Total Cells: {len(context.get("notebook_cells", []))}
- Has Plan: {"Yes" if context.get("plan") else "No"}

PLAN STATUS:
{self._format_plan_status(context.get("plan"), context.get("completed_steps", []))}

NOTEBOOK CELLS:
{self._format_notebook_cells(context.get("notebook_cells", []))}

CONVERSATION HISTORY:
{self._format_conversation_history(context.get("conversation_history", []))}

DECISION LOGIC:
- For greetings like "hi", "hello", "thanks" → Use "respond" action
- For data analysis requests → Use "create_plan" or other analysis actions
- Look at the actual user message to determine intent

Choose the most appropriate action based on what the user actually said.
"""

    def _create_system_prompt(self) -> str:
        """Create system prompt for the LLM"""
        return """
You are a helpful data analysis assistant for JupyterLab.

CRITICAL: Read the user's message carefully and respond appropriately:

FOR SIMPLE CONVERSATION (greetings, casual chat, questions):
- Messages like "hi", "hello", "how are you", "thanks" → Use "respond" action
- Be friendly and conversational

FOR CODE EXECUTION REQUESTS:
- Direct requests like "plot x and y", "calculate this", "run this code" → Use "execute_code" DIRECTLY
- Simple plotting, calculations, single tasks → Use "execute_code"

FOR COMPLEX ANALYSIS REQUESTS:
- Only when user asks for multi-step analysis, data exploration, or complex workflows
- Look for keywords like "analyze dataset", "explore data", "full analysis"
- Then use "create_plan" first

AVAILABLE ACTIONS:
- "respond": For greetings, casual chat, questions (params: {{"message": "your response"}})
- "execute_code": Run Python code directly (params: {{"code": "python code", "description": "what this does"}})
- "create_plan": Only for complex multi-step analysis (params: {{}})
- "query_data": Query available data (params: {{"query": "description of what to find"}})
- "create_visualization": Make charts/plots (params: {{"type": "chart type", "description": "what to visualize"}})
- "complete_analysis": Finish analysis (params: {{}})

PARAMS FORMAT: Always provide params as a JSON object, even if empty: "{{}}"

You must respond with a valid JSON object matching the required schema.
"""

    def _format_conversation_history(self, history: List[Dict]) -> str:
        """Format conversation history for prompt"""
        if not history:
            return "No previous conversation"

        # Show last 5 messages for context
        recent_history = history[-5:]
        formatted = []

        for msg in recent_history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:200]  # Truncate long messages
            formatted.append(f"{role.upper()}: {content}")

        return "\n".join(formatted)

    def _format_plan_status(self, plan: List[Dict], completed_steps: List[str]) -> str:
        """Format plan status for LLM context"""
        if not plan:
            return "No plan created yet"

        status_lines = []
        for i, step in enumerate(plan, 1):
            step_id = step.get("step_id", f"step_{i}")
            title = step.get("title", "Unknown step")
            status = "✅ COMPLETED" if step_id in completed_steps else "⏳ PENDING"
            status_lines.append(f"{i}. {title} - {status}")

        next_step = None
        for step in plan:
            step_id = step.get("step_id", "")
            if step_id not in completed_steps:
                next_step = step.get("title", "Unknown step")
                break

        result = "PLAN STEPS:\n" + "\n".join(status_lines)
        if next_step:
            result += f"\n\nNEXT STEP TO EXECUTE: {next_step}"
        else:
            result += "\n\nALL STEPS COMPLETED"

        return result

    def _format_notebook_cells(self, cells: List[Dict]) -> str:
        """Format notebook cells for LLM context"""
        if not cells:
            return "No cells in notebook yet"

        cell_summaries = []
        for cell in cells:
            cell_type = cell.get("type", "unknown")
            source = cell.get("source", "")[:200]  # Truncate long content
            outputs = cell.get("outputs", [])

            if cell_type == "markdown":
                cell_summaries.append(f"MARKDOWN: {source}")
            elif cell_type == "code":
                exec_count = cell.get("execution_count")
                status = f"[{exec_count}]" if exec_count else "[not executed]"
                has_output = "with output" if outputs else "no output"
                cell_summaries.append(f"CODE {status}: {source} ({has_output})")

        return "\n".join(cell_summaries)

    async def generate_plan(
        self, request: str, context: Dict[str, Any], provider: str = "openai"
    ) -> List[PlanStepSchema]:
        """Generate analysis plan using specified provider"""
        try:
            llm = self.get_provider(provider)

            prompt = f"""
Create a detailed analysis plan for this request: "{request}"

Context:
- Notebook has {len(context.get("notebook_cells", []))} cells
- Available data sources: {len(context.get("available_data_sources", []))}

Create a step-by-step plan with 3-7 concrete, actionable steps.
Each step should have a clear title and detailed description.
"""

            system_prompt = "You are an expert data analyst creating analysis plans."

            plan_schema = await llm.generate_with_structured_output(
                prompt, PlanSchema, system_prompt
            )

            return plan_schema.steps

        except Exception as e:
            logger.error(f"❌ Plan generation failed: {e}")
            # Return basic fallback plan
            return [
                {
                    "title": "Explore Data",
                    "description": "Load and examine the dataset",
                },
                {
                    "title": "Analyze Patterns",
                    "description": "Identify key patterns and trends",
                },
                {
                    "title": "Create Visualizations",
                    "description": "Generate charts and plots",
                },
                {"title": "Summarize Findings", "description": "Document key insights"},
            ]
