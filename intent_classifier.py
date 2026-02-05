"""
Intent Classifier using SAP GenAI Hub Orchestration Service V2

This module handles the LLM-based classification of user queries to determine
if they relate to Talent Management and identify the specific topic.

Uses Orchestration Service V2 features:
- Structured prompts (SystemMessage/UserMessage)
- JSON schema response formatting (guaranteed valid JSON)
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

from topic_links import TOPIC_LINKS, get_topics_for_prompt

# Lazy imports for GenAI Hub Orchestration SDK (may not be available locally)
try:
    from gen_ai_hub.orchestration.service import OrchestrationService
    from gen_ai_hub.orchestration.models.message import SystemMessage, UserMessage
    from gen_ai_hub.orchestration.models.template import Template, TemplateValue
    from gen_ai_hub.orchestration.models.llm import LLM
    from gen_ai_hub.orchestration.models.config import OrchestrationConfig
    from gen_ai_hub.orchestration.models.response_format import ResponseFormatJsonSchema
    # Content filtering imports
    from gen_ai_hub.orchestration.models.content_filtering import (
        ContentFiltering, InputFiltering, OutputFiltering
    )
    from gen_ai_hub.orchestration.models.azure_content_filter import (
        AzureContentFilter, AzureThreshold
    )
    # Data masking imports
    from gen_ai_hub.orchestration.models.data_masking import DataMasking
    from gen_ai_hub.orchestration.models.sap_data_privacy_integration import (
        SAPDataPrivacyIntegration, MaskingMethod, ProfileEntity
    )
    # Exception for content filtering blocks
    from gen_ai_hub.orchestration.exceptions import OrchestrationError
    GENAI_HUB_AVAILABLE = True
except ImportError:
    GENAI_HUB_AVAILABLE = False
    OrchestrationError = Exception  # Fallback for type checking

logger = logging.getLogger(__name__)

# JSON schema for classification response - ensures valid, structured output
CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "is_talent_management": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "topic": {"type": ["string", "null"]},
        "reasoning": {"type": "string"}
    },
    "required": ["is_talent_management", "confidence", "topic", "reasoning"],
    "additionalProperties": False
}


class IntentClassifier:
    """Classifies user queries into Talent Management topics using GPT-4 via Orchestration Service."""

    def __init__(self):
        """Initialize the classifier with GenAI Hub Orchestration Service."""
        self._service = None
        self._initialize_client()

    def _create_template(self) -> "Template":
        """Create the prompt template with system and user messages."""
        topics_list = get_topics_for_prompt()

        return Template(
            messages=[
                SystemMessage(content=f"""You are an expert at classifying HR and Talent Management queries.
Available Talent Management topics:
{topics_list}

