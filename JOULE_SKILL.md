# Joule Skill Configuration: tm-help

This document contains the complete Joule Skill configuration for the TM Intent Classifier, enabling natural language talent management queries through SAP Joule.

## Architecture Overview

```
User → Joule → tm-help Skill → TM Intent Classifier Action → Destination → API
  ↑                                                                         |
  └────────────────────── Formatted Response ←─────────────────────────────┘
```

---

## Skill Definition

| Property | Value |
|----------|-------|
| **Skill Name** | `tm-help` |
| **Display Name** | Talent Management Help |
| **Description** | Helps users find SAP SuccessFactors Talent Management resources |
| **Category** | HR / Human Resources |
| **Linked Action** | TM Intent Classifier (SAP Build) |

---

## Slots

| Slot Name | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | String | No | The user's talent management question |

**Note**: The `query` slot is optional because we support menu-style triggers that don't include a query.

---

## Trigger Phrases

### Category A: Query Triggers (with `{query}` slot)

These phrases extract the user's question into the `query` slot:

```
- "Help me with {query}"
- "I need help with {query}"
- "How do I {query}"
- "Find resources for {query}"
- "What's the process for {query}"
- "Can you help with {query}"
- "I have a question about {query}"
```

**Examples**:
- "Help me with performance reviews" → `query = "performance reviews"`
- "How do I request time off" → `query = "request time off"`
- "Find resources for onboarding new hires" → `query = "onboarding new hires"`

### Category B: Menu Triggers (no slot)

These phrases show the topic menu without calling the API:

```
- "Talent management help"
- "What HR topics can you help with"
- "Show me talent management options"
- "What can you help me with for HR"
- "SuccessFactors help"
```

### Category C: Demo Mode Triggers

These phrases call the API with `show_pipeline=true`:

```
- "Show me how TM classification works"
- "Demo talent management"
- "How does the TM classifier work"
```

---

## Action Mapping

### Action Details

| Property | Value |
|----------|-------|
| **Action Name** | TM Intent Classifier |
| **Action Method** | classifyQuery |
| **Source** | SAP Build Action Repository |

### Input Mapping

| Skill Element | Action Parameter | Condition |
|---------------|------------------|-----------|
| `query` slot | `query` | When query is provided |
| `false` (literal) | `show_pipeline` | Normal mode |
| `true` (literal) | `show_pipeline` | Demo mode triggers |

### Output Fields (from API Response)

| Field | Type | Description |
|-------|------|-------------|
| `is_talent_management` | boolean | Whether query relates to TM |
| `confidence` | float | Classification confidence (0.0-1.0) |
| `topic` | string | Topic key (e.g., "performance_management") |
| `topic_display_name` | string | Display name (e.g., "Performance Management") |
| `links` | array | Array of help resource links |
| `summary` | string | LLM-generated summary message |
| `pipeline` | object | Pipeline details (when show_pipeline=true) |

---

## Response Templates

### Template 1: TM Query Match

**Condition**: `query` provided AND `is_talent_management = true`

```
I found resources for {{topic_display_name}}:

{{summary}}

Here are some helpful links:
{{#each links}}
• {{this.title}} - {{this.url}}
{{/each}}
```

**Example Output**:
```
I found resources for Performance Management:

Your question is about performance reviews. I can help you with setting up
review cycles, managing goals, and tracking employee feedback.

Here are some helpful links:
• Performance & Goals Administration - https://help.sap.com/docs/SAP_SUCCESSFACTORS_PERFORMANCE_GOALS
• Setting Up Goal Plans - https://help.sap.com/docs/SAP_SUCCESSFACTORS_PERFORMANCE_GOALS/f79bd61a0c9c42f5b7ee88e3ad0c8424/a2b83ea8f3a04b8a93a8e61ce8c7eb79.html
```

### Template 2: Non-TM Query

**Condition**: `query` provided AND `is_talent_management = false`

```
{{summary}}

I can help with these Talent Management topics - just ask!
• Performance Management
• Learning & Development
• Recruitment
• Compensation & Benefits
• Succession Planning
• Employee Onboarding
• Time & Attendance
• Employee Central
```

**Example Output**:
```
Your question about resetting your password isn't related to Talent Management.
For IT support issues, please contact your system administrator.

I can help with these Talent Management topics - just ask!
• Performance Management
• Learning & Development
• Recruitment
• Compensation & Benefits
• Succession Planning
• Employee Onboarding
• Time & Attendance
• Employee Central
```

### Template 3: Topic Menu (No Query)

**Condition**: No `query` slot value (menu trigger used)

```
I can help you with these SAP SuccessFactors topics:

📊 Performance Management - Reviews, goals, feedback
📚 Learning & Development - Training, courses, certifications
👥 Recruitment - Job postings, candidates, interviews
💰 Compensation & Benefits - Salary, bonuses, benefits
🎯 Succession Planning - Career paths, talent pools
🚀 Employee Onboarding - New hire setup, orientation
⏰ Time & Attendance - Leave, time off, timesheets
🏢 Employee Central - Employee data, org charts

What would you like help with?
```

