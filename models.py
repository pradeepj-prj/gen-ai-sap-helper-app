"""
Pydantic Models for Request/Response Validation

These models provide:
1. Automatic request validation
2. Response serialization
3. OpenAPI schema generation
"""

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """Request model for the documentation assistant endpoint."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The user question about SAP AI services",
        json_schema_extra={"example": "How do I deploy a model on SAP AI Core?"},
    )
    show_pipeline: bool = Field(
        False,
        description="Include orchestration pipeline processing details in response (for demos)",
    )


class LinkInfo(BaseModel):
    """Information about a documentation link."""

    title: str = Field(..., description="Title of the documentation resource")
    url: str = Field(..., description="URL to the SAP Help Portal page")
    description: str = Field(..., description="Brief description of the resource")


# Pipeline visibility models
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

    model: str = Field(..., description="Model used for processing")
    prompt_tokens: int = Field(0, description="Tokens in the prompt")
    completion_tokens: int = Field(0, description="Tokens in the response")


class LLMMessage(BaseModel):
    """A message in the LLM conversation."""

    role: str = Field(..., description="Message role (system/user/assistant/tool)")
    content: str = Field(..., description="Message content (with PII masked)")


class ContentFilteringDetails(BaseModel):
    """Input and output content filter results."""

    input: ContentFilterScores = Field(..., description="Input content filter scores")
    output: ContentFilterScores = Field(..., description="Output content filter scores")


class ToolCallDetails(BaseModel):
    """Details about a tool call made during the orchestration."""

    tool_name: str = Field(..., description="Name of the tool called")
    arguments: dict = Field(..., description="Arguments passed to the tool")
    result_count: int = Field(..., description="Number of results returned")
    results_preview: list[dict] = Field(
        ..., description="Preview of results (id + title only)"
    )


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
    tool_calls: list[ToolCallDetails] | None = Field(
        None, description="Tool calls made during orchestration"
    )


class AskResponse(BaseModel):
    """Response model for the documentation assistant endpoint."""

    is_sap_ai: bool = Field(
        ..., description="Whether the question relates to SAP AI services"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0 to 1.0)",
    )
    services: list[str] = Field(
        default_factory=list, description="Relevant SAP AI service keys"
    )
    links: list[LinkInfo] = Field(
        default_factory=list, description="Relevant SAP documentation links"
    )
    answer: str = Field(
        ..., description="Detailed answer to the user's question"
    )
    pipeline: PipelineDetails | None = Field(
        None, description="Pipeline processing details (when show_pipeline=true)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "is_sap_ai": True,
                    "confidence": 0.95,
                    "services": ["ai_core"],
                    "links": [
                        {
                            "title": "SAP AI Core Overview",
                            "url": "https://help.sap.com/docs/sap-ai-core",
                            "description": "Main documentation landing page for SAP AI Core",
                        }
                    ],
                    "answer": "To deploy a model on SAP AI Core, you need to create a serving template that defines the model server configuration, then register it as a scenario. After that, you can create a deployment configuration and start the deployment through the AI Core API or AI Launchpad UI.",
                },
                {
                    "is_sap_ai": False,
                    "confidence": 0.92,
                    "services": [],
                    "links": [],
                    "answer": "This question doesn't appear to be related to SAP AI services. I can help with topics like SAP AI Core, Generative AI Hub, Joule, HANA Cloud Vector Engine, and more.",
                },
            ]
        }
    }


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""

    status: str = Field(..., description="Health status of the service")
    service: str = Field(..., description="Name of the service")
    version: str = Field(..., description="API version")


# KB management models
class KBEntryCreate(BaseModel):
    """Request model for creating a new knowledge base entry."""

    service_key: str = Field(..., description="Service key (e.g., 'ai_core')")
    title: str = Field(..., description="Title of the documentation resource")
    url: str = Field(..., description="URL to the documentation page")
    description: str = Field(..., description="Brief description of the resource")
    tags: list[str] = Field(default_factory=list, description="Search tags")


class KBEntryUpdate(BaseModel):
    """Request model for updating a knowledge base entry (partial update)."""

    title: str | None = Field(None, description="New title")
    url: str | None = Field(None, description="New URL")
    description: str | None = Field(None, description="New description")
    tags: list[str] | None = Field(None, description="New tags")


class KBEntryResponse(BaseModel):
    """Response model for a knowledge base entry."""

    id: str = Field(..., description="Unique document ID")
    service_key: str = Field(..., description="Service key this entry belongs to")
    title: str = Field(..., description="Title of the documentation resource")
    url: str = Field(..., description="URL to the documentation page")
    description: str = Field(..., description="Brief description of the resource")
    tags: list[str] = Field(default_factory=list, description="Search tags")
