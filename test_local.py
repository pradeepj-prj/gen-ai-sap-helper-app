#!/usr/bin/env python3
"""
Local test script for the SAP AI Documentation Assistant.

Run this to validate the knowledge base, search function, KB management,
and mock assistant logic before deploying with the full GenAI Hub integration.
"""

import json
import copy
import sys

sys.path.insert(0, ".")

from knowledge_base import (
    load_knowledge_base,
    search_knowledge_base,
    get_docs_by_ids,
    get_all_doc_ids,
    get_services_summary,
    get_all_entries,
    get_available_services,
    add_entry,
    update_entry,
    delete_entry,
    save_knowledge_base,
    _invalidate_cache,
)


def test_kb_loading():
    """Test that the knowledge base loads correctly from JSON."""
    print("=== Testing KB Loading ===\n")

    _invalidate_cache()
    kb = load_knowledge_base()

    assert "services" in kb, "KB should have 'services' key"
    assert len(kb["services"]) == 6, f"Expected 6 services, got {len(kb['services'])}"
    print(f"  ✓ Loaded {len(kb['services'])} services")

    expected_services = [
        "ai_core", "genai_hub", "ai_launchpad",
        "joule", "hana_cloud_vector", "document_processing",
    ]
    for svc in expected_services:
        assert svc in kb["services"], f"Missing service: {svc}"
        svc_data = kb["services"][svc]
        assert "display_name" in svc_data, f"Missing display_name for {svc}"
        assert "description" in svc_data, f"Missing description for {svc}"
        assert "docs" in svc_data, f"Missing docs for {svc}"
        assert len(svc_data["docs"]) >= 8, f"Expected >=8 docs for {svc}, got {len(svc_data['docs'])}"
        print(f"  ✓ {svc}: {svc_data['display_name']} ({len(svc_data['docs'])} docs)")

    print("\n✓ KB loading passed\n")


def test_id_uniqueness():
    """Test that all document IDs are unique across all services."""
    print("=== Testing ID Uniqueness ===\n")

    all_ids = get_all_doc_ids()
    kb = load_knowledge_base()

    total_docs = sum(len(svc["docs"]) for svc in kb["services"].values())
    assert len(all_ids) == total_docs, f"ID count ({len(all_ids)}) != doc count ({total_docs})"
    print(f"  ✓ All {len(all_ids)} document IDs are unique")

    print("\n✓ ID uniqueness passed\n")


def test_search():
    """Test the search_knowledge_base function with various queries."""
    print("=== Testing KB Search ===\n")

    # Test 1: Search for AI Core setup
    results = json.loads(search_knowledge_base("ai core setup deployment"))
    assert len(results) > 0, "Should find results for 'ai core setup deployment'"
    assert any(r["service"] == "ai_core" for r in results), "Should find ai_core results"
    print(f"  ✓ 'ai core setup deployment' → {len(results)} results (top: {results[0]['title']})")

    # Test 2: Search with service filter
    results = json.loads(search_knowledge_base("overview", service="genai_hub"))
    assert len(results) > 0, "Should find results for 'overview' in genai_hub"
    assert all(r["service"] == "genai_hub" for r in results), "All results should be genai_hub"
    print(f"  ✓ 'overview' (genai_hub only) → {len(results)} results")

    # Test 3: Search for vector/embeddings
    results = json.loads(search_knowledge_base("vector embeddings similarity search"))
    assert len(results) > 0, "Should find results for vector search"
    assert any(r["service"] == "hana_cloud_vector" for r in results), "Should find HANA vector results"
    print(f"  ✓ 'vector embeddings similarity search' → {len(results)} results")

    # Test 4: Search for RAG/grounding
    results = json.loads(search_knowledge_base("RAG retrieval augmented generation grounding"))
    assert len(results) > 0, "Should find results for RAG"
    print(f"  ✓ 'RAG retrieval augmented generation' → {len(results)} results")

    # Test 5: Search for Joule skills
    results = json.loads(search_knowledge_base("joule skill creation"))
    assert len(results) > 0, "Should find Joule results"
    assert any(r["service"] == "joule" for r in results), "Should find joule results"
    print(f"  ✓ 'joule skill creation' → {len(results)} results")

    # Test 6: Search for document extraction
    results = json.loads(search_knowledge_base("invoice extraction schema"))
    assert len(results) > 0, "Should find DOX results"
    assert any(r["service"] == "document_processing" for r in results)
    print(f"  ✓ 'invoice extraction schema' → {len(results)} results")

    # Test 7: Nonsense query should return few/no results
    results = json.loads(search_knowledge_base("xyzzy foobar blargh"))
    print(f"  ✓ Nonsense query → {len(results)} results (expected few/none)")

    print("\n✓ KB search passed\n")


