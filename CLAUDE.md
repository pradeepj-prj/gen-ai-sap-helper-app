# Joule Talent Management Intent Classification API

## Project Overview
A FastAPI application that classifies user queries related to SAP SuccessFactors Talent Management topics and returns relevant help portal links.

## Architecture
- **Framework:** FastAPI with Pydantic models
- **LLM:** GPT-4 via SAP GenAI Hub SDK
- **Deployment:** Cloud Foundry with AI Core service binding
- **Integration:** Joule Studio via BTP Destination Service

## Key Files
- `app.py` - FastAPI application with `/api/v1/classify` endpoint
- `intent_classifier.py` - GenAI Hub SDK integration for LLM classification
- `topic_links.py` - 8 TM topics mapped to SAP Help Portal URLs
- `models.py` - Pydantic request/response schemas
- `JOULE_SKILL.md` - Joule Skill configuration and trigger phrases

## Running Locally
```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables (see .env.example)
export AICORE_AUTH_URL=...
export AICORE_CLIENT_ID=...
export AICORE_CLIENT_SECRET=...
export AICORE_RESOURCE_GROUP=...
export AICORE_BASE_URL=...

# Run the app
uvicorn app:app --reload
```

## API Endpoints
- `POST /api/v1/classify` - Classify a user query
- `GET /health` - Health check
- `GET /docs` - Swagger UI
- `GET /openapi.json` - OpenAPI spec for Joule Action import

## Topics Supported
1. Performance Management
2. Learning & Development
3. Recruitment
4. Compensation & Benefits
5. Succession Planning
6. Employee Onboarding
7. Time & Attendance
8. Employee Central

## Features
- **Dynamic Summaries** - LLM generates query-specific, natural language summaries
- **Pipeline Visibility** - Add `?pipeline=true` to see orchestration details
- **Content Filtering** - Azure Content Safety filters harmful content
- **Data Masking** - PII anonymization via SAP Data Privacy Integration

## Cloud Foundry Deployment
- **App name:** tm-intent-classifier
- **Region:** AP10 (Australia)
- **API endpoint:** https://api.cf.ap10.hana.ondemand.com
- **Service binding:** default_aicore (AI Core)
- **Health check:** /health

See `CF_COMMANDS.md` for deployment commands.

## Joule Integration

### Integration Stack
```
User → Joule → tm-help Skill → SAP Build Action → BTP Destination → API
```

### Components
| Component | Status | Details |
|-----------|--------|---------|
| API | Deployed | Cloud Foundry (tm-intent-classifier) |
| BTP Destination | Created | Points to CF app URL |
| SAP Build Action | Published | Uses OpenAPI spec from `/openapi.json` |
| Joule Skill | Configured | See `JOULE_SKILL.md` |

### Joule Skill: `tm-help`
- **Trigger phrases**: "Help me with {query}", "How do I {query}", etc.
- **Menu trigger**: "Talent management help" (shows 8 topics)
- **Demo mode**: "Show me how TM classification works" (exposes pipeline)

See `JOULE_SKILL.md` for complete skill configuration, response templates, and test cases.