### Template 4: Demo Mode (Pipeline Visible)

**Condition**: Demo mode trigger used (calls API with `show_pipeline=true`)

```
Here's how the TM classification pipeline works:

📥 Your query: "{{query}}"

🔒 Content Filtering:
   • Input: {{#if pipeline.content_filtering.input.passed}}✅ Passed{{else}}❌ Blocked{{/if}}
   • Output: {{#if pipeline.content_filtering.output.passed}}✅ Passed{{else}}❌ Blocked{{/if}}

🤖 LLM Processing:
   • Model: {{pipeline.llm.model}}
   • Prompt tokens: {{pipeline.llm.prompt_tokens}}
   • Completion tokens: {{pipeline.llm.completion_tokens}}

📊 Result:
   • Topic: {{topic_display_name}}
   • Confidence: {{confidence}}
   • Is TM: {{is_talent_management}}
```

---

## Conversation Flow Examples

### Flow 1: Direct Query
```
User: "How do I submit my performance review?"
Joule: [Calls API with query="submit my performance review"]
       → Returns Performance Management links with summary
```

### Flow 2: Topic Browse Then Query
```
User: "Talent management help"
Joule: [Shows topic menu - no API call]

User: "Tell me about time off requests"
Joule: [Calls API with query="time off requests"]
       → Returns Time & Attendance links with summary
```

### Flow 3: Non-TM Query
```
User: "Help me with resetting my SAP password"
Joule: [Calls API with query="resetting my SAP password"]
       → Returns non-TM response with topic suggestions
```

### Flow 4: Demo Mode
```
User: "Show me how TM classification works"
Joule: [Calls API with query="example query", show_pipeline=true]
       → Returns pipeline visibility details
```

---

## Test Cases

### Functional Tests

| # | User Input | Expected Behavior |
|---|------------|-------------------|
| 1 | "Help me with performance reviews" | Returns Performance Management links |
| 2 | "How do I request time off" | Returns Time & Attendance links |
| 3 | "Find resources for hiring candidates" | Returns Recruitment links |
| 4 | "What's the process for new employee onboarding" | Returns Onboarding links |
| 5 | "Help me with compensation planning" | Returns Compensation & Benefits links |
| 6 | "How do I view the org chart" | Returns Employee Central links |
| 7 | "Find resources for succession planning" | Returns Succession Planning links |
| 8 | "I need help with training courses" | Returns Learning & Development links |

### Edge Cases

| # | User Input | Expected Behavior |
|---|------------|-------------------|
| 9 | "Talent management help" | Shows topic menu (no API call) |
| 10 | "What HR topics can you help with" | Shows topic menu |
| 11 | "Help me reset my password" | Returns non-TM fallback with topic suggestions |
| 12 | "How do I fix my laptop" | Returns non-TM fallback |
| 13 | "Demo talent management" | Shows pipeline details |
| 14 | "Show me how TM classification works" | Shows pipeline details |

### Slot Extraction Tests

| # | User Input | Extracted `query` |
|---|------------|-------------------|
| 15 | "Help me with annual reviews" | "annual reviews" |
| 16 | "How do I create a job posting" | "create a job posting" |
| 17 | "I need help with employee data" | "employee data" |

---

## Implementation Checklist

### Joule Studio Configuration

- [ ] Create skill with name `tm-help`
- [ ] Add description: "Helps users find SAP SuccessFactors Talent Management resources"
- [ ] Define `query` slot (String, optional)
- [ ] Add all Category A trigger phrases with slot binding
- [ ] Add all Category B trigger phrases (menu triggers)
- [ ] Add all Category C trigger phrases (demo triggers)
- [ ] Link to TM Intent Classifier action
- [ ] Configure input mapping (query → query, show_pipeline conditional)
- [ ] Set up response template conditions
- [ ] Configure response templates for all 4 scenarios

### Testing

- [ ] Test each of the 8 TM topics
- [ ] Test menu triggers show topic list
- [ ] Test non-TM queries return fallback
- [ ] Test demo mode shows pipeline
- [ ] Test slot extraction accuracy
- [ ] Verify links are clickable in Joule UI

### Deployment

- [ ] Review skill configuration
- [ ] Publish to Joule
- [ ] End-to-end test in production Joule

---

## Related Files

| File | Purpose |
|------|---------|
| `app.py` | FastAPI endpoint implementation |
| `models.py` | Pydantic request/response schemas |
| `topic_links.py` | Topic definitions and help links |
| `intent_classifier.py` | LLM classification logic |
| `CF_COMMANDS.md` | Cloud Foundry deployment commands |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-01 | Initial skill design and documentation |