Rules:
- If the query is clearly about Talent Management, set is_talent_management to true
- Choose the single most relevant topic from the list above
- If ambiguous, choose the most likely topic
- If NOT about Talent Management, set is_talent_management to false and topic to null
- Confidence should reflect classification certainty (0.0-1.0)"""),
                UserMessage(content="Classify this query: {{?user_query}}")
            ],
            response_format=ResponseFormatJsonSchema(
                name="classification_result",
                description="Intent classification result",
                schema=CLASSIFICATION_SCHEMA
            )
        )

    def _create_content_filter(self) -> "ContentFiltering":
        """Configure Azure Content Safety filtering for input and output."""
        azure_filter = AzureContentFilter(
            hate=AzureThreshold.ALLOW_SAFE,
            violence=AzureThreshold.ALLOW_SAFE,
            self_harm=AzureThreshold.ALLOW_SAFE,
            sexual=AzureThreshold.ALLOW_SAFE
        )

        return ContentFiltering(
            input_filtering=InputFiltering(filters=[azure_filter]),
            output_filtering=OutputFiltering(filters=[azure_filter])
        )

    def _create_data_masking(self) -> "DataMasking":
        """Configure PII masking using SAP Data Privacy Integration."""
        return DataMasking(
            providers=[SAPDataPrivacyIntegration(
                method=MaskingMethod.ANONYMIZATION,
                entities=[
                    ProfileEntity.PERSON,
                    ProfileEntity.EMAIL,
                    ProfileEntity.PHONE,
                    ProfileEntity.ADDRESS,
                ]
            )]
        )

    def _initialize_client(self):
        """Initialize the GenAI Hub Orchestration Service with all modules."""
        if not GENAI_HUB_AVAILABLE:
            logger.info("GenAI Hub SDK not available - using mock classification")
            self._service = None
            return

        try:
            # Create orchestration config with all modules
            config = OrchestrationConfig(
                template=self._create_template(),
                llm=LLM(name="gpt-4o", parameters={"max_tokens": 500}),
                filtering=self._create_content_filter(),
                data_masking=self._create_data_masking()
            )

            self._service = OrchestrationService(config=config)
            logger.info("GenAI Hub Orchestration service initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize orchestration service: {e}")
            logger.info("Classifier will use mock responses for local testing")
            self._service = None

    def classify(self, query: str, include_pipeline: bool = False) -> dict:
        """
        Classify a user query.

        Args:
            query: The user's query text
            include_pipeline: Whether to include orchestration pipeline details

        Returns:
            Dictionary with classification results
        """
        if not query or not query.strip():
            return {
                "is_talent_management": False,
                "confidence": 1.0,
                "topic": None,
                "topic_display_name": None,
                "links": [],
                "summary": "Please provide a valid query.",
            }

        try:
            if self._service is None:
                # Mock response for local testing without GenAI Hub
                result = self._mock_classify(query)
                if include_pipeline:
                    result["pipeline"] = self._mock_pipeline_details(query)
                return result

            # Run orchestration with template values
            orch_result = self._service.run(
                template_values=[TemplateValue(name="user_query", value=query)]
            )

            # ResponseFormatJsonSchema guarantees valid JSON - no markdown stripping needed
            llm_result = json.loads(orch_result.orchestration_result.choices[0].message.content)
            response = self._format_response(llm_result)

            if include_pipeline:
                response["pipeline"] = self._extract_pipeline_details(query, orch_result)

            return response

        except OrchestrationError as e:
            # Content filtering blocked the request - extract pipeline details from exception
            logger.warning(f"Orchestration blocked: {e}")
            response = self._content_filtered_response(query, str(e))
            if include_pipeline:
                response["pipeline"] = self._extract_pipeline_from_error(query, e)
            return response
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return self._fallback_response(query)
        except Exception as e:
            logger.error(f"Classification error: {e}")
            return self._fallback_response(query)

    def _format_response(self, llm_result: dict) -> dict:
        """Format the LLM result into the API response format."""
        is_tm = llm_result.get("is_talent_management", False)
        topic = llm_result.get("topic")
        confidence = llm_result.get("confidence", 0.5)

        if is_tm and topic and topic in TOPIC_LINKS:
            topic_info = TOPIC_LINKS[topic]
            return {
                "is_talent_management": True,
                "confidence": confidence,
                "topic": topic,
                "topic_display_name": topic_info["display_name"],
                "links": topic_info["links"],
                "summary": f"Your question is about {topic_info['display_name']}. Here are helpful resources.",
            }
        else:
            return {
                "is_talent_management": False,
                "confidence": confidence,
                "topic": None,
                "topic_display_name": None,
                "links": [],
                "summary": "This query doesn't appear to be related to Talent Management.",
            }

    def _extract_pipeline_details(self, original_query: str, result) -> dict:
        """Extract pipeline processing details from orchestration result."""
        mr = result.module_results

        # Extract masked query and entities from input_masking
        masked_query = original_query
        entities_masked = []
        if mr.input_masking and mr.input_masking.data:
            masked_template = mr.input_masking.data.get("masked_template", "")
            # Extract entity types like MASKED_PERSON, MASKED_EMAIL
            entities_masked = list(set(re.findall(r"MASKED_(\w+)", masked_template)))
            # Try to extract the masked user query from the template
            # The template structure is: system message + user message with masked content
            if "Classify this query:" in masked_template:
                match = re.search(r"Classify this query:\s*(.+?)(?:\n|$)", masked_template)
                if match:
                    masked_query = match.group(1).strip()

        # Extract messages sent to LLM from templating module
        messages_to_llm = []
        if mr.templating:
            for msg in mr.templating:
                messages_to_llm.append({"role": msg.role, "content": msg.content})

        # Extract content filtering scores
        input_filter = {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": True}
        output_filter = {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": True}

        if mr.input_filtering and mr.input_filtering.data:
            azure_scores = mr.input_filtering.data.get("azure_content_safety", {})
            input_filter = {
                "hate": azure_scores.get("Hate", 0),
                "self_harm": azure_scores.get("SelfHarm", 0),
                "sexual": azure_scores.get("Sexual", 0),
                "violence": azure_scores.get("Violence", 0),
                "passed": True,
            }

        if mr.output_filtering and mr.output_filtering.data:
            choices = mr.output_filtering.data.get("choices", [{}])
            if choices:
                azure_scores = choices[0].get("azure_content_safety", {})
                output_filter = {
                    "hate": azure_scores.get("Hate", 0),
                    "self_harm": azure_scores.get("SelfHarm", 0),
                    "sexual": azure_scores.get("Sexual", 0),
                    "violence": azure_scores.get("Violence", 0),
                    "passed": True,
                }

        # Extract LLM details
        orch = result.orchestration_result
        llm_details = {
            "model": orch.model if hasattr(orch, "model") else "unknown",
            "prompt_tokens": orch.usage.prompt_tokens if hasattr(orch, "usage") and orch.usage else 0,
            "completion_tokens": orch.usage.completion_tokens if hasattr(orch, "usage") and orch.usage else 0,
        }

        return {
            "data_masking": {
                "original_query": original_query,
                "masked_query": masked_query,
                "entities_masked": entities_masked,
            } if entities_masked else None,
            "content_filtering": {
                "input": input_filter,
                "output": output_filter,
            },
            "llm": llm_details,
            "messages_to_llm": messages_to_llm,
        }

    def _mock_pipeline_details(self, query: str) -> dict:
        """Generate mock pipeline details for local testing."""
        return {
            "data_masking": None,  # No masking in mock mode
            "content_filtering": {
                "input": {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": True},
                "output": {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": True},
            },
            "llm": {"model": "mock", "prompt_tokens": 0, "completion_tokens": 0},
            "messages_to_llm": [
                {"role": "system", "content": "[MOCK] System prompt would appear here"},
                {"role": "user", "content": f"Classify this query: {query}"},
            ],
        }

    def _mock_classify(self, query: str) -> dict:
        """Mock classification for local testing without GenAI Hub."""
        query_lower = query.lower()

        # Non-TM patterns to check first (to avoid false positives)
        non_tm_patterns = [
            "password",
            "laptop",
            "computer",
            "printer",
            "wifi",
            "weather",
            "email setup",
            "vpn",
            "software install",
        ]
        if any(pattern in query_lower for pattern in non_tm_patterns):
            return {
                "is_talent_management": False,
                "confidence": 0.90,
                "topic": None,
                "topic_display_name": None,
                "links": [],
                "summary": "[MOCK] This query doesn't appear to be related to Talent Management.",
            }

        # Simple keyword-based mock classification (order matters for priority)
        topic_matches = [
            # Check more specific patterns first
            ("employee_onboarding", [
                "onboarding",
                "new hire",
                "new employee",
                "orientation",
                "first day",
                "preboarding",
            ]),
            ("succession_planning", [
                "succession",
                "career path",
                "talent pool",
                "successor",
                "next in line",
                "leadership pipeline",
                "high potential",
            ]),
            ("time_attendance", [
                "time off",
                "leave request",
                "vacation",
                "attendance",
                "absence",
                "pto",
                "sick leave",
                "timesheet",
            ]),
            ("performance_management", [
                "performance",
                "review",
                "goal",
                "feedback",
                "appraisal",
                "evaluation",
            ]),
            ("learning_development", [
                "training",
                "course",
                "learn",
                "certification",
                "skill development",
                "curriculum",
            ]),
            ("recruitment", [
                "job posting",
                "job opening",
                "candidate",
                "interview",
                "recruiting",
                "requisition",
                "applicant",
            ]),
            ("compensation_benefits", [
                "salary",
                "bonus",
                "pay",
                "compensation",
                "benefit",
                "merit increase",
            ]),
            ("employee_central", [
                "employee data",
                "org chart",
                "profile",
                "organization",
                "personal information",
                "reporting structure",
            ]),
        ]

        for topic, keywords in topic_matches:
            if any(kw in query_lower for kw in keywords):
                topic_info = TOPIC_LINKS[topic]
                return {
                    "is_talent_management": True,
                    "confidence": 0.85,
                    "topic": topic,
                    "topic_display_name": topic_info["display_name"],
                    "links": topic_info["links"],
                    "summary": f"[MOCK] Your question is about {topic_info['display_name']}. Here are helpful resources.",
                }

        return {
            "is_talent_management": False,
            "confidence": 0.80,
            "topic": None,
            "topic_display_name": None,
            "links": [],
            "summary": "[MOCK] This query doesn't appear to be related to Talent Management.",
        }

    def _fallback_response(self, query: str) -> dict:
        """Fallback response when classification fails."""
        return {
            "is_talent_management": False,
            "confidence": 0.0,
            "topic": None,
            "topic_display_name": None,
            "links": [],
            "summary": "Unable to classify the query. Please try again or rephrase your question.",
        }

    def _content_filtered_response(self, query: str, error_message: str) -> dict:
        """Response when content filtering blocks the request."""
        return {
            "is_talent_management": False,
            "confidence": 0.0,
            "topic": None,
            "topic_display_name": None,
            "links": [],
            "summary": "Your query was blocked by content filtering. Please rephrase your question.",
        }

    def _extract_pipeline_from_error(self, original_query: str, error: "OrchestrationError") -> dict:
        """Extract pipeline details from an OrchestrationError (e.g., content filter block)."""
        # Access module_results from the exception
        mr = getattr(error, "module_results", {}) or {}

        # Extract masked query if available
        # Structure: input_masking -> data -> masked_template
        masked_query = original_query
        entities_masked = []
        input_masking = mr.get("input_masking", {})
        if input_masking:
            masking_data = input_masking.get("data", {})
            masked_template = masking_data.get("masked_template", "")
            entities_masked = list(set(re.findall(r"MASKED_(\w+)", masked_template)))
            if "Classify this query:" in masked_template:
                match = re.search(r"Classify this query:\s*(.+?)(?:\n|$)", masked_template)
                if match:
                    masked_query = match.group(1).strip()

        # Extract input filtering scores (this is where the block happened)
        # Structure: input_filtering -> data -> azure_content_safety
        input_filter = {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": True}
        input_filtering = mr.get("input_filtering", {})
        if input_filtering:
            filter_data = input_filtering.get("data", {})
            azure_scores = filter_data.get("azure_content_safety", {})
            input_filter = {
                "hate": azure_scores.get("Hate", 0),
                "self_harm": azure_scores.get("SelfHarm", 0),
                "sexual": azure_scores.get("Sexual", 0),
                "violence": azure_scores.get("Violence", 0),
                "passed": False,  # Content was blocked
            }

        # Output filtering won't have run if input was blocked
        output_filter = {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": False}

        # Extract templating messages if available
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
            } if entities_masked else None,
            "content_filtering": {
                "input": input_filter,
                "output": output_filter,
            },
            "llm": {"model": "blocked", "prompt_tokens": 0, "completion_tokens": 0},
            "messages_to_llm": messages_to_llm,
        }


# Singleton instance
_classifier_instance = None


def get_classifier() -> IntentClassifier:
    """Get or create the classifier singleton instance."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = IntentClassifier()
    return _classifier_instance
