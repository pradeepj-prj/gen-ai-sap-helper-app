"""
Intent Classifier using SAP GenAI Hub SDK

This module handles the LLM-based classification of user queries to determine
if they relate to Talent Management and identify the specific topic.
"""

import json
import logging
import os

from dotenv import load_dotenv

# Load environment variables from .env file (for local development)
# This must happen before any GenAI Hub SDK imports that read AICORE_* vars
load_dotenv()

from topic_links import TOPIC_LINKS, get_topics_for_prompt

# Lazy imports for GenAI Hub SDK (may not be available locally)
try:
    from gen_ai_hub.proxy.core.proxy_clients import get_proxy_client
    from gen_ai_hub.proxy.langchain.openai import ChatOpenAI
    GENAI_HUB_AVAILABLE = True
except ImportError:
    GENAI_HUB_AVAILABLE = False
    get_proxy_client = None
    ChatOpenAI = None

logger = logging.getLogger(__name__)


class IntentClassifier:
    """Classifies user queries into Talent Management topics using GPT-4."""

    def __init__(self):
        """Initialize the classifier with GenAI Hub client."""
        self._llm = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize the GenAI Hub proxy client and LLM."""
        if not GENAI_HUB_AVAILABLE:
            logger.info("GenAI Hub SDK not available - using mock classification")
            self._llm = None
            return

        try:
            # GenAI Hub SDK automatically picks up credentials from:
            # 1. Environment variables (AICORE_*)
            # 2. CF service binding (VCAP_SERVICES)
            proxy_client = get_proxy_client("gen-ai-hub")

            self._llm = ChatOpenAI(
                proxy_client=proxy_client,
                proxy_model_name="gpt-4",
                temperature=0.1,  # Low temperature for consistent classification
                max_tokens=500,
            )
            logger.info("GenAI Hub client initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize GenAI Hub client: {e}")
            logger.info("Classifier will use mock responses for local testing")
            self._llm = None

    def _build_classification_prompt(self, query: str) -> str:
        """Build the prompt for classification."""
        topics_list = get_topics_for_prompt()

        return f"""You are an expert at classifying HR and Talent Management queries.

Analyze the following user query and determine:
1. Whether it relates to SAP SuccessFactors Talent Management
2. If yes, which specific topic it belongs to

Available Talent Management topics:
{topics_list}

User Query: "{query}"

Respond with a JSON object in this exact format:
{{
    "is_talent_management": true/false,
    "confidence": 0.0-1.0,
    "topic": "topic_key_or_null",
    "reasoning": "brief explanation"
}}

Rules:
- If the query is clearly about Talent Management, set is_talent_management to true
- Choose the single most relevant topic from the list above
- If the query is ambiguous or could relate to multiple topics, choose the most likely one
- If the query is NOT about Talent Management (e.g., IT support, general questions), set is_talent_management to false and topic to null
- Confidence should reflect how certain you are about the classification

Respond ONLY with the JSON object, no additional text."""

    def classify(self, query: str) -> dict:
        """
        Classify a user query.

        Args:
            query: The user's query text

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
            if self._llm is None:
                # Mock response for local testing without GenAI Hub
                return self._mock_classify(query)

            prompt = self._build_classification_prompt(query)
            response = self._llm.invoke(prompt)

            # Parse the JSON response
            result = json.loads(response.content)

            return self._format_response(result)

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


# Singleton instance
_classifier_instance = None


def get_classifier() -> IntentClassifier:
    """Get or create the classifier singleton instance."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = IntentClassifier()
    return _classifier_instance