def test_doc_lookup():
    """Test looking up documents by their IDs."""
    print("=== Testing Doc Lookup ===\n")

    docs = get_docs_by_ids(["aicore_overview_01", "genai_sdk_03", "joule_studio_01"])
    assert len(docs) == 3, f"Expected 3 docs, got {len(docs)}"
    titles = [d["title"] for d in docs]
    assert "What Is SAP AI Core?" in titles
    assert "SAP Cloud SDK for AI (Python)" in titles
    print(f"  ✓ Looked up 3 docs by ID: {', '.join(titles)}")

    # Non-existent ID should be skipped
    docs = get_docs_by_ids(["aicore_overview_01", "nonexistent_999"])
    assert len(docs) == 1, "Should only return existing docs"
    print(f"  ✓ Non-existent ID correctly skipped")

    print("\n✓ Doc lookup passed\n")


def test_services_summary():
    """Test the services summary generation for the system prompt."""
    print("=== Testing Services Summary ===\n")

    summary = get_services_summary()
    assert len(summary) > 0, "Summary should not be empty"
    assert "ai_core" in summary
    assert "genai_hub" in summary
    assert "joule" in summary
    assert "hana_cloud_vector" in summary
    print("Generated services summary:\n")
    print(summary)

    print("\n✓ Services summary passed\n")


def test_kb_management():
    """Test KB CRUD operations (add, update, delete) without persisting to disk."""
    print("=== Testing KB Management ===\n")

    # Save original KB state for restoration
    kb_original = copy.deepcopy(load_knowledge_base())

    try:
        # Test add
        new_id = add_entry("ai_core", {
            "title": "Test Entry",
            "url": "https://example.com/test",
            "description": "A test documentation entry",
            "tags": ["test"],
        })
        assert new_id is not None, "add_entry should return an ID"
        assert new_id in get_all_doc_ids(), "New entry should be in all IDs"
        print(f"  ✓ Added entry: {new_id}")

        # Test add to nonexistent service
        result = add_entry("nonexistent_service", {
            "title": "Bad", "url": "x", "description": "x"
        })
        assert result is None, "Should return None for nonexistent service"
        print(f"  ✓ Add to nonexistent service correctly returns None")

        # Test update
        success = update_entry(new_id, {"title": "Updated Test Entry"})
        assert success, "update_entry should return True"
        docs = get_docs_by_ids([new_id])
        assert docs[0]["title"] == "Updated Test Entry", "Title should be updated"
        print(f"  ✓ Updated entry title to 'Updated Test Entry'")

        # Test update nonexistent
        success = update_entry("nonexistent_id", {"title": "X"})
        assert not success, "Should return False for nonexistent ID"
        print(f"  ✓ Update nonexistent entry correctly returns False")

        # Test delete
        success = delete_entry(new_id)
        assert success, "delete_entry should return True"
        assert new_id not in get_all_doc_ids(), "Deleted entry should be gone"
        print(f"  ✓ Deleted entry: {new_id}")

        # Test delete nonexistent
        success = delete_entry("nonexistent_id")
        assert not success, "Should return False for nonexistent ID"
        print(f"  ✓ Delete nonexistent entry correctly returns False")

    finally:
        # Restore original KB
        save_knowledge_base(kb_original)
        _invalidate_cache()

    print("\n✓ KB management passed\n")


def test_available_services():
    """Test the available services listing."""
    print("=== Testing Available Services ===\n")

    services = get_available_services()
    assert len(services) == 6, f"Expected 6 services, got {len(services)}"

    for svc in services:
        assert "key" in svc
        assert "display_name" in svc
        assert "description" in svc
        assert "doc_count" in svc
        assert svc["doc_count"] >= 8
        print(f"  ✓ {svc['key']}: {svc['display_name']} ({svc['doc_count']} docs)")

    print("\n✓ Available services passed\n")


