"""
SAP AI Documentation Assistant using GenAI Hub Orchestration Service

This module handles the LLM-based documentation assistance using tool calling:
1. User asks a question about SAP AI services
2. LLM calls search_knowledge_base() tool to find relevant docs
3. Python executes the tool against knowledge_base.json
4. LLM receives search results and writes a detailed answer with doc references

Uses Orchestration Service features:
- Structured prompts (SystemMessage/UserMessage)
- JSON schema response formatting
- Tool calling (function tools)
- Content filtering (Azure Content Safety)
- Data masking (PII anonymization)
"""

import json
import logging
import re

from dotenv import load_dotenv

# Load environment variables from .env file (for local development)
# This must happen before any GenAI Hub SDK imports that read AICORE_* vars
load_dotenv()

from knowledge_base import (
    search_knowledge_base,
    get_docs_by_ids,
    get_all_doc_ids,
    get_services_summary,
)

# Lazy imports for GenAI Hub Orchestration SDK V2 (may not be available locally)
try:
    from gen_ai_hub.orchestration_v2.service import OrchestrationService
    from gen_ai_hub.orchestration_v2.models.message import (
        SystemMessage,
        UserMessage,
        ToolChatMessage,
    )
    from gen_ai_hub.orchestration_v2.models.template import Template, PromptTemplatingModuleConfig
    from gen_ai_hub.orchestration_v2.models.llm_model_details import LLMModelDetails
    from gen_ai_hub.orchestration_v2.models.config import ModuleConfig, OrchestrationConfig
    from gen_ai_hub.orchestration_v2.models.response_format import ResponseFormatJsonSchema, JSONResponseSchema
    from gen_ai_hub.orchestration_v2.models.content_filtering import (
        ContentFilter,
        FilteringModuleConfig,
        InputFiltering,
        OutputFiltering,
    )
    from gen_ai_hub.orchestration_v2.models.azure_content_filter import (
        AzureContentFilter,
        AzureThreshold,
    )
    from gen_ai_hub.orchestration_v2.models.data_masking import (
        MaskingModuleConfig,
        MaskingProviderConfig,
        MaskingMethod,
        ProfileEntity,
        DPIStandardEntity,
    )
    from gen_ai_hub.orchestration_v2.exceptions import OrchestrationError

    GENAI_HUB_AVAILABLE = True
except ImportError:
    GENAI_HUB_AVAILABLE = False
    OrchestrationError = Exception  # Fallback for type checking

logger = logging.getLogger(__name__)

# JSON schema for the final LLM response (after tool calling)
ASSISTANT_SCHEMA = {
    "type": "object",
    "properties": {
        "is_sap_ai": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "services": {"type": "array", "items": {"type": "string"}},
        "doc_ids": {"type": "array", "items": {"type": "string"}},
        "answer": {"type": "string"},
    },
    "required": ["is_sap_ai", "confidence", "services", "doc_ids", "answer"],
    "additionalProperties": False,
}

# Tool definition for the LLM — describes search_knowledge_base as a callable function
SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_knowledge_base",
        "description": "Search the SAP AI documentation knowledge base for relevant documentation entries. Returns matching docs with titles, URLs, and descriptions.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search terms related to the user's question",
                },
                "service": {
                    "type": "string",
                    "description": "Optional service key to filter results. One of: ai_core, genai_hub, ai_launchpad, joule, hana_cloud_vector, document_processing",
                },
            },
            "required": ["query"],
        },
    },
}


