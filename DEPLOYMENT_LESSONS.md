# Cloud Foundry Deployment — Lessons Learned

## Deployment Details
- **App URL:** https://sap-ai-doc-assistant.cfapps.ap10.hana.ondemand.com
- **Region:** AP10 (Australia)
- **Org:** SEAIO_dial-3-0-zme762l7
- **Space:** dev
- **Buildpack:** python_buildpack 1.8.38
- **Python:** 3.11.x
- **SDK:** sap-ai-sdk-gen 6.1.2

---

## Issue 1: Wrong SDK Package Name (CRITICAL — silent failure)

**Symptom:** App starts fine, health check passes, but all responses are keyword-matched mock responses instead of real LLM answers.

**Root Cause:** `requirements.txt` listed `generative-ai-hub-sdk>=1.0.0` (the deprecated V1 package). The app imports from `gen_ai_hub.orchestration_v2.*`, which only exists in the V2 package `sap-ai-sdk-gen`. With V1 installed, the V2 imports fail silently — caught by the `try/except ImportError` block in `doc_assistant.py` — setting `GENAI_HUB_AVAILABLE = False` and falling to mock mode.

**Fix:** Change `generative-ai-hub-sdk>=1.0.0` → `sap-ai-sdk-gen>=6.1.2` in `requirements.txt`.

**Lesson:** The try/except import pattern is a double-edged sword. It enables graceful local dev without the SDK, but also silently hides package mismatch issues in production. Always check startup logs for the `"GenAI Hub Orchestration service initialized successfully"` message after deployment.

---

## Issue 2: Disk Quota Exceeded (512M not enough)

**Symptom:** `cf push` stages successfully (pip install works), but the app crashes immediately on startup with `No space left on device` errors during droplet extraction.

**Root Cause:** The V2 SDK (`sap-ai-sdk-gen`) has a massive transitive dependency tree: langchain, langgraph, numpy, sqlalchemy, tiktoken, openai, aiohttp, and many more. The compiled droplet (Python runtime + all packages) exceeds 512M.

**Fix:** Bump `disk_quota` from `512M` to `1G` in `manifest.yml`.

**Lesson:** CF `disk_quota` is the filesystem size for the container (code + dependencies + temp files), separate from `memory` (RAM). The staging container has ample space, so pip install succeeds — but when the droplet is copied to the smaller runtime container, it fails. Always check the dependency tree size when using SDKs with heavy transitive deps like langchain.

---

## Issue 3: Missing `AICORE_RESOURCE_GROUP` Env Var

**Symptom:** SDK imports succeed (`GENAI_HUB_AVAILABLE = True`), but `OrchestrationService()` initialization throws: `Failed to get /deployments: Invalid Request, Missing header parameter 'AI-Resource-Group'`.

**Root Cause:** The CF service binding (`default_aicore`) injects credentials into `VCAP_SERVICES` (client ID, secret, auth URL, service URLs), but the resource group is an application-level concept — it's not part of the service key. The SDK auto-reads auth from `VCAP_SERVICES` but needs `AICORE_RESOURCE_GROUP` set as a separate environment variable.

**Fix:** Add `AICORE_RESOURCE_GROUP: default` under `env:` in `manifest.yml`.

**Lesson:** `VCAP_SERVICES` provides service credentials, not application configuration. Resource groups, which determine where orchestration deployments live, must be explicitly configured. The `"default"` resource group is the standard one created during AI Core onboarding.

---

## Issue 4: Memory Allocation

**Context:** Original setting was `memory: 256M`. Bumped to `512M` preemptively.

**Rationale:** Python has ~50-80MB baseline. FastAPI's ASGI server, Pydantic model compilation, and the GenAI Hub SDK's HTTP client + auth modules add significant overhead. 256M would likely OOM during first request processing. 512M provides safe headroom.

---

## Final Working `manifest.yml`

```yaml
---
applications:
  - name: sap-ai-doc-assistant
    memory: 512M
    disk_quota: 1G
    instances: 1
    buildpacks:
      - python_buildpack
    command: uvicorn app:app --host 0.0.0.0 --port $PORT
    health-check-type: http
    health-check-http-endpoint: /health
    timeout: 120
    env:
      PYTHON_VERSION: 3.11.x
      AICORE_RESOURCE_GROUP: default
    services:
      - default_aicore
```

## Known Limitation: Ephemeral Filesystem

KB management endpoints (POST/PUT/DELETE) write to `knowledge_base.json` on disk. On CF's ephemeral filesystem, these writes work but are lost on app restart or restage. Acceptable for a demo where the KB is managed via git. For runtime persistence, a database backend would be needed.

## Verification Checklist

After every `cf push`:

1. `cf logs sap-ai-doc-assistant --recent` — look for:
   - `"GenAI Hub Orchestration service initialized successfully"` (real SDK, not mock)
   - No `"Failed to initialize"` warnings
2. `curl <app-url>/health` — should return `{"status": "healthy"}`
3. `POST /api/v1/ask` with `show_pipeline: true` — confirm real LLM response with pipeline details (content filtering scores, tool calls, etc.)