def test_get_all_entries():
    """Test listing all entries with optional service filter."""
    print("=== Testing Get All Entries ===\n")

    all_entries = get_all_entries()
    assert len(all_entries) == 60, f"Expected 60 total entries, got {len(all_entries)}"
    print(f"  ✓ Total entries: {len(all_entries)}")

    ai_core_entries = get_all_entries(service_filter="ai_core")
    assert len(ai_core_entries) == 10, f"Expected 10 ai_core entries, got {len(ai_core_entries)}"
    assert all(e["service_key"] == "ai_core" for e in ai_core_entries)
    print(f"  ✓ ai_core entries: {len(ai_core_entries)}")

    print("\n✓ Get all entries passed\n")


def test_mock_assistant():
    """Test the mock documentation assistant with various questions."""
    print("=== Testing Mock Assistant ===\n")

    from doc_assistant import DocAssistant

    assistant = DocAssistant()

    # Test cases: (question, expected_is_sap_ai, expected_services_contain)
    test_cases = [
        ("How do I set up AI Core?", True, ["ai_core"]),
        ("What SDK should I use for orchestration?", True, ["genai_hub"]),
        ("How do I create a Joule skill?", True, ["joule"]),
        ("How does RAG work in SAP?", True, ["genai_hub"]),
        ("How do I store vector embeddings in HANA?", True, ["hana_cloud_vector"]),
        ("How do I extract data from invoices?", True, ["document_processing"]),
        ("How do I deploy a model?", True, ["ai_core"]),
        ("What's the weather today?", False, []),
        ("How do I reset my laptop password?", False, []),
    ]

    passed = 0
    failed = 0

    for question, expected_is_sap, expected_services in test_cases:
        result = assistant.ask(question)

        is_sap_match = result["is_sap_ai"] == expected_is_sap
        services_match = (
            not expected_services
            or all(s in result["services"] for s in expected_services)
        )

        if is_sap_match and services_match:
            svc_str = ", ".join(result["services"]) if result["services"] else "N/A"
            link_count = len(result["links"])
            print(f"  ✓ '{question[:45]}...'")
            print(f"    → services=[{svc_str}], links={link_count}, confidence={result['confidence']}")
            passed += 1
        else:
            print(f"  ✗ '{question[:45]}...'")
            print(f"    Expected: is_sap_ai={expected_is_sap}, services⊇{expected_services}")
            print(f"    Got:      is_sap_ai={result['is_sap_ai']}, services={result['services']}")
            failed += 1

    print(f"\n{'✓' if failed == 0 else '✗'} {passed}/{len(test_cases)} tests passed\n")
    return failed == 0


def test_pipeline_visibility():
    """Test that pipeline details include tool call information."""
    print("=== Testing Pipeline Visibility ===\n")

    from doc_assistant import DocAssistant

    assistant = DocAssistant()
    result = assistant.ask("How do I deploy models on AI Core?", include_pipeline=True)

    assert "pipeline" in result, "Pipeline should be in result when include_pipeline=True"
    pipeline = result["pipeline"]

    assert "content_filtering" in pipeline, "Pipeline should have content_filtering"
    assert "llm" in pipeline, "Pipeline should have llm details"
    assert "messages_to_llm" in pipeline, "Pipeline should have messages_to_llm"
    assert "tool_calls" in pipeline, "Pipeline should have tool_calls"

    print(f"  ✓ Pipeline has all expected fields")

    # Check tool call details
    tool_calls = pipeline["tool_calls"]
    assert tool_calls is not None, "Tool calls should not be None in mock mode"
    assert len(tool_calls) > 0, "Should have at least one tool call"

    tc = tool_calls[0]
    assert "tool_name" in tc, "Tool call should have tool_name"
    assert "arguments" in tc, "Tool call should have arguments"
    assert "result_count" in tc, "Tool call should have result_count"
    assert "results_preview" in tc, "Tool call should have results_preview"
    print(f"  ✓ Tool call: {tc['tool_name']}({tc['arguments']}) → {tc['result_count']} results")

    print("\n✓ Pipeline visibility passed\n")


def test_empty_query():
    """Test handling of empty/whitespace queries."""
    print("=== Testing Empty Query ===\n")

    from doc_assistant import DocAssistant

    assistant = DocAssistant()

    result = assistant.ask("")
    assert result["is_sap_ai"] is False
    assert "valid question" in result["answer"].lower()
    print(f"  ✓ Empty query handled correctly")

    result = assistant.ask("   ")
    assert result["is_sap_ai"] is False
    print(f"  ✓ Whitespace query handled correctly")

    print("\n✓ Empty query passed\n")


