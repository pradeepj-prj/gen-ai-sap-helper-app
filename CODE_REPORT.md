# SAP AI Documentation Assistant — Architecture & Implementation Report

## Table of Contents

1. [What This Application Does](#1-what-this-application-does)
2. [High-Level Architecture](#2-high-level-architecture)
3. [How the Files Fit Together](#3-how-the-files-fit-together)
4. [The Agentic Tool Calling Pattern](#4-the-agentic-tool-calling-pattern)
5. [Knowledge Base Design](#5-knowledge-base-design)
6. [The Search Algorithm](#6-the-search-algorithm)
7. [LLM Integration & Orchestration SDK](#7-llm-integration--orchestration-sdk)
8. [Content Filtering](#8-content-filtering)
9. [Data Masking (PII Anonymization)](#9-data-masking-pii-anonymization)
10. [Pipeline Visibility](#10-pipeline-visibility)
11. [API Layer & Pydantic Models](#11-api-layer--pydantic-models)
12. [Mock Mode & Graceful Degradation](#12-mock-mode--graceful-degradation)
13. [Testing Strategy](#13-testing-strategy)
14. [Key Design Decisions & Trade-offs](#14-key-design-decisions--trade-offs)
15. [Deployment](#15-deployment)

---

## 1. What This Application Does

This is a **REST API** that answers questions about SAP AI services. When a user sends a question like *"How do I deploy a model on SAP AI Core?"*, the app:

1. Anonymizes any personal information in the question (names, emails, etc.)
2. Checks the question for harmful content (hate speech, violence, etc.)
3. Sends the question to GPT-4o, which decides to search a knowledge base
4. Executes the search against 60+ curated SAP documentation entries
5. Sends the search results back to GPT-4o, which writes a detailed answer
6. Returns the answer along with relevant SAP Help Portal links

The app covers 6 SAP AI services: AI Core, Generative AI Hub, AI Launchpad, Joule, HANA Cloud Vector Engine, and Document Information Extraction.

---

## 2. High-Level Architecture

```
┌─────────────┐      POST /api/v1/ask       ┌──────────────────┐
│   Client     │  ─────────────────────────> │   FastAPI (app.py)│
│  (UI/curl)   │  <───────────────────────── │                  │
└─────────────┘      JSON response           └────────┬─────────┘
                                                      │
                                              calls get_assistant().ask()
                                                      │
                                                      ▼
                                            ┌─────────────────────┐
                                            │  DocAssistant        │
                                            │  (doc_assistant.py)  │
                                            │                     │
                                            │  Data Masking ──────│──> SAP DPI (anonymize PII)
                                            │  Content Filter ────│──> Azure Content Safety
                                            │  LLM Call 1 ────────│──> GPT-4o (via SAP AI Core)
                                            │    └─ tool_calls ───│──> search_knowledge_base()
                                            │  LLM Call 2 ────────│──> GPT-4o (with search results)
                                            │                     │
                                            └────────┬────────────┘
                                                     │
                                                     │ calls search function
                                                     ▼
                                            ┌─────────────────────┐
                                            │  knowledge_base.py   │
                                            │  (search, CRUD)      │
                                            └────────┬────────────┘
                                                     │
                                                     │ reads/writes
                                                     ▼
                                            ┌─────────────────────┐
                                            │  knowledge_base.json │
                                            │  (60 entries, 6 svcs)│
                                            └─────────────────────┘
```

**Key architectural property:** The knowledge base module (`knowledge_base.py`) has zero dependencies on the LLM layer. It is a pure data module — load, search, CRUD. This clean separation means you could swap the LLM provider or even remove it entirely and the KB would still work independently.

---

## 3. How the Files Fit Together

| File | Role | Lines | Dependencies |
|------|------|-------|-------------|
| `app.py` | HTTP layer — routes, validation, CORS | ~278 | `doc_assistant`, `knowledge_base`, `models` |
| `doc_assistant.py` | LLM orchestration — the "brain" | ~689 | `knowledge_base`, GenAI Hub SDK |
| `knowledge_base.py` | Data layer — search, CRUD, caching | ~312 | `knowledge_base.json` (file I/O only) |
| `knowledge_base.json` | Persistent storage — 60 doc entries | ~1500 | None (pure data) |
| `models.py` | Pydantic schemas for request/response | ~199 | None (Pydantic only) |
| `test_local.py` | Test suite — 11 tests | ~369 | All of the above |

**Dependency flow:**

```
app.py ──> doc_assistant.py ──> knowledge_base.py ──> knowledge_base.json
  │                                     ▲
  └─────────────────────────────────────┘  (KB management endpoints skip the LLM)
```

The FastAPI app imports from all three modules, but the critical insight is that the **KB management endpoints** (`GET/POST/PUT/DELETE /api/v1/kb/entries`) go directly to `knowledge_base.py` without touching `doc_assistant.py` at all. Only the `/api/v1/ask` endpoint invokes the LLM layer.

---

## 4. The Agentic Tool Calling Pattern

This is the most important architectural concept in the application. Rather than hard-coding "search the KB, then call the LLM", we let the LLM **decide for itself** when and how to search.

### How It Works (two LLM round-trips)

**Step 1 — First LLM Call:**
The user's question is sent to GPT-4o along with a *tool definition* — a JSON schema that describes the `search_knowledge_base` function (its name, description, parameters). The LLM reads the question and responds not with text, but with a **tool call request**: *"I'd like to call `search_knowledge_base` with `query='deploy model'` and `service='ai_core'`."*

**Step 2 — Tool Execution:**
Our Python code intercepts this tool call request, parses the arguments, and calls the actual `search_knowledge_base()` function locally. The search results (up to 10 matching docs) are serialized to JSON.

**Step 3 — Second LLM Call:**
The search results are sent back to the LLM as a `ToolChatMessage`. The LLM now has the user's question AND the matching KB entries, so it writes a detailed answer and selects the most relevant `doc_ids`.

```python
# Simplified flow from doc_assistant.py _run_with_tools()

# First LLM call — LLM receives question + tool definition
result = service.run(config=config, placeholder_values={"user_question": question})
msg = result.final_result.choices[0].message

# LLM chose to call a tool
if msg.tool_calls:
    for tc in msg.tool_calls:
        args = json.loads(tc.function.arguments)        # e.g. {"query": "deploy model", "service": "ai_core"}
        tool_result = search_knowledge_base(**args)      # Execute locally
        history.append(ToolChatMessage(content=str(tool_result), tool_call_id=tc.id))

    # Second LLM call — LLM now has search results in context
    result = service.run(config=config, placeholder_values={"user_question": question}, history=history)
```

### Why This Pattern (vs. Simpler Alternatives)

**Alternative 1: "Just search and summarize"** — We could skip the first LLM call, search the KB ourselves based on keywords, and pass the results to the LLM to summarize. This is simpler but worse because:
- The LLM is much better at reformulating search queries than simple keyword extraction
- The LLM can choose to filter by service based on context
- The LLM could (in theory) make multiple search calls with different queries

**Alternative 2: RAG with vector embeddings** — We could embed all KB entries as vectors and do similarity search. This would avoid the first LLM call but requires:
- An embedding model and vector store infrastructure
- Re-embedding whenever KB entries change
- More complex setup for a 60-entry knowledge base where keyword search works well

The tool calling pattern is a good middle ground — the LLM handles query understanding, but search execution stays local and fast.

### The Tool Definition

The tool is defined as a plain Python dictionary (not a decorator or SDK class). This is intentional — it keeps the tool definition independent of any SDK import:

```python
SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_knowledge_base",
        "description": "Search the SAP AI documentation knowledge base...",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search terms..."},
                "service": {"type": "string", "description": "Optional service key..."},
            },
            "required": ["query"],
        },
    },
}
```

This follows the OpenAI function calling schema (which the SAP Orchestration Service also uses). The `service` parameter is optional — the LLM may or may not include it depending on the question.

### JSON Schema Response Formatting

The second LLM call is constrained to output a specific JSON structure using `ResponseFormatJsonSchema`. This forces GPT-4o to return exactly:

```json
{
    "is_sap_ai": true,
    "confidence": 0.95,
    "services": ["ai_core"],
    "doc_ids": ["aicore_deploy_08", "aicore_overview_01"],
    "answer": "To deploy a model on SAP AI Core, you need to..."
}
```

Without this schema constraint, the LLM might return free-form text, wrap the JSON in markdown code blocks, or include extra fields — making parsing unreliable. The schema is defined in `ASSISTANT_SCHEMA` (line 74 of `doc_assistant.py`) and enforced through the Orchestration SDK's `ResponseFormatJsonSchema` wrapper.

---

## 5. Knowledge Base Design

### Data Structure (`knowledge_base.json`)

```json
{
    "services": {
        "ai_core": {
            "display_name": "SAP AI Core",
            "description": "Runtime for AI model training, deployment, and inference on SAP BTP",
            "docs": [
                {
                    "id": "aicore_overview_01",
                    "title": "What Is SAP AI Core?",
                    "url": "https://help.sap.com/docs/sap-ai-core/...",
                    "description": "Main overview of SAP AI Core as an engine for...",
                    "tags": ["overview", "getting started", "introduction"]
                }
            ]
        },
        "genai_hub": { ... },
        "ai_launchpad": { ... },
        "joule": { ... },
        "hana_cloud_vector": { ... },
        "document_processing": { ... }
    }
}
```

**Structure rationale:**
- **Grouped by service** — not a flat array. This enables service-filtered searches and makes the file navigable by humans.
- **Each service has metadata** — `display_name` and `description` are used in the LLM system prompt and in search scoring.
- **Each doc has an ID** — prefixed with the service key (e.g., `aicore_deploy_08`). The LLM returns these IDs, and the code validates them against the KB before returning links to the user. This prevents the LLM from hallucinating URLs.
- **Tags are explicit** — rather than relying on NLP to extract keywords from descriptions, each entry has curated tags. These get a high weight (2.5) in the search scoring.

### In-Memory Caching

```python
_kb_cache: dict | None = None

def load_knowledge_base() -> dict:
    global _kb_cache
    if _kb_cache is not None:
        return _kb_cache          # Return cached version
    with open(KB_FILE) as f:
        _kb_cache = json.load(f)  # Load and cache on first call
    return _kb_cache
```

The KB is loaded from disk once and stored in the module-level `_kb_cache` variable. Every subsequent call to `load_knowledge_base()` returns the cached dict — no file I/O. This is safe because:

1. The KB only changes via the CRUD API (`add_entry`, `update_entry`, `delete_entry`)
2. Every mutation calls `save_knowledge_base()`, which updates both the file AND the cache
3. For testing, `_invalidate_cache()` forces a reload from disk

This is a deliberate trade-off: the app doesn't handle external edits to `knowledge_base.json` while running (you'd need to restart the server). But for a single-process API, this is the right simplicity/performance balance.

---

## 6. The Search Algorithm

The search function (`search_knowledge_base`, line 70 of `knowledge_base.py`) uses **weighted keyword scoring** — not vector similarity or fuzzy matching.

### How Scoring Works

For each KB entry, the algorithm:
1. Splits the query into individual terms (whitespace-separated)
2. Checks each term against 5 text fields, with different weights:

| Field | Weight | Rationale |
|-------|--------|-----------|
| `title` | 3.0 | Title match is the strongest signal |
| `tags` | 2.5 | Curated tags are precise |
| `description` | 2.0 | Descriptions are longer, more generic |
| `display_name` (service) | 1.5 | Service-level match |
| `description` (service) | 0.5 | Weakest signal — very broad |

3. Terms shorter than 2 characters are skipped (avoids matching on "a", "I", etc.)
4. Scores are accumulated across all terms — a query with more matching terms gets a higher score
5. Results are sorted by score descending, top 10 returned

### Example

For the query `"deploy model ai core"`:

| Term | `aicore_deploy_08` (Deploy Models) | `genai_sdk_03` (Python SDK) |
|------|------------------------------------|-----------------------------|
| `deploy` | title: +3.0, tags: +2.5, desc: +2.0 | desc: +2.0 |
| `model` | title: +3.0, desc: +2.0 | — |
| `ai` | title: — , svc_name: +1.5 | svc_name: +1.5 |
| `core` | svc_name: +1.5 | — |
| **Total** | **15.5** | **3.5** |

The "Deploy Models" entry in AI Core wins decisively.

### Why Not Vector Search?

For 60 entries, keyword scoring is:
- **Fast** — no embedding model calls, no vector DB
- **Transparent** — you can debug why a result ranked high
- **Good enough** — with curated tags, keyword matching covers the vocabulary well

Vector similarity would be overkill here and would add significant infrastructure complexity (embedding model, vector store, re-indexing on mutations). If the KB grew to thousands of entries, vector search would make more sense.

### Return Format

`search_knowledge_base()` returns a **JSON string**, not a Python list. This is intentional — the LLM tool calling protocol requires tool results to be strings. The function is designed to be called as an LLM tool, so its output format matches that contract:

```python
return json.dumps(top_results)  # String, not list — for LLM consumption
```

---

## 7. LLM Integration & Orchestration SDK

### SDK Version: V2 (`sap-ai-sdk-gen`)

The app uses SAP's **Orchestration Service V2** SDK (`gen_ai_hub.orchestration_v2`). This is important because V1 (`generative-ai-hub-sdk`) is deprecated. The V2 API has significant structural differences.

### Configuration Architecture

V2 uses a **nested configuration** pattern:

```python
# LLM model selection
llm = LLMModelDetails(name="gpt-4o", params={"max_tokens": 1000})

# Prompt template (combines messages + model + tools + response format)
prompt_template = PromptTemplatingModuleConfig(
    prompt=Template(
        template=[SystemMessage(...), UserMessage(...)],
        tools=[SEARCH_TOOL],
        response_format=ResponseFormatJsonSchema(...)
    ),
    model=llm,
)

# Top-level config bundles all modules
config = OrchestrationConfig(
    modules=ModuleConfig(
        prompt_templating=prompt_template,
        filtering=content_filter,
        masking=data_masking,
    ),
)
```

This nesting (`OrchestrationConfig` > `ModuleConfig` > individual module configs) is a V2 design choice. In V1, everything was flat.

### Stateless Service

```python
self._service = OrchestrationService()  # No config passed to constructor!
result = self._service.run(config=self._config, placeholder_values={...})
```

The `OrchestrationService()` is stateless — you pass the config on every `run()` call. This means you could theoretically use different configs for different requests (e.g., different models or filtering thresholds per user). The current implementation uses one shared config.

### Template Placeholders

The user's question is injected into the prompt via a placeholder:

```python
UserMessage(content="{{?user_question}}")  # {{?...}} is the V2 placeholder syntax
```

At runtime, `placeholder_values={"user_question": question}` fills it in. The `?` prefix means the placeholder is optional (won't error if missing).

---

## 8. Content Filtering

Content filtering uses **Azure Content Safety**, applied to both input (user's question) and output (LLM's response).

### Configuration

```python
azure_config = AzureContentFilter(
    hate=AzureThreshold.ALLOW_SAFE,              # Strictest — only clearly safe content
    violence=AzureThreshold.ALLOW_SAFE_LOW,       # Allows safe + low severity
    self_harm=AzureThreshold.ALLOW_SAFE_LOW_MEDIUM,  # More permissive
    sexual=AzureThreshold.ALLOW_SAFE_LOW_MEDIUM,     # More permissive
)
```

### Threshold Levels (from strictest to most permissive)

| Threshold | Meaning |
|-----------|---------|
| `ALLOW_SAFE` | Only content with severity 0 passes |
| `ALLOW_SAFE_LOW` | Severity 0-2 passes |
| `ALLOW_SAFE_LOW_MEDIUM` | Severity 0-4 passes |
| `ALLOW_ALL` | Everything passes (filtering disabled) |

The rationale for the current thresholds:
- **Hate speech is strict** (`ALLOW_SAFE`) — a documentation assistant should never process hateful queries
- **Violence is moderately strict** (`ALLOW_SAFE_LOW`) — some SAP docs discuss "killing" processes, server "termination", etc.
- **Self-harm and sexual are more permissive** (`ALLOW_SAFE_LOW_MEDIUM`) — unlikely to appear in SAP doc queries, so a wider threshold avoids false positives

### What Happens When Filtering Blocks

When input filtering blocks a request, the SAP Orchestration Service raises an `OrchestrationError`. The code catches this and returns a specific response:

```python
except OrchestrationError as e:
    response = self._content_filtered_response(question, str(e))
    if include_pipeline:
        response["pipeline"] = self._extract_pipeline_from_error(question, e)
```

The response is HTTP 200 (not 4xx) with `is_sap_ai: false` and `confidence: 0.0`. This is a deliberate choice — content filtering is an expected outcome, not an error. The pipeline details still include the filtering scores so the UI can show what triggered the block.

### Content Filter Wrapping (V2 Specificity)

V2 requires wrapping `AzureContentFilter` in a `ContentFilter` envelope:

```python
content_filter = ContentFilter(type="azure_content_safety", config=azure_config)
```

This extra layer exists because V2's architecture supports pluggable filter types. If SAP adds a new content safety provider in the future, the same `ContentFilter` wrapper would be used with a different `type` string.

---

## 9. Data Masking (PII Anonymization)

Before the question reaches the LLM, SAP's **Data Privacy Integration (DPI)** scans it for personally identifiable information and replaces it with tokens.

### Entities Masked

```python
entities=[
    DPIStandardEntity(type=ProfileEntity.PERSON),            # "Pradeep" → "MASKED_PERSON"
    DPIStandardEntity(type=ProfileEntity.ORG),               # "SAP SE" → "MASKED_ORG"
    DPIStandardEntity(type=ProfileEntity.EMAIL),             # "user@sap.com" → "MASKED_EMAIL"
    DPIStandardEntity(type=ProfileEntity.PHONE),             # "+1-555-0123" → "MASKED_PHONE"
    DPIStandardEntity(type=ProfileEntity.ADDRESS),           # Physical addresses
    DPIStandardEntity(type=ProfileEntity.USERNAME_PASSWORD),  # Credentials
    DPIStandardEntity(type=ProfileEntity.SAP_IDS_INTERNAL),  # Internal SAP IDs (I/D/C numbers)
    DPIStandardEntity(type=ProfileEntity.SAP_IDS_PUBLIC),    # Public SAP customer numbers
]
```

### How It Works in the Pipeline

1. User sends: *"Pradeep from SAP asked how to deploy a model"*
2. DPI masks: *"MASKED_PERSON from MASKED_ORG asked how to deploy a model"*
3. The masked query goes to GPT-4o — the LLM never sees the original PII
4. The response refers to "MASKED_PERSON" but the pipeline details show both original and masked versions

The masking method is `ANONYMIZATION` (one-way), not `PSEUDONYMIZATION` (reversible). The original PII is never sent to the LLM.

### V2 Masked Template Format

This is a notable V2 implementation detail: the masked template comes back as a **JSON array of message objects**, not a flat string:

```json
[
    {"role": "system", "content": "You are an SAP AI documentation expert..."},
    {"role": "user", "content": "MASKED_PERSON from MASKED_ORG asked how to deploy a model"}
]
```

The pipeline extraction code parses this JSON to find the user message and extract the masked query (see `_extract_pipeline_details()`, line 367 of `doc_assistant.py`).

---

## 10. Pipeline Visibility

When a request includes `show_pipeline: true`, the response includes a `pipeline` object that exposes every step of the orchestration process. This was built for demos and debugging.

### What the Pipeline Shows

```json
{
    "pipeline": {
        "data_masking": {
            "original_query": "Pradeep asked about AI Core",
            "masked_query": "MASKED_PERSON asked about AI Core",
            "entities_masked": ["PERSON"]
        },
        "content_filtering": {
            "input": {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": true},
            "output": {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": true}
        },
        "llm": {
            "model": "gpt-4o-2024-08-06",
            "prompt_tokens": 1953,
            "completion_tokens": 226
        },
        "messages_to_llm": [
            {"role": "system", "content": "You are an SAP AI documentation..."},
            {"role": "user", "content": "MASKED_PERSON asked about AI Core"}
        ],
        "tool_calls": [
            {
                "tool_name": "search_knowledge_base",
                "arguments": {"query": "deploy model", "service": "ai_core"},
                "result_count": 10,
                "results_preview": [{"id": "aicore_deploy_08", "title": "Deploy Models"}]
            }
        ]
    }
}
```

### How Pipeline Data is Extracted

The V2 Orchestration SDK returns an `intermediate_results` object on every response. This object has sub-fields for each module:

```python
mr = result.intermediate_results
mr.input_masking       # Data masking results
mr.input_filtering     # Input content filter results
mr.output_filtering    # Output content filter results
mr.templating          # The resolved prompt messages
```

The `_extract_pipeline_details()` method (line 367) reads from each of these sub-fields. A few non-obvious implementation details:

1. **The `passed` field** is derived from the `message` attribute of each filtering result (e.g., `"Filtering passed successfully."`) — there's no explicit boolean field in V2.

2. **`messages_to_llm`** shows the post-masking messages (what the LLM actually received), not the pre-masking template. When masking is active, it reads from `mr.input_masking.data["masked_template"]` rather than `mr.templating`.

3. **Error pipeline** (`_extract_pipeline_from_error()`, line 602) uses the same extraction logic but reads from `error.intermediate_results`. This is important because even when content filtering blocks a request, the intermediate results still contain the masking and filtering data. The V2 `OrchestrationError` exposes `intermediate_results` as the same `ModuleResults` type used on the success path.

---

## 11. API Layer & Pydantic Models

### FastAPI Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Health check for CF/monitoring |
| `POST` | `/api/v1/ask` | Ask a question (main endpoint) |
| `GET` | `/api/v1/kb/entries` | List KB entries (optional `?service=` filter) |
| `POST` | `/api/v1/kb/entries` | Add a new KB entry |
| `PUT` | `/api/v1/kb/entries/{doc_id}` | Update an entry (partial) |
| `DELETE` | `/api/v1/kb/entries/{doc_id}` | Delete an entry |
| `GET` | `/api/v1/kb/services` | List available services |

### Pydantic Model Hierarchy

```
AskRequest
  ├── question: str (1-2000 chars)
  └── show_pipeline: bool (default false)

AskResponse
  ├── is_sap_ai: bool
  ├── confidence: float (0.0-1.0)
  ├── services: list[str]
  ├── links: list[LinkInfo]
  │     └── title, url, description
  ├── answer: str
  └── pipeline: PipelineDetails | None
        ├── data_masking: DataMaskingDetails | None
        │     └── original_query, masked_query, entities_masked
        ├── content_filtering: ContentFilteringDetails
        │     ├── input: ContentFilterScores
        │     └── output: ContentFilterScores
        │           └── hate, self_harm, sexual, violence, passed
        ├── llm: LLMDetails
        │     └── model, prompt_tokens, completion_tokens
        ├── messages_to_llm: list[LLMMessage]
        │     └── role, content
        └── tool_calls: list[ToolCallDetails] | None
              └── tool_name, arguments, result_count, results_preview
```

### Why Pydantic?

Pydantic models serve three purposes simultaneously:
1. **Request validation** — `AskRequest` rejects questions longer than 2000 characters or empty strings
2. **Response serialization** — ensures every API response has the exact shape clients expect
3. **OpenAPI documentation** — FastAPI auto-generates Swagger UI (`/docs`) from the Pydantic schemas

The `model_config` on `AskResponse` includes example responses that appear in the Swagger UI, making the API self-documenting.

### Lifespan Handler

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    get_assistant()  # Pre-initialize on startup
    yield
```

This ensures the `DocAssistant` singleton (and therefore the Orchestration Service connection) is initialized when the server starts, not on the first request. First-request initialization would add several seconds of latency for the first user.

---

## 12. Mock Mode & Graceful Degradation

### How Mock Mode Activates

```python
try:
    from gen_ai_hub.orchestration_v2.service import OrchestrationService
    # ... all V2 SDK imports ...
    GENAI_HUB_AVAILABLE = True
except ImportError:
    GENAI_HUB_AVAILABLE = False
```

If the GenAI Hub SDK is not installed (or any single import fails), the entire block falls to the `except` branch and `GENAI_HUB_AVAILABLE` is set to `False`. This is an **all-or-nothing** pattern — if even one import fails, the entire SDK is considered unavailable.

When `GENAI_HUB_AVAILABLE` is `False`, `DocAssistant.__init__()` sets `self._service = None`, and all `ask()` calls route to `_mock_ask()`.

### Mock Response Logic

The mock assistant uses keyword matching to simulate the LLM:

1. **Non-SAP questions** — Checks for keywords like "password", "weather", "email setup". Returns `is_sap_ai: false`.
2. **Service-matched questions** — Checks against per-service keyword lists (e.g., "hana vector", "embedding" → `hana_cloud_vector`). Then runs the **real** `search_knowledge_base()` to get actual KB entries, so the links in mock responses are genuine.
3. **Generic SAP questions** — Matches broad terms like "sap", "btp", "cloud foundry" but can't determine a specific service.

Mock responses are prefixed with `[MOCK]` so UIs can detect them.

### Layered Error Handling

The `ask()` method has three catch levels:

```python
try:
    return self._run_with_tools(question, include_pipeline)
except OrchestrationError:      # Content filtering blocked → specific response with pipeline
except json.JSONDecodeError:     # LLM returned invalid JSON → fallback response
except Exception:                # Anything else → generic fallback
```

This ensures the API **never returns a 500 error** for LLM-related issues. Even if the LLM returns garbage or the orchestration service is down, the user gets a structured response.

---

## 13. Testing Strategy

### Test Structure (`test_local.py`)

11 tests organized by concern:

| Test | What It Validates |
|------|-------------------|
| `test_kb_loading` | JSON loads, 6 services present, each has >= 8 docs |
| `test_id_uniqueness` | All 60 doc IDs are unique |
| `test_search` | 7 queries across all services + nonsense query |
| `test_doc_lookup` | `get_docs_by_ids()` with valid and invalid IDs |
| `test_services_summary` | System prompt service summary generation |
| `test_kb_management` | Full CRUD lifecycle (add → update → delete) |
| `test_available_services` | Service listing with metadata |
| `test_get_all_entries` | All entries listing + service filter |
| `test_mock_assistant` | 9 questions testing classification accuracy |
| `test_pipeline_visibility` | Pipeline fields present in mock mode |
| `test_empty_query` | Empty/whitespace query handling |

### State Isolation Pattern

KB mutation tests save and restore state:

```python
def test_kb_management():
    kb_original = copy.deepcopy(load_knowledge_base())  # Snapshot
    try:
        add_entry(...)    # Mutate
        update_entry(...)
        delete_entry(...)
    finally:
        save_knowledge_base(kb_original)  # Always restore
        _invalidate_cache()               # Force reload
```

The `finally` block ensures the KB file is restored even if assertions fail. `_invalidate_cache()` is essential — without it, the in-memory cache would still hold the modified data.

### Dual Execution

Tests work both as pytest and as a standalone script:

```bash
pytest test_local.py -v        # pytest discovery
python test_local.py           # Direct execution (uses __main__ block)
```

---

## 14. Key Design Decisions & Trade-offs

### 1. Tool Calling vs. Direct RAG

**Decision:** Use LLM tool calling (two round-trips) instead of direct vector-based RAG.

**Trade-off:** Adds ~3-5 seconds of latency (two LLM calls instead of one) but gives the LLM control over search query formulation. For a 60-entry KB, this is more flexible than setting up a vector store.

### 2. JSON File Storage vs. Database

**Decision:** Store the KB in a plain JSON file, not a database.

**Trade-off:** No concurrent write safety (fine for single-process), no indexing (fine for 60 entries), but zero infrastructure dependencies. The KB loads into memory in milliseconds. If you needed multi-user write access or thousands of entries, you'd switch to SQLite or PostgreSQL.

### 3. Keyword Scoring vs. Vector Similarity

**Decision:** Use weighted keyword matching for search, not embeddings.

**Trade-off:** Keyword search can miss semantically related terms (e.g., "deploy" won't match "serve" unless both are tagged). But with curated tags covering the vocabulary, this works well for a domain-specific KB. It's also completely transparent — you can explain exactly why a result ranked high.

### 4. Singleton Assistant Pattern

**Decision:** `get_assistant()` returns a module-level singleton.

**Trade-off:** The Orchestration Service connection is established once on startup. This saves ~1-2 seconds per request but means you can't change the LLM configuration without restarting the server. For a single-config production deployment, this is the right call.

### 5. String Return Type for Search Tool

**Decision:** `search_knowledge_base()` returns `json.dumps(results)` (string), not `list[dict]`.

**Trade-off:** Less Pythonic, but the function is designed to be called as an LLM tool, and the tool calling protocol requires string results. The `ToolChatMessage(content=str(tool_result))` in the agentic loop would stringify it anyway.

### 6. All-or-Nothing SDK Import

**Decision:** If any V2 SDK import fails, the entire SDK is treated as unavailable.

**Trade-off:** A single missing class (like `ToolChatMessage`) would silently disable real mode and fall back to mock. This happened during the V1 → V2 migration (V1 didn't have `ToolMessage`). The all-or-nothing approach is safer than partial imports that might produce confusing runtime errors.

### 7. HTTP 200 for Content Filter Blocks

**Decision:** Content-filtered responses return HTTP 200, not 4xx.

**Trade-off:** UI developers need to check `is_sap_ai: false` and `confidence: 0.0` to detect blocks, rather than just checking the HTTP status. But this keeps the response schema consistent — every request returns the same structure. 4xx errors are reserved for truly malformed requests (validation failures, missing fields).

### 8. doc_ids Validation After LLM Response

**Decision:** After the LLM returns `doc_ids`, the code validates them against the actual KB before returning links.

```python
valid_ids = get_all_doc_ids()
validated_ids = [did for did in doc_ids if did in valid_ids]
```

**Trade-off:** Adds a small amount of code, but prevents the LLM from hallucinating document IDs. If the LLM returns `"aicore_magic_99"` (which doesn't exist), it's silently dropped. The user only sees links to real documents.

---

## 15. Deployment

### Cloud Foundry Configuration

The app deploys to SAP BTP Cloud Foundry with an AI Core service binding:

- **App name:** `sap-ai-doc-assistant`
- **Region:** AP10 (Australia)
- **Service binding:** `default_aicore` — provides `AICORE_*` environment variables that the GenAI Hub SDK reads automatically
- **Health check:** The CF health check hits `/health` to verify the app is running
- **Build:** Python buildpack, `requirements.txt` for dependencies

### Environment Variables

The SDK automatically reads:
- `AICORE_SERVICE_KEY` or `VCAP_SERVICES` (CF service binding) — contains the AI Core service credentials
- When running locally, `load_dotenv()` reads from a `.env` file (not committed to git)

### Startup Sequence

1. Uvicorn starts the FastAPI app
2. The `lifespan` handler calls `get_assistant()`
3. `DocAssistant.__init__()` imports the SDK, creates the config, initializes `OrchestrationService()`
4. If any step fails, mock mode is activated silently
5. The app starts accepting requests

---

*Report generated for the SAP AI Documentation Assistant v2.0.0 codebase.*
