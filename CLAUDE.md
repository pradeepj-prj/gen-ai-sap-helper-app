# SAP AI Documentation Assistant API

## Project Overview
A FastAPI application that answers questions about SAP AI services using LLM tool calling against a curated knowledge base of SAP Help Portal documentation.

## Architecture
- **Framework:** FastAPI with Pydantic models
- **LLM:** GPT-4o via SAP GenAI Hub Orchestration SDK (tool calling)
- **Knowledge Base:** JSON file with 60+ entries across 6 SAP AI services
- **Deployment:** Cloud Foundry with AI Core service binding

## Key Files
- `app.py` - FastAPI application with `/api/v1/ask` endpoint + KB management routes
- `doc_assistant.py` - GenAI Hub SDK integration with tool calling agentic loop
- `knowledge_base.py` - KB loading, search tool function, CRUD management
- `knowledge_base.json` - Persistent storage for documentation entries (~60 entries)
- `models.py` - Pydantic request/response schemas

## How It Works
1. User asks a question via `POST /api/v1/ask`
2. Data masking anonymizes PII (SAP DPI)
3. Content filtering checks input (Azure Content Safety)
4. LLM Call 1: GPT-4o receives question + `search_knowledge_base` tool definition
5. LLM calls the tool → Python searches `knowledge_base.json`
6. LLM Call 2: GPT-4o receives search results, writes detailed answer + selects doc IDs
7. Code validates doc_ids, looks up full entries, returns response with links

## Running Locally
```bash
pip install -r requirements.txt
uvicorn app:app --reload    # Runs with mock LLM responses
python test_local.py        # Run all tests
```

## API Endpoints
- `POST /api/v1/ask` - Ask a question about SAP AI services
- `GET /api/v1/kb/entries` - List KB entries (optional `?service=ai_core` filter)
- `POST /api/v1/kb/entries` - Add a new KB entry
- `PUT /api/v1/kb/entries/{doc_id}` - Update an entry
- `DELETE /api/v1/kb/entries/{doc_id}` - Delete an entry
- `GET /api/v1/kb/services` - List available services
- `GET /health` - Health check
- `GET /docs` - Swagger UI

## SAP AI Services Covered
1. **SAP AI Core** — model training, deployment, resource groups, AI API
2. **Generative AI Hub** — orchestration SDK, prompts, content filtering, grounding, RAG
3. **SAP AI Launchpad** — UI, monitoring, MLOps, model registry
4. **SAP Joule** — skills, Joule Studio, actions, capabilities
5. **SAP HANA Cloud Vector Engine** — vector storage, embeddings, similarity search
6. **Document Information Extraction** — DOX service, schemas, extraction

## Features
- **Tool Calling** — LLM searches KB via `search_knowledge_base()` function tool
- **Detailed Answers** — 1-2 paragraph explanations with curated doc links
- **Pipeline Visibility** — `show_pipeline: true` exposes data masking, content filtering, LLM details, and tool call details
- **Content Filtering** — Azure Content Safety filters harmful content
- **Data Masking** — PII anonymization via SAP Data Privacy Integration
- **KB Management API** — Add/update/delete entries at runtime
- **Mock Fallback** — Works locally without GenAI Hub SDK

## Cloud Foundry Deployment
- **App name:** sap-ai-doc-assistant
- **Region:** AP10 (Australia)
- **API endpoint:** https://api.cf.ap10.hana.ondemand.com
- **Service binding:** default_aicore (AI Core)
- **Health check:** /health

See `CF_COMMANDS.md` for deployment commands.