def test_content_filtered_pipeline():
    """Test that content-filtered requests return pipeline details instead of crashing."""
    print("=== Testing Content Filtered Pipeline ===\n")

    from doc_assistant import DocAssistant
    from models import LLMDetails

    assistant = DocAssistant()

    # Test 1: _content_filtered_response returns correct structure
    response = assistant._content_filtered_response("test question", "blocked by filter")
    assert response["is_sap_ai"] is False
    assert response["confidence"] == 0.0
    assert response["services"] == []
    assert response["links"] == []
    assert "blocked" in response["answer"].lower()
    print("  ✓ _content_filtered_response returns correct structure")

    # Test 2: _fallback_error_pipeline returns valid pipeline with blocked_by/reason
    error = Exception("Content was blocked by input filtering")
    pipeline = assistant._fallback_error_pipeline("inflammatory query", error)
    assert pipeline["data_masking"] is None
    assert pipeline["content_filtering"]["input"]["passed"] is False
    assert pipeline["content_filtering"]["output"]["passed"] is False
    assert pipeline["llm"]["model"] == "blocked"
    assert pipeline["llm"]["blocked_by"] == "unknown"
    assert "blocked by input filtering" in pipeline["llm"]["reason"]
    assert pipeline["messages_to_llm"][0]["content"] == "inflammatory query"
    assert pipeline["tool_calls"] is None
    print("  ✓ _fallback_error_pipeline returns valid pipeline with blocked_by/reason")

    # Test 3: _extract_pipeline_from_error handles None intermediate_results
    class FakeError(Exception):
        pass
    fake_err = FakeError("filter blocked")
    # No intermediate_results attribute — should not crash thanks to getattr fallback
    pipeline = assistant._extract_pipeline_from_error("test query", fake_err)
    assert pipeline["llm"]["model"] == "blocked"
    assert pipeline["content_filtering"]["input"]["passed"] is False
    print("  ✓ _extract_pipeline_from_error handles missing intermediate_results")

    # Test 6: _extract_pipeline_from_error extracts REAL scores from dict-based
    # intermediate_results (as the V2 SDK actually provides them)
    class FakeOrchError(Exception):
        pass
    dict_err = FakeOrchError("Content filtered")
    dict_err.location = "input_filtering"
    dict_err.message = "Content was blocked due to hate speech"
    dict_err.intermediate_results = {
        "input_filtering": {
            "message": "Content filter failed.",
            "data": {
                "azure_content_safety": {
                    "hate": 6,
                    "self_harm": 0,
                    "sexual": 0,
                    "violence": 2,
                }
            },
        },
        "templating": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "some inflammatory query"},
        ],
    }
    pipeline = assistant._extract_pipeline_from_error("some inflammatory query", dict_err)
    scores = pipeline["content_filtering"]["input"]
    assert scores["hate"] == 6, f"Expected hate=6, got {scores['hate']}"
    assert scores["violence"] == 2, f"Expected violence=2, got {scores['violence']}"
    assert scores["self_harm"] == 0
    assert scores["sexual"] == 0
    assert scores["passed"] is False
    assert pipeline["llm"]["blocked_by"] == "input_filtering"
    assert "hate speech" in pipeline["llm"]["reason"]
    assert len(pipeline["messages_to_llm"]) == 2
    assert pipeline["messages_to_llm"][1]["content"] == "some inflammatory query"
    print("  ✓ _extract_pipeline_from_error extracts real Azure scores from dict intermediate_results")

    # Test 4: LLMDetails Pydantic model accepts new blocked_by/reason fields
    llm = LLMDetails(model="blocked", prompt_tokens=0, completion_tokens=0,
                     blocked_by="input_filtering", reason="Hate content detected")
    assert llm.blocked_by == "input_filtering"
    assert llm.reason == "Hate content detected"
    print("  ✓ LLMDetails accepts blocked_by and reason fields")

    # Test 5: LLMDetails still works without blocked_by/reason (backwards compat)
    llm_normal = LLMDetails(model="gpt-4o", prompt_tokens=100, completion_tokens=50)
    assert llm_normal.blocked_by is None
    assert llm_normal.reason is None
    print("  ✓ LLMDetails backwards compatible (None defaults)")

    print("\n✓ Content filtered pipeline passed\n")


