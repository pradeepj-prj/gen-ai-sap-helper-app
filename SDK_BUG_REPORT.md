# SDK Bug Report: OrchestrationError.intermediate_results is a raw dict, not ModuleResults as type-hinted

**Package:** `sap-ai-sdk-gen` (v6.1.2)
**Repository:** https://github.com/SAP/ai-sdk-python
**Module:** `gen_ai_hub.orchestration_v2`

## Summary

`OrchestrationError.intermediate_results` is type-hinted as `ModuleResults` but receives a raw `dict` at runtime, making it impossible to access content filter scores using the typed API.

## Details

The `OrchestrationError` constructor declares `intermediate_results` as type `ModuleResults`:

```python
# gen_ai_hub/orchestration_v2/exceptions.py (line 24)
def __init__(self, ..., intermediate_results: ModuleResults, ...):
    self.intermediate_results = intermediate_results
```

However, both call sites that raise this error pass a raw dict from the JSON response:

```python
# gen_ai_hub/orchestration_v2/sse_client.py (line 287, _handle_http_error)
intermediate_results=error_content.get("intermediate_results", {})

# gen_ai_hub/orchestration_v2/sse_client.py (line 45, _parse_event_data)
intermediate_results=error_event.get("intermediate_results", {})
```

Since `OrchestrationError` extends `Exception` (not `BaseModel`), there is no Pydantic validation to convert the dict into a `ModuleResults` object. The raw dict is stored as-is.

## Impact

Any code that trusts the type hint and uses attribute access crashes:

```python
try:
    result = service.run(config=config, ...)
except OrchestrationError as e:
    mr = e.intermediate_results          # raw dict, not ModuleResults
    if mr.input_filtering:               # AttributeError: 'dict' has no attribute 'input_filtering'
        scores = mr.input_filtering.data  # never reached
```

This makes it impossible to extract Azure Content Safety scores from blocked requests without working around the SDK. In our case, this caused the API to return HTTP 500 instead of the filtering scores — the `AttributeError` escaped the `OrchestrationError` handler and hit the application's catch-all error handler.

## Suggested Fix

Convert the dict to `ModuleResults` in the `OrchestrationError` constructor:

```python
# In OrchestrationError.__init__:
self.intermediate_results = (
    ModuleResults(**intermediate_results)
    if isinstance(intermediate_results, dict)
    else intermediate_results
)
```

Alternatively, update the type hint to `dict | ModuleResults` to reflect the actual runtime behavior.

## Workaround

Use dict access instead of attribute access on `intermediate_results`:

```python
except OrchestrationError as e:
    mr = getattr(e, "intermediate_results", None) or {}
    input_filtering = mr.get("input_filtering")  # dict access, not attribute
    if input_filtering:
        scores = input_filtering.get("data", {}).get("azure_content_safety", {})
```

## Environment

- `sap-ai-sdk-gen` version: 6.1.2
- Python: 3.10
- Affected files in SDK:
  - `gen_ai_hub/orchestration_v2/exceptions.py` (type hint)
  - `gen_ai_hub/orchestration_v2/sse_client.py` (both raise sites)
