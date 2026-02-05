"""
FastAPI Application for Talent Management Intent Classification

This API classifies user queries to determine if they relate to
SAP SuccessFactors Talent Management topics and returns relevant help links.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from intent_classifier import get_classifier
from models import (
    ClassifyRequest,
    ClassifyResponse,
    ContentFilteringDetails,
    ContentFilterScores,
    DataMaskingDetails,
    HealthResponse,
    LinkInfo,
    LLMDetails,
    LLMMessage,
    PipelineDetails,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup."""
    logger.info("Initializing Intent Classifier...")
    get_classifier()  # Pre-initialize the classifier
    logger.info("Application started successfully")
    yield
    logger.info("Application shutting down")


app = FastAPI(
    title="Talent Management Intent Classifier API",
    description="""
Classifies user queries related to SAP SuccessFactors Talent Management
and returns relevant help portal links.

## Features
- Identifies if a query relates to Talent Management
- Classifies queries into 8 specific TM topics
- Returns relevant SAP Help Portal documentation links

## Topics Supported
- Performance Management
- Learning & Development
- Recruitment
- Compensation & Benefits
- Succession Planning
- Employee Onboarding
- Time & Attendance
- Employee Central
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS middleware for cross-origin requests from Joule
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint for Cloud Foundry and monitoring.

    Returns the service status, name, and version.
    """
    return HealthResponse(
        status="healthy",
        service="tm-intent-classifier",
        version="1.0.0",
    )


@app.post(
    "/api/v1/classify",
    response_model=ClassifyResponse,
    tags=["Classification"],
    summary="Classify a user query",
    description="Analyzes a user query to determine if it relates to Talent Management and identifies the specific topic.",
)
async def classify_query(request: ClassifyRequest):
    """
    Classify a user query for Talent Management topics.

    This endpoint uses GPT-4 via SAP GenAI Hub to analyze the query and:
    1. Determine if it relates to SAP SuccessFactors Talent Management
    2. Identify the specific topic (e.g., Performance Management, Learning)
    3. Return relevant SAP Help Portal links

    Set `show_pipeline: true` to include orchestration pipeline details (data masking,
    content filtering, LLM info) for demo purposes.

    **Example Request:**
    ```json
    {
        "query": "How do I submit my annual performance review?"
    }
    ```

    **Example Response (TM Query):**
    ```json
    {
        "is_talent_management": true,
        "confidence": 0.95,
        "topic": "performance_management",
        "topic_display_name": "Performance Management",
        "links": [...],
        "summary": "Your question is about Performance Management."
    }
    ```
    """
    try:
        classifier = get_classifier()
        result = classifier.classify(request.query, include_pipeline=request.show_pipeline)

        # Build pipeline details if requested
        pipeline = None
        if request.show_pipeline and "pipeline" in result:
            pipeline_data = result["pipeline"]
            pipeline = PipelineDetails(
                data_masking=DataMaskingDetails(**pipeline_data["data_masking"])
                if pipeline_data.get("data_masking")
                else None,
                content_filtering=ContentFilteringDetails(
                    input=ContentFilterScores(**pipeline_data["content_filtering"]["input"]),
                    output=ContentFilterScores(**pipeline_data["content_filtering"]["output"]),
                ),
                llm=LLMDetails(**pipeline_data["llm"]),
                messages_to_llm=[LLMMessage(**msg) for msg in pipeline_data["messages_to_llm"]],
            )

        return ClassifyResponse(
            is_talent_management=result["is_talent_management"],
            confidence=result["confidence"],
            topic=result["topic"],
            topic_display_name=result["topic_display_name"],
            links=[LinkInfo(**link) for link in result["links"]],
            summary=result["summary"],
            pipeline=pipeline,
        )
    except Exception as e:
        logger.error(f"Classification failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while classifying the query. Please try again.",
        )


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information."""
    return {
        "service": "Talent Management Intent Classifier API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "classify": "/api/v1/classify",
    }
