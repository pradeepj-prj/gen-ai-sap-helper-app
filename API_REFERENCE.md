# SAP AI Documentation Assistant — API Reference for UI Integration

## Base URL
- Local: `http://localhost:8000`
- Production: Cloud Foundry deployment (see CF_COMMANDS.md)

## CORS
Enabled for all origins. No auth required for local dev.

---

## Core Endpoint

### POST /api/v1/ask
Ask a question about SAP AI services. The backend uses GPT-4o with tool calling to search a knowledge base of 60+ SAP Help Portal entries.

**Request:**
```json
{
  "question": "How do I deploy a model on SAP AI Core?",
  "show_pipeline": true
}
```
- `question` (string, required, max 2000 chars)
- `show_pipeline` (boolean, optional, default false) — include orchestration pipeline details

**Response (success):**
```json
{
  "is_sap_ai": true,
  "confidence": 0.95,
  "services": ["ai_core"],
  "links": [
    {
      "title": "Deploy Models",
      "url": "https://help.sap.com/docs/sap-ai-core/...",
      "description": "Guide to deploying AI models as inference endpoints"
    }
  ],
  "answer": "To deploy a model on SAP AI Core, you need to...",
  "pipeline": null
}
```

**Response fields:**
| Field | Type | Description |
|-------|------|-------------|
| `is_sap_ai` | boolean | Whether the question relates to SAP AI services |
| `confidence` | float (0-1) | How well the KB covers the question |
| `services` | string[] | Matched service keys: `ai_core`, `genai_hub`, `ai_launchpad`, `joule`, `hana_cloud_vector`, `document_processing` |
| `links` | object[] | Relevant SAP Help Portal docs (title, url, description) |
| `answer` | string | 1-2 paragraph detailed answer |
| `pipeline` | object\|null | Pipeline details (only when `show_pipeline: true`) |

**Pipeline object (when `show_pipeline: true`):**
```json
{
  "pipeline": {
    "data_masking": {
      "original_query": "Pradeep asked about AI Core",
      "masked_query": "MASKED_PERSON asked about AI Core",
      "entities_masked": ["PERSON"]
    },
    "content_filtering": {
      "input": { "hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": true },
      "output": { "hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": true }
    },
    "llm": {
      "model": "gpt-4o-2024-08-06",
      "prompt_tokens": 1953,
      "completion_tokens": 226
    },
    "messages_to_llm": [
      { "role": "system", "content": "You are an SAP AI documentation..." },
      { "role": "user", "content": "MASKED_PERSON asked about AI Core" }
    ],
    "tool_calls": [
      {
        "tool_name": "search_knowledge_base",
        "arguments": { "query": "deploy model", "service": "ai_core" },
        "result_count": 10,
        "results_preview": [
          { "id": "aicore_deploy_08", "title": "Deploy Models" }
        ]
      }
    ]
  }
}
```

**Response when content filtering blocks (HTTP 200, not an error):**
```json
{
  "is_sap_ai": false,
  "confidence": 0.0,
  "services": [],
  "links": [],
  "answer": "Your question was blocked by content filtering. Please rephrase your question.",
  "pipeline": {
    "content_filtering": {
      "input": { "hate": 4, "self_harm": 0, "sexual": 0, "violence": 0, "passed": false }
    },
    "llm": { "model": "blocked", "blocked_by": "Input Filter", "reason": "..." }
  }
}
```

**Response for non-SAP questions:**
```json
{
  "is_sap_ai": false,
  "confidence": 0.8,
  "services": [],
  "links": [],
  "answer": "This doesn't appear to be related to SAP AI services. I can help with..."
}
```

---

## Knowledge Base Endpoints

### GET /api/v1/kb/entries
List all KB entries. Optional filter: `?service=ai_core`

### POST /api/v1/kb/entries
```json
{
  "service_key": "ai_core",
  "title": "New Doc",
  "url": "https://...",
  "description": "Description here",
  "tags": ["deploy", "model"]
}
```
Returns 201 with the created entry (including generated `id`).

### PUT /api/v1/kb/entries/{doc_id}
Partial update. Returns `{"status": "updated", "id": "..."}`.

### DELETE /api/v1/kb/entries/{doc_id}
Returns `{"status": "deleted", "id": "..."}` or 404.

### GET /api/v1/kb/services
Returns list of categories: `[{"key": "ai_core", "display_name": "SAP AI Core", "description": "...", "doc_count": 10}]`

---

## Health

### GET /health
```json
{"status": "healthy", "service": "sap-ai-doc-assistant", "version": "2.0.0"}
```

---

## SAP AI Services (for UI display)

| Key | Display Name | Icon Suggestion |
|-----|-------------|-----------------|
| `ai_core` | SAP AI Core | server/cloud |
| `genai_hub` | Generative AI Hub | brain/sparkle |
| `ai_launchpad` | SAP AI Launchpad | dashboard/monitor |
| `joule` | SAP Joule | robot/assistant |
| `hana_cloud_vector` | SAP HANA Cloud Vector Engine | database/vector |
| `document_processing` | Document Information Extraction | document/scan |

---

## UI Integration Notes

- The `/api/v1/ask` endpoint takes 3-8 seconds for real LLM responses (two LLM round-trips with tool calling). Show a loading state.
- `show_pipeline: true` adds ~0 latency but increases response payload. Good for a "debug/demo" toggle in the UI.
- `links` array may be empty for non-SAP questions. Always check `is_sap_ai` first.
- `services` array can contain multiple services for cross-cutting questions.
- The `answer` field is plain text (not markdown). It's typically 1-2 paragraphs.
- Content-filtered responses return HTTP 200 (not 4xx) — check `is_sap_ai: false` + `confidence: 0.0` pattern.
- Mock mode (no AI Core) prefixes answers with `[MOCK]` — useful for detecting during UI dev.

## Running the Backend
```bash
cd /Users/I774404/gen-ai-sap-helper-app
uvicorn app:app --reload --port 8000
```
Swagger UI at http://localhost:8000/docs
