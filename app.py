"""
FastAPI Application for SAP AI Documentation Assistant

This API answers user questions about SAP AI services (AI Core, GenAI Hub,
Joule, HANA Cloud Vector Engine, etc.) using LLM tool calling against a
curated knowledge base of SAP Help Portal documentation.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from doc_assistant import get_assistant
from knowledge_base import (
    add_entry,
    delete_entry,
    get_all_entries,
    get_available_services,
    update_entry,
)
from models import (
    AskRequest,
    AskResponse,
    ContentFilteringDetails,
    ContentFilterScores,
    DataMaskingDetails,
    HealthResponse,
    KBEntryCreate,
    KBEntryResponse,
    KBEntryUpdate,
    LinkInfo,
    LLMDetails,
    LLMMessage,
    PipelineDetails,
    ToolCallDetails,
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
    logger.info("Initializing Documentation Assistant...")
    get_assistant()  # Pre-initialize the assistant
    logger.info("Application started successfully")
    yield
    logger.info("Application shutting down")


app = FastAPI(
    title="SAP AI Documentation Assistant API",
    description="""
Answers questions about SAP AI services and returns relevant documentation links.

## Features
- Answers questions about 6 SAP AI services with curated documentation links
- Uses GenAI Hub tool calling to search a knowledge base of 60+ SAP Help Portal entries
- Content filtering, PII data masking, and pipeline visibility for demos
- Runtime knowledge base management API

## SAP AI Services Covered
- SAP AI Core — model training and deployment
- Generative AI Hub — orchestration SDK, prompts, content filtering, RAG
- SAP AI Launchpad — UI, monitoring, MLOps
- SAP Joule — AI copilot skills and Joule Studio
- SAP HANA Cloud Vector Engine — vector storage and similarity search
- Document Information Extraction — AI document processing
    """,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS middleware for cross-origin requests
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
        service="sap-ai-doc-assistant",
        version="2.0.0",
    )


@app.post(
    "/api/v1/ask",
    response_model=AskResponse,
    tags=["Documentation Assistant"],
    summary="Ask a question about SAP AI services",
    description="Analyzes a user question, searches the knowledge base using LLM tool calling, and returns a detailed answer with documentation links.",
)
async def ask_question(request: AskRequest):
    """
    Ask a question about SAP AI services.

    This endpoint uses GPT-4o via SAP GenAI Hub with tool calling to:
    1. Search the knowledge base for relevant documentation
    2. Provide a detailed answer based on the search results
    3. Return curated SAP Help Portal links

    Set `show_pipeline: true` to include orchestration pipeline details
    (data masking, content filtering, LLM info, tool calls) for demos.

    **Example Request:**
    ```json
    {
        "question": "How do I deploy a model on SAP AI Core?"
    }
    ```
    """
    try:
        assistant = get_assistant()
        result = assistant.ask(request.question, include_pipeline=request.show_pipeline)

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
                tool_calls=[ToolCallDetails(**tc) for tc in pipeline_data["tool_calls"]]
                if pipeline_data.get("tool_calls")
                else None,
            )

        return AskResponse(
            is_sap_ai=result["is_sap_ai"],
            confidence=result["confidence"],
            services=result["services"],
            links=[LinkInfo(**link) for link in result["links"]],
            answer=result["answer"],
            pipeline=pipeline,
        )
    except Exception as e:
        logger.error(f"Question processing failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing the question. Please try again.",
        )


# --- Knowledge Base Management Endpoints ---


@app.get(
    "/api/v1/kb/entries",
    response_model=list[KBEntryResponse],
    tags=["Knowledge Base"],
    summary="List all KB entries",
)
async def list_kb_entries(
    service: str | None = Query(None, description="Filter by service key (e.g., 'ai_core')"),
):
    """List all knowledge base entries, optionally filtered by service."""
    entries = get_all_entries(service_filter=service)
    return [KBEntryResponse(**entry) for entry in entries]


@app.post(
    "/api/v1/kb/entries",
    response_model=KBEntryResponse,
    status_code=201,
    tags=["Knowledge Base"],
    summary="Add a new KB entry",
)
async def create_kb_entry(entry: KBEntryCreate):
    """Add a new documentation entry to the knowledge base."""
    doc_id = add_entry(
        service_key=entry.service_key,
        entry={
            "title": entry.title,
            "url": entry.url,
            "description": entry.description,
            "tags": entry.tags,
        },
    )
    if doc_id is None:
        raise HTTPException(
            status_code=404,
            detail=f"Service '{entry.service_key}' not found in knowledge base",
        )
    return KBEntryResponse(
        id=doc_id,
        service_key=entry.service_key,
        title=entry.title,
        url=entry.url,
        description=entry.description,
        tags=entry.tags,
    )


@app.put(
    "/api/v1/kb/entries/{doc_id}",
    response_model=dict,
    tags=["Knowledge Base"],
    summary="Update a KB entry",
)
async def update_kb_entry(doc_id: str, updates: KBEntryUpdate):
    """Update an existing knowledge base entry (partial update)."""
    update_dict = updates.model_dump(exclude_none=True)
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")

    success = update_entry(doc_id, update_dict)
    if not success:
        raise HTTPException(status_code=404, detail=f"Entry '{doc_id}' not found")
    return {"status": "updated", "id": doc_id}


@app.delete(
    "/api/v1/kb/entries/{doc_id}",
    response_model=dict,
    tags=["Knowledge Base"],
    summary="Delete a KB entry",
)
async def delete_kb_entry(doc_id: str):
    """Remove a documentation entry from the knowledge base."""
    success = delete_entry(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Entry '{doc_id}' not found")
    return {"status": "deleted", "id": doc_id}


@app.get(
    "/api/v1/kb/services",
    response_model=list[dict],
    tags=["Knowledge Base"],
    summary="List available services",
)
async def list_services():
    """List all available SAP AI services in the knowledge base."""
    return get_available_services()


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information."""
    return {
        "service": "SAP AI Documentation Assistant API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
        "ask": "/api/v1/ask",
        "kb_entries": "/api/v1/kb/entries",
        "kb_services": "/api/v1/kb/services",
    }