class DocAssistant:
    """Answers SAP AI documentation questions using GPT-4o via Orchestration Service with tool calling."""

    def __init__(self):
        """Initialize the assistant with GenAI Hub Orchestration Service."""
        self._service = None
        self._initialize_client()

    def _create_template(self) -> "Template":
        """Create the prompt template with system and user messages + tool definition."""
        services_summary = get_services_summary()

        return Template(
            template=[
                SystemMessage(
                    content=f"""You are an SAP AI documentation expert assistant.
Your job is to help users find relevant SAP documentation and provide detailed explanations.

Available SAP AI services in the knowledge base:
{services_summary}

Instructions:
1. Use the search_knowledge_base tool to find relevant documentation
2. You may call the tool multiple times with different queries or service filters
3. After reviewing search results, respond with this JSON structure:
   - is_sap_ai: whether the question relates to SAP AI services
   - services: list of relevant service keys (e.g., ["ai_core", "genai_hub"])
   - doc_ids: IDs of the most relevant docs from search results (2-5 IDs)
   - answer: detailed 1-2 paragraph explanation that directly addresses the question
   - confidence: how well the available docs cover the question (0.0-1.0)
4. If the question is NOT about SAP AI services, set is_sap_ai to false with empty services/doc_ids lists and explain what you can help with instead"""
                ),
                UserMessage(content="{{?user_question}}"),
            ],
            tools=[SEARCH_TOOL],
            response_format=ResponseFormatJsonSchema(
                json_schema=JSONResponseSchema(
                    name="doc_assistant_result",
                    description="Documentation assistant structured response",
                    schema=ASSISTANT_SCHEMA,
                ),
            ),
        )

    def _create_content_filter(self) -> "FilteringModuleConfig":
        """Configure Azure Content Safety filtering for input and output."""
        azure_config = AzureContentFilter(
            hate=AzureThreshold.ALLOW_SAFE,
            violence=AzureThreshold.ALLOW_SAFE_LOW,
            self_harm=AzureThreshold.ALLOW_SAFE_LOW_MEDIUM,
            sexual=AzureThreshold.ALLOW_SAFE_LOW_MEDIUM,
        )
        content_filter = ContentFilter(type="azure_content_safety", config=azure_config)

        return FilteringModuleConfig(
            input=InputFiltering(filters=[content_filter]),
            output=OutputFiltering(filters=[content_filter]),
        )

    def _create_data_masking(self) -> "MaskingModuleConfig":
        """Configure PII masking using SAP Data Privacy Integration."""
        return MaskingModuleConfig(
            masking_providers=[
                MaskingProviderConfig(
                    method=MaskingMethod.ANONYMIZATION,
                    entities=[
                        DPIStandardEntity(type=ProfileEntity.PERSON),
                        DPIStandardEntity(type=ProfileEntity.ORG),
                        DPIStandardEntity(type=ProfileEntity.EMAIL),
                        DPIStandardEntity(type=ProfileEntity.PHONE),
                        DPIStandardEntity(type=ProfileEntity.ADDRESS),
                        DPIStandardEntity(type=ProfileEntity.USERNAME_PASSWORD),
                        DPIStandardEntity(type=ProfileEntity.SAP_IDS_INTERNAL),
                        DPIStandardEntity(type=ProfileEntity.SAP_IDS_PUBLIC),
                    ],
                )
            ]
        )

    def _initialize_client(self):
        """Initialize the GenAI Hub Orchestration Service with all modules."""
        if not GENAI_HUB_AVAILABLE:
            logger.info("GenAI Hub SDK not available - using mock responses")
            self._service = None
            return

        try:
            llm = LLMModelDetails(
                name="gpt-4o",
                params={"max_tokens": 1000},
            )
            prompt_template = PromptTemplatingModuleConfig(
                prompt=self._create_template(),
                model=llm,
            )
            self._config = OrchestrationConfig(
                modules=ModuleConfig(
                    prompt_templating=prompt_template,
                    filtering=self._create_content_filter(),
                    masking=self._create_data_masking(),
                ),
            )

            self._service = OrchestrationService()
            logger.info("GenAI Hub Orchestration service initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize orchestration service: {e}")
            logger.info("Assistant will use mock responses for local testing")
            self._service = None

    def ask(self, question: str, include_pipeline: bool = False) -> dict:
        """
        Answer a user question about SAP AI services.

        Args:
            question: The user's question text
            include_pipeline: Whether to include orchestration pipeline details

        Returns:
            Dictionary with answer, services, links, and optional pipeline details
        """
        if not question or not question.strip():
            return {
                "is_sap_ai": False,
                "confidence": 1.0,
                "services": [],
                "links": [],
                "answer": "Please provide a valid question.",
            }

        try:
            if self._service is None:
                result = self._mock_ask(question)
                if include_pipeline:
                    result["pipeline"] = self._mock_pipeline_details(question)
                return result

            return self._run_with_tools(question, include_pipeline)

        except OrchestrationError as e:
            logger.warning(f"Orchestration blocked: {e}")
            response = self._content_filtered_response(question, str(e))
            if include_pipeline:
                response["pipeline"] = self._extract_pipeline_from_error(question, e)
            return response
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return self._fallback_response(question)
        except Exception as e:
            logger.error(f"Assistant error: {e}")
            return self._fallback_response(question)

    def _run_with_tools(self, question: str, include_pipeline: bool) -> dict:
        """Execute the agentic tool calling loop with the LLM.

        Flow:
        1. First LLM call — may return tool_calls or a direct answer
        2. If tool_calls: execute each tool, build conversation history
        3. Second LLM call with tool results — gets final structured answer
        """
        tool_call_details = []

        # First LLM call
        result = self._service.run(
            config=self._config,
            placeholder_values={"user_question": question},
        )
        msg = result.final_result.choices[0].message

        # Check if the LLM wants to call tools
        tool_calls = getattr(msg, "tool_calls", None)

        if tool_calls:
            # Build conversation history including the assistant's tool call request
            history = list(result.intermediate_results.templating)
            history.append(msg)

            for tc in tool_calls:
                # Parse and execute the tool
                args = json.loads(tc.function.arguments)
                tool_result = search_knowledge_base(**args)

                # Add tool result to conversation history
                history.append(
                    ToolChatMessage(content=str(tool_result), tool_call_id=tc.id)
                )

                # Track for pipeline visibility
                parsed_results = json.loads(tool_result)
                tool_call_details.append(
                    {
                        "tool_name": tc.function.name,
                        "arguments": args,
                        "result_count": len(parsed_results),
                        "results_preview": [
                            {"id": r["id"], "title": r["title"]}
                            for r in parsed_results[:5]
                        ],
                    }
                )

            # Second LLM call with tool results in context
            result = self._service.run(
                config=self._config,
                placeholder_values={"user_question": question},
                history=history,
            )

        # Parse the final structured response
        llm_result = json.loads(
            result.final_result.choices[0].message.content
        )
        response = self._format_response(llm_result)

        if include_pipeline:
            response["pipeline"] = self._extract_pipeline_details(question, result)
            response["pipeline"]["tool_calls"] = tool_call_details or None

        return response

    def _format_response(self, llm_result: dict) -> dict:
        """Format the LLM result into the API response format.

        Validates doc_ids against the KB and looks up full entries.
        """
        is_sap_ai = llm_result.get("is_sap_ai", False)
        services = llm_result.get("services", [])
        doc_ids = llm_result.get("doc_ids", [])
        answer = llm_result.get("answer", "")
        confidence = llm_result.get("confidence", 0.5)

        # Validate doc_ids against actual KB entries
        valid_ids = get_all_doc_ids()
        validated_ids = [did for did in doc_ids if did in valid_ids]

        # Look up full entries for validated IDs
        links = []
        if validated_ids:
            docs = get_docs_by_ids(validated_ids)
            links = [
                {
                    "title": doc["title"],
                    "url": doc["url"],
                    "description": doc["description"],
                }
                for doc in docs
            ]

        return {
            "is_sap_ai": is_sap_ai,
            "confidence": confidence,
            "services": services,
            "links": links,
            "answer": answer,
        }

    def _extract_pipeline_details(self, original_query: str, result) -> dict:
        """Extract pipeline processing details from orchestration result."""
        mr = result.intermediate_results

        # Extract masked query and entities from input_masking
        masked_query = original_query
        entities_masked = []
        if mr.input_masking and mr.input_masking.data:
            masked_template = mr.input_masking.data.get("masked_template", "")
            entities_masked = list(set(re.findall(r"MASKED_(\w+)", masked_template)))
            # V2 format: masked_template is a JSON array of message objects
            try:
                masked_messages = json.loads(masked_template)
                for msg in masked_messages:
                    if msg.get("role") == "user":
                        masked_query = msg["content"]
                        break
            except (json.JSONDecodeError, TypeError):
                pass

        # Extract messages sent to LLM (post-masking if available, otherwise pre-masking)
        messages_to_llm = []
        if entities_masked and mr.input_masking and mr.input_masking.data:
            # Use masked messages — what the LLM actually received
            try:
                masked_messages = json.loads(mr.input_masking.data.get("masked_template", ""))
                for msg in masked_messages:
                    messages_to_llm.append({"role": msg["role"], "content": msg["content"]})
            except (json.JSONDecodeError, TypeError, KeyError):
                pass
        if not messages_to_llm and mr.templating:
            for msg in mr.templating:
                messages_to_llm.append({"role": msg.role, "content": msg.content})

        # Extract content filtering scores (V2 uses lowercase keys)
        input_filter = {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": True}
        output_filter = {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": True}

        if mr.input_filtering:
            passed = "passed" in (getattr(mr.input_filtering, "message", "") or "").lower()
            if mr.input_filtering.data:
                azure_scores = mr.input_filtering.data.get("azure_content_safety", {})
                input_filter = {
                    "hate": azure_scores.get("hate", 0),
                    "self_harm": azure_scores.get("self_harm", 0),
                    "sexual": azure_scores.get("sexual", 0),
                    "violence": azure_scores.get("violence", 0),
                    "passed": passed,
                }

        if mr.output_filtering:
            passed = "passed" in (getattr(mr.output_filtering, "message", "") or "").lower()
            if mr.output_filtering.data:
                choices = mr.output_filtering.data.get("choices", [{}])
                if choices:
                    azure_scores = choices[0].get("azure_content_safety", {})
                    output_filter = {
                        "hate": azure_scores.get("hate", 0),
                        "self_harm": azure_scores.get("self_harm", 0),
                        "sexual": azure_scores.get("sexual", 0),
                        "violence": azure_scores.get("violence", 0),
                        "passed": passed,
                    }

        # Extract LLM details
        final = result.final_result
        llm_details = {
            "model": final.model if hasattr(final, "model") else "unknown",
            "prompt_tokens": final.usage.prompt_tokens if hasattr(final, "usage") and final.usage else 0,
            "completion_tokens": final.usage.completion_tokens if hasattr(final, "usage") and final.usage else 0,
        }

        return {
            "data_masking": {
                "original_query": original_query,
                "masked_query": masked_query,
                "entities_masked": entities_masked,
            }
            if entities_masked
            else None,
            "content_filtering": {
                "input": input_filter,
                "output": output_filter,
            },
            "llm": llm_details,
            "messages_to_llm": messages_to_llm,
        }

    def _mock_pipeline_details(self, question: str) -> dict:
        """Generate mock pipeline details for local testing."""
        return {
            "data_masking": None,
            "content_filtering": {
                "input": {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": True},
                "output": {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": True},
            },
            "llm": {"model": "mock", "prompt_tokens": 0, "completion_tokens": 0},
            "messages_to_llm": [
                {"role": "system", "content": "[MOCK] System prompt would appear here"},
                {"role": "user", "content": question},
            ],
            "tool_calls": [
                {
                    "tool_name": "search_knowledge_base",
                    "arguments": {"query": question},
                    "result_count": 3,
                    "results_preview": [
                        {"id": "mock_01", "title": "[MOCK] Matching doc 1"},
                        {"id": "mock_02", "title": "[MOCK] Matching doc 2"},
                    ],
                }
            ],
        }

    def _mock_ask(self, question: str) -> dict:
        """Mock documentation assistant for local testing without GenAI Hub."""
        query_lower = question.lower()

        # Non-SAP AI patterns
        non_sap_patterns = [
            "password", "laptop", "computer", "printer", "wifi",
            "weather", "email setup", "vpn", "software install",
            "recipe", "movie", "sports",
        ]
        if any(pattern in query_lower for pattern in non_sap_patterns):
            return {
                "is_sap_ai": False,
                "confidence": 0.90,
                "services": [],
                "links": [],
                "answer": "[MOCK] This doesn't appear to be related to SAP AI services. I can help with SAP AI Core, Generative AI Hub, Joule, HANA Cloud Vector Engine, AI Launchpad, and Document Information Extraction.",
            }

        # Service keyword matching (order by specificity)
        service_matches = [
            ("hana_cloud_vector", [
                "hana vector", "vector engine", "real_vector", "cosine_similarity",
                "l2distance", "vector index", "embedding", "hana embedding",
                "similarity search", "vector column", "vector", "hana cloud",
            ]),
            ("document_processing", [
                "document extraction", "dox", "document information",
                "invoice", "document processing", "schema extraction",
                "purchase order extraction", "extract data",
            ]),
            ("joule", [
                "joule", "joule studio", "joule skill", "joule action",
                "joule capability",
            ]),
            ("ai_launchpad", [
                "ai launchpad", "launchpad", "mlops", "ml operations",
                "model registry", "ai monitoring",
            ]),
            ("genai_hub", [
                "orchestration", "genai hub", "generative ai hub", "sdk",
                "content filter", "data masking", "grounding", "prompt registry",
                "rag", "retrieval augmented",
            ]),
            ("ai_core", [
                "ai core", "deploy", "resource group",
                "serving template", "workflow template", "docker registry",
                "ai api", "execution", "scenario",
            ]),
        ]

        matched_services = []
        for service_key, keywords in service_matches:
            if any(kw in query_lower for kw in keywords):
                matched_services.append(service_key)

        if matched_services:
            # Run actual search to get real KB entries
            search_results = json.loads(search_knowledge_base(question))
            links = [
                {
                    "title": r["title"],
                    "url": r["url"],
                    "description": r["description"],
                }
                for r in search_results[:5]
            ]

            service_names = []
            from knowledge_base import load_knowledge_base
            kb = load_knowledge_base()
            for svc in matched_services:
                if svc in kb.get("services", {}):
                    service_names.append(kb["services"][svc]["display_name"])

            return {
                "is_sap_ai": True,
                "confidence": 0.85,
                "services": matched_services,
                "links": links,
                "answer": f"[MOCK] I can help you with {', '.join(service_names)}. Based on your question, I've found several relevant documentation resources. Please review the linked docs for detailed guidance.",
            }

        # Generic SAP-related but no specific service match
        if any(term in query_lower for term in ["sap", "btp", "cloud foundry", "fiori"]):
            return {
                "is_sap_ai": True,
                "confidence": 0.60,
                "services": [],
                "links": [],
                "answer": "[MOCK] Your question seems related to SAP but I couldn't match it to a specific AI service. I cover: SAP AI Core, Generative AI Hub, Joule, HANA Cloud Vector Engine, AI Launchpad, and Document Information Extraction.",
            }

        return {
            "is_sap_ai": False,
            "confidence": 0.80,
            "services": [],
            "links": [],
            "answer": "[MOCK] This doesn't appear to be related to SAP AI services. I can help with SAP AI Core, Generative AI Hub, Joule, HANA Cloud Vector Engine, AI Launchpad, and Document Information Extraction.",
        }

    def _fallback_response(self, question: str) -> dict:
        """Fallback response when the assistant fails."""
        return {
            "is_sap_ai": False,
            "confidence": 0.0,
            "services": [],
            "links": [],
            "answer": "Unable to process the question. Please try again or rephrase your question.",
        }

    def _content_filtered_response(self, question: str, error_message: str) -> dict:
        """Response when content filtering blocks the request."""
        return {
            "is_sap_ai": False,
            "confidence": 0.0,
            "services": [],
            "links": [],
            "answer": "Your question was blocked by content filtering. Please rephrase your question.",
        }

    def _extract_pipeline_from_error(self, original_query: str, error: "OrchestrationError") -> dict:
        """Extract pipeline details from an OrchestrationError (e.g., content filter block)."""
        mr = getattr(error, "module_results", {}) or {}

        masked_query = original_query
        entities_masked = []
        input_masking = mr.get("input_masking", {})
        if input_masking:
            masking_data = input_masking.get("data", {})
            masked_template = masking_data.get("masked_template", "")
            entities_masked = list(set(re.findall(r"MASKED_(\w+)", masked_template)))

        input_filter = {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": True}
        input_filtering = mr.get("input_filtering", {})
        if input_filtering:
            filter_data = input_filtering.get("data", {})
            azure_scores = filter_data.get("azure_content_safety", {})
            input_filter = {
                "hate": azure_scores.get("hate", 0),
                "self_harm": azure_scores.get("self_harm", 0),
                "sexual": azure_scores.get("sexual", 0),
                "violence": azure_scores.get("violence", 0),
                "passed": False,
            }

        output_filter = {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": False}

        messages_to_llm = []
        templating = mr.get("templating", [])
        if templating:
            for msg in templating:
                if isinstance(msg, dict):
                    messages_to_llm.append({"role": msg.get("role", ""), "content": msg.get("content", "")})

        return {
            "data_masking": {
                "original_query": original_query,
                "masked_query": masked_query,
                "entities_masked": entities_masked,
            }
            if entities_masked
            else None,
            "content_filtering": {
                "input": input_filter,
                "output": output_filter,
            },
            "llm": {"model": "blocked", "prompt_tokens": 0, "completion_tokens": 0},
            "messages_to_llm": messages_to_llm,
            "tool_calls": None,
        }


# Singleton instance
_assistant_instance = None


def get_assistant() -> DocAssistant:
    """Get or create the assistant singleton instance."""
    global _assistant_instance
    if _assistant_instance is None:
        _assistant_instance = DocAssistant()
    return _assistant_instance
