# SAP AI Documentation Assistant API

A FastAPI service that answers questions about SAP AI services using LLM tool calling against a curated knowledge base of 60+ SAP Help Portal documentation entries.

## Features

- Answers questions about 6 SAP AI services with detailed explanations
- Uses GenAI Hub tool calling to search a knowledge base dynamically
- Returns curated SAP Help Portal documentation links
- **Content Filtering**: Azure Content Safety checks for harmful content
- **Data Masking**: Automatic PII anonymization before LLM processing
- **Pipeline Visibility**: Optional detailed view of orchestration steps including tool calls
- **KB Management API**: Add, update, and delete documentation entries at runtime
- Mock fallback for local development without GenAI Hub

## How It Works

The assistant uses SAP GenAI Hub's Orchestration Service with tool calling:

1. **Data Masking**: PII (names, emails, phone numbers) is anonymized via SAP Data Privacy Integration
2. **Input Content Filtering**: Azure Content Safety scans for harmful content
3. **LLM Call 1**: GPT-4o receives the question + a `search_knowledge_base` tool definition
4. **Tool Execution**: The LLM calls the search tool — Python searches `knowledge_base.json` and returns matching docs
5. **LLM Call 2**: GPT-4o receives search results, writes a detailed answer, and selects the most relevant doc IDs
6. **Output Content Filtering**: Response is scanned before being returned
7. **Response**: Validated links from the knowledge base + detailed answer

## SAP AI Services Covered

| Service | Key | Example Topics |
|---------|-----|----------------|
| SAP AI Core | `ai_core` | Deployments, resource groups, serving templates, AI API |
| Generative AI Hub | `genai_hub` | Orchestration SDK, content filtering, grounding, RAG |
| SAP AI Launchpad | `ai_launchpad` | UI, monitoring, MLOps, model registry |
| SAP Joule | `joule` | Skills, Joule Studio, actions, capabilities |
| HANA Cloud Vector Engine | `hana_cloud_vector` | Vector storage, embeddings, similarity search |
| Document Information Extraction | `document_processing` | Invoice extraction, schemas, DOX API |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (uses mock responses)
uvicorn app:app --reload

# Run tests
python test_local.py
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/ask` | Ask a question about SAP AI services |
| GET | `/api/v1/kb/entries` | List KB entries (filter: `?service=ai_core`) |
| POST | `/api/v1/kb/entries` | Add a new KB entry |
| PUT | `/api/v1/kb/entries/{doc_id}` | Update an entry |
| DELETE | `/api/v1/kb/entries/{doc_id}` | Delete an entry |
| GET | `/api/v1/kb/services` | List available services |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger UI |

## Example Request

```bash
curl -X POST http://localhost:8000/api/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How do I deploy a model on SAP AI Core?"}'
```

## Example Response

```json
{
  "is_sap_ai": true,
  "confidence": 0.95,
  "services": ["ai_core"],
  "links": [
    {
      "title": "Deploy Models",
      "url": "https://help.sap.com/docs/sap-ai-core/sap-ai-core-service-guide/deploy-models",
      "description": "Guide to deploying AI models as inference endpoints on SAP AI Core"
    },
    {
      "title": "Serving Templates",
      "url": "https://help.sap.com/docs/sap-ai-core/sap-ai-core-service-guide/serving-templates",
      "description": "Defining deployment templates using KServe notation for model serving"
    }
  ],
  "answer": "To deploy a model on SAP AI Core, you need to create a serving template that defines the model server configuration using KServe notation. Register it as a scenario, then create a deployment configuration specifying the resource group and model artifacts. You can trigger the deployment through the AI Core API or the AI Launchpad UI."
}
```

## Pipeline Visibility (Demo Feature)

For demos and debugging, set `show_pipeline: true` to see orchestration details including tool calls:

```bash
curl -X POST http://localhost:8000/api/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How do I set up RAG with HANA?", "show_pipeline": true}'
```

This returns additional details:

```json
{
  "is_sap_ai": true,
  "pipeline": {
    "data_masking": null,
    "content_filtering": {
      "input": {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": true},
      "output": {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": true}
    },
    "llm": {
      "model": "gpt-4o",
      "prompt_tokens": 580,
      "completion_tokens": 210
    },
    "messages_to_llm": [
      {"role": "system", "content": "You are an SAP AI documentation expert..."},
      {"role": "user", "content": "How do I set up RAG with HANA?"}
    ],
    "tool_calls": [
      {
        "tool_name": "search_knowledge_base",
        "arguments": {"query": "RAG HANA vector", "service": "hana_cloud_vector"},
        "result_count": 8,
        "results_preview": [
          {"id": "hana_vector_embeddings_03", "title": "Vectors, Vector Embeddings, and Similarity Measures"},
          {"id": "hana_vector_auto_embed_08", "title": "Creating Vector Embeddings Automatically"}
        ]
      }
    ]
  }
}
```

## KB Management

Add a new documentation entry at runtime:

```bash
curl -X POST http://localhost:8000/api/v1/kb/entries \
  -H "Content-Type: application/json" \
  -d '{
    "service_key": "ai_core",
    "title": "Custom Model Serving",
    "url": "https://help.sap.com/docs/sap-ai-core/custom-serving",
    "description": "Guide to serving custom ML models",
    "tags": ["custom", "serving", "models"]
  }'
```

## Deployment

### Cloud Foundry

```bash
cf push
```

The app binds to an AI Core service instance configured in `manifest.yml`.

### Environment Variables

For local development with GenAI Hub, set these variables (see `.env.example`):

- `AICORE_AUTH_URL`
- `AICORE_CLIENT_ID`
- `AICORE_CLIENT_SECRET`
- `AICORE_BASE_URL`
- `AICORE_RESOURCE_GROUP`
