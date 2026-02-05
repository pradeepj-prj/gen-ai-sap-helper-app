# Talent Management Intent Classifier API

A FastAPI service that classifies user queries related to SAP SuccessFactors Talent Management and returns relevant help portal links. Designed for integration with SAP Joule.

## Features

- Classifies queries into 8 Talent Management topics
- Returns relevant SAP Help Portal documentation links
- Uses GPT-4 via SAP GenAI Hub Orchestration Service
- **Content Filtering**: Azure Content Safety checks for harmful content
- **Data Masking**: Automatic PII anonymization before LLM processing
- **Pipeline Visibility**: Optional detailed view of orchestration steps (for demos)
- Auto-generated OpenAPI spec for Joule Action import
- Mock classification fallback for local development

## How Classification Works

The classifier uses SAP GenAI Hub's Orchestration Service to process queries through a secure pipeline:

1. **Data Masking**: PII (names, emails, phone numbers, addresses) is automatically anonymized using SAP Data Privacy Integration before the query reaches the LLM
2. **Input Content Filtering**: Azure Content Safety scans the query for harmful content (hate speech, violence, self-harm, sexual content)
3. **LLM Classification**: GPT-4 analyzes the (masked) query against the 8 supported topics and returns a structured JSON response with topic classification and confidence score
4. **Output Content Filtering**: The LLM response is scanned for harmful content before being returned

If content filtering blocks a query, the API returns a safe response indicating the content was filtered.

## Supported Topics

| Topic | Example Queries |
|-------|-----------------|
| Performance Management | performance review, goals, feedback |
| Learning & Development | training, courses, certifications |
| Recruitment | job posting, candidates, interviews |
| Compensation & Benefits | salary, bonus, benefits |
| Succession Planning | career path, talent pool, successors |
| Employee Onboarding | new hire, onboarding checklist |
| Time & Attendance | time off, leave request, vacation |
| Employee Central | employee data, org chart, profile |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (uses mock classification)
uvicorn app:app --reload

# Run tests
python test_local.py
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/classify` | Classify a user query |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger UI |
| GET | `/openapi.json` | OpenAPI spec |

## Example Request

```bash
curl -X POST http://localhost:8000/api/v1/classify \
  -H "Content-Type: application/json" \
  -d '{"query": "How do I submit my performance review?"}'
```

## Example Response

```json
{
  "is_talent_management": true,
  "confidence": 0.95,
  "topic": "performance_management",
  "topic_display_name": "Performance Management",
  "links": [
    {
      "title": "Performance & Goals Administration",
      "url": "https://help.sap.com/docs/SAP_SUCCESSFACTORS_PERFORMANCE_GOALS",
      "description": "Complete guide to Performance Management in SuccessFactors"
    }
  ],
  "summary": "Your question is about Performance Management. Here are helpful resources."
}
```

## Pipeline Visibility (Demo Feature)

For demos and debugging, you can request detailed pipeline information by setting `show_pipeline: true`:

```bash
curl -X POST http://localhost:8000/api/v1/classify \
  -H "Content-Type: application/json" \
  -d '{"query": "John Smith at john@example.com needs vacation time", "show_pipeline": true}'
```

This returns additional details about each orchestration step:

```json
{
  "is_talent_management": true,
  "confidence": 0.95,
  "topic": "time_attendance",
  "pipeline": {
    "data_masking": {
      "original_query": "John Smith at john@example.com needs vacation time",
      "masked_query": "MASKED_PERSON at MASKED_EMAIL needs vacation time",
      "entities_masked": ["PERSON", "EMAIL"]
    },
    "content_filtering": {
      "input": {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": true},
      "output": {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 0, "passed": true}
    },
    "llm": {
      "model": "gpt-4o-2024-08-06",
      "prompt_tokens": 356,
      "completion_tokens": 68
    },
    "messages_to_llm": [
      {"role": "system", "content": "You are an expert at classifying HR queries..."},
      {"role": "user", "content": "Classify this query: MASKED_PERSON at MASKED_EMAIL needs vacation time"}
    ]
  }
}
```

When content is blocked by safety filters, the pipeline shows which category triggered the block:

```json
{
  "is_talent_management": false,
  "summary": "Your query was blocked by content filtering. Please rephrase your question.",
  "pipeline": {
    "content_filtering": {
      "input": {"hate": 0, "self_harm": 0, "sexual": 0, "violence": 4, "passed": false}
    },
    "llm": {"model": "blocked", "prompt_tokens": 0, "completion_tokens": 0}
  }
}
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

## Joule Integration

1. Deploy the app to Cloud Foundry
2. Create a BTP Destination pointing to the app URL
3. Import `/openapi.json` as an Action in SAP Build Process Automation
4. Create a Joule Skill that calls the classification action
