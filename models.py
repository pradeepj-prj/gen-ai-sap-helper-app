"""
Pydantic Models for Request/Response Validation

These models provide:
1. Automatic request validation
2. Response serialization
3. OpenAPI schema generation for Joule Action import
"""

from pydantic import BaseModel, Field


class ClassifyRequest(BaseModel):
    """Request model for the classification endpoint."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The user query to classify",
        json_schema_extra={"example": "How do I submit my annual performance review?"},
    )
    show_pipeline: bool = Field(
        False,
        description="Include orchestration pipeline processing details in response (for demos)",
    )


class LinkInfo(BaseModel):
    """Information about a help resource link."""

    title: str = Field(..., description="Title of the help resource")
    url: str = Field(..., description="URL to the SAP Help Portal page")
    description: str = Field(..., description="Brief description of the resource")


# Pipeline visibility models for demo purposes
class ContentFilterScores(BaseModel):
    """Content safety scores from Azure Content Safety."""

    hate: int = Field(0, description="Hate speech score (0=safe)")
    self_harm: int = Field(0, description="Self-harm content score")
    sexual: int = Field(0, description="Sexual content score")
    violence: int = Field(0, description="Violence content score")
    passed: bool = Field(..., description="Whether content passed filtering")


class DataMaskingDetails(BaseModel):
    """Details about PII masking applied to the query."""

    original_query: str = Field(..., description="Original user query")
    masked_query: str = Field(..., description="Query after PII anonymization")
    entities_masked: list[str] = Field(
        default_factory=list, description="Types of PII detected and masked"
    )


class LLMDetails(BaseModel):
    """Details about the LLM processing."""

    model: str = Field(..., description="Model used for classification")
    prompt_tokens: int = Field(0, description="Tokens in the prompt")
    completion_tokens: int = Field(0, description="Tokens in the response")


class LLMMessage(BaseModel):
    """A message in the LLM conversation."""

    role: str = Field(..., description="Message role (system/user)")
    content: str = Field(..., description="Message content (with PII masked)")


class ContentFilteringDetails(BaseModel):
    """Input and output content filter results."""

    input: ContentFilterScores = Field(..., description="Input content filter scores")
    output: ContentFilterScores = Field(..., description="Output content filter scores")


class PipelineDetails(BaseModel):
    """Orchestration pipeline processing details."""

    data_masking: DataMaskingDetails | None = Field(
        None, description="PII masking details (null if no masking configured)"
    )
    content_filtering: ContentFilteringDetails = Field(
        ..., description="Input/output content filter results"
    )
    llm: LLMDetails = Field(..., description="LLM processing details")
    messages_to_llm: list[LLMMessage] = Field(
        ..., description="Exact messages sent to the LLM (after masking)"
    )


class ClassifyResponse(BaseModel):
    """Response model for the classification endpoint."""

    is_talent_management: bool = Field(
        ..., description="Whether the query relates to Talent Management"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score of the classification (0.0 to 1.0)",
    )
    topic: str | None = Field(
        None, description="The identified topic key (e.g., 'performance_management')"
    )
    topic_display_name: str | None = Field(
        None, description="Human-readable topic name (e.g., 'Performance Management')"
    )
    links: list[LinkInfo] = Field(
        default_factory=list, description="Relevant SAP Help Portal links"
    )
    summary: str = Field(
        ..., description="A brief summary message about the classification result"
    )
    pipeline: PipelineDetails | None = Field(
        None, description="Pipeline processing details (when show_pipeline=true)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "is_talent_management": True,
                    "confidence": 0.95,
                    "topic": "performance_management",
                    "topic_display_name": "Performance Management",
                    "links": [
                        {
                            "title": "Performance & Goals Administration",
                            "url": "https://help.sap.com/docs/SAP_SUCCESSFACTORS_PERFORMANCE_GOALS",
                            "description": "Complete guide to Performance Management in SuccessFactors",
                        }
                    ],
                    "summary": "Your question is about Performance Management. Here are helpful resources.",
                },
                {
                    "is_talent_management": False,
                    "confidence": 0.92,
                    "topic": None,
                    "topic_display_name": None,
                    "links": [],
                    "summary": "This query doesn't appear to be related to Talent Management.",
                },
            ]
        }
    }


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""

    status: str = Field(..., description="Health status of the service")
    service: str = Field(..., description="Name of the service")
    version: str = Field(..., description="API version")