def test_client_side_masking():
    """Test client-side NRIC/FIN masking in DocAssistant."""
    print("=== Testing Client-Side NRIC Masking ===\n")

    from doc_assistant import DocAssistant

    assistant = DocAssistant()

    # Test 1: Basic NRIC masking (S prefix — citizen born before 2000)
    text, entities = assistant._client_side_mask("My NRIC is S1234567D and I need help.")
    assert "S1234567D" not in text, "NRIC should be masked"
    assert "MASKED_NRIC" in text, "Should contain MASKED_NRIC"
    assert "NRIC" in entities, "Entities should include NRIC"
    print("  ✓ Basic NRIC (S prefix) masked correctly")

    # Test 2: FIN masking (G prefix — foreigner)
    text, entities = assistant._client_side_mask("FIN: G9876543K")
    assert "G9876543K" not in text
    assert "MASKED_NRIC" in text
    assert "NRIC" in entities
    print("  ✓ FIN (G prefix) masked correctly")

    # Test 3: T prefix (citizen born 2000+)
    text, entities = assistant._client_side_mask("ID T0012345J")
    assert "T0012345J" not in text
    assert "MASKED_NRIC" in text
    print("  ✓ NRIC (T prefix) masked correctly")

    # Test 4: M prefix (foreigner 2022+)
    text, entities = assistant._client_side_mask("Number M1234567X")
    assert "M1234567X" not in text
    assert "MASKED_NRIC" in text
    print("  ✓ FIN (M prefix) masked correctly")

    # Test 5: Case-insensitive matching (lowercase)
    text, entities = assistant._client_side_mask("my nric is s1234567d")
    assert "s1234567d" not in text
    assert "MASKED_NRIC" in text
    assert "NRIC" in entities
    print("  ✓ Lowercase NRIC masked correctly")

    # Test 5b: Mixed case
    text, entities = assistant._client_side_mask("FIN: g9876543K")
    assert "g9876543K" not in text
    assert "MASKED_NRIC" in text
    print("  ✓ Mixed-case NRIC masked correctly")

    # Test 6: Multiple NRICs in one string
    text, entities = assistant._client_side_mask("IDs: S1234567D and F9876543N")
    assert "S1234567D" not in text
    assert "F9876543N" not in text
    assert text.count("MASKED_NRIC") == 2
    assert entities == ["NRIC"]  # only one label, not duplicated
    print("  ✓ Multiple NRICs masked, single entity label")

    # Test 6: No NRIC — passthrough unchanged
    text, entities = assistant._client_side_mask("How do I deploy a model on AI Core?")
    assert text == "How do I deploy a model on AI Core?"
    assert entities == []
    print("  ✓ Non-NRIC text passed through unchanged")

    # Test 7: Mock pipeline integration — NRIC in question shows in pipeline
    result = assistant.ask("My NRIC is S1234567D. How do I deploy?", include_pipeline=True)
    pipeline = result["pipeline"]
    assert pipeline["data_masking"] is not None, "Pipeline should show data_masking"
    assert "NRIC" in pipeline["data_masking"]["entities_masked"]
    assert "S1234567D" not in pipeline["data_masking"]["masked_query"]
    assert "MASKED_NRIC" in pipeline["data_masking"]["masked_query"]
    assert "S1234567D" in pipeline["data_masking"]["original_query"]
    # Verify user message to LLM also has NRIC masked
    user_msgs = [m for m in pipeline["messages_to_llm"] if m["role"] == "user"]
    assert any("MASKED_NRIC" in m["content"] for m in user_msgs), \
        "User message to LLM should contain MASKED_NRIC"
    print("  ✓ Mock pipeline shows NRIC masking in data_masking details")

    # Test 8: Question without NRIC — NRIC should not appear in entities
    result = assistant.ask("How do I deploy?", include_pipeline=True)
    if result["pipeline"]["data_masking"] is not None:
        assert "NRIC" not in result["pipeline"]["data_masking"]["entities_masked"], \
            "NRIC should not appear in entities for non-NRIC question"
    print("  ✓ Non-NRIC question: no NRIC in entities_masked")

    print("\n✓ Client-side NRIC masking passed\n")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("SAP AI Documentation Assistant - Local Tests")
    print("=" * 60 + "\n")

    test_kb_loading()
    test_id_uniqueness()
    test_search()
    test_doc_lookup()
    test_services_summary()
    test_kb_management()
    test_available_services()
    test_get_all_entries()
    success = test_mock_assistant()
    test_pipeline_visibility()
    test_empty_query()
    test_content_filtered_pipeline()
    test_client_side_masking()

    print("=" * 60)
    print("TEST SUMMARY: " + ("ALL PASSED ✓" if success else "SOME FAILED ✗"))
    print("=" * 60 + "\n")

    sys.exit(0 if success else 1)
