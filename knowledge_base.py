"""
Knowledge Base for SAP AI Documentation

Provides:
- Loading/saving the KB from/to a JSON file
- A search tool function for LLM tool calling
- CRUD operations for KB management API
- Utility functions for doc lookups and service summaries
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Path to the knowledge base JSON file (same directory as this module)
KB_FILE = Path(os.path.dirname(os.path.abspath(__file__))) / "knowledge_base.json"

# In-memory cache of the knowledge base
_kb_cache: dict | None = None


def load_knowledge_base() -> dict:
    """Load the knowledge base from the JSON file.

    Returns the full KB dict with structure:
    {"services": {"ai_core": {"display_name": ..., "description": ..., "docs": [...]}}}
    """
    global _kb_cache
    if _kb_cache is not None:
        return _kb_cache

    try:
        with open(KB_FILE) as f:
            _kb_cache = json.load(f)
        logger.info(f"Loaded knowledge base with {_count_total_docs(_kb_cache)} entries")
        return _kb_cache
    except FileNotFoundError:
        logger.warning(f"Knowledge base file not found: {KB_FILE}")
        _kb_cache = {"services": {}}
        return _kb_cache
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in knowledge base file: {e}")
        _kb_cache = {"services": {}}
        return _kb_cache


def save_knowledge_base(kb: dict) -> None:
    """Persist the knowledge base to the JSON file."""
    global _kb_cache
    with open(KB_FILE, "w") as f:
        json.dump(kb, f, indent=2)
    _kb_cache = kb
    logger.info(f"Saved knowledge base with {_count_total_docs(kb)} entries")


def _count_total_docs(kb: dict) -> int:
    """Count total documentation entries across all services."""
    return sum(len(svc.get("docs", [])) for svc in kb.get("services", {}).values())


def _invalidate_cache() -> None:
    """Clear the in-memory cache so next load reads from disk."""
    global _kb_cache
    _kb_cache = None


def search_knowledge_base(query: str, service: str | None = None) -> str:
    """Search SAP AI documentation knowledge base.

    This function is designed to be called as a tool by the LLM.

    Args:
        query: Search terms related to the user's question
        service: Optional service key to filter results (e.g., 'ai_core')

    Returns:
        JSON string of matching documentation entries (max 10 results)
    """
    kb = load_knowledge_base()
    query_lower = query.lower()
    query_terms = query_lower.split()

    results = []
    services = kb.get("services", {})

    # Filter to specific service if requested
    if service and service in services:
        search_services = {service: services[service]}
    else:
        search_services = services

    for svc_key, svc_data in search_services.items():
        for doc in svc_data.get("docs", []):
            score = _score_doc(doc, svc_data, query_terms, query_lower)
            if score > 0:
                results.append({
                    "id": doc["id"],
                    "service": svc_key,
                    "title": doc["title"],
                    "url": doc["url"],
                    "description": doc["description"],
                    "tags": doc.get("tags", []),
                    "score": score,
                })

    # Sort by score descending, take top 10
    results.sort(key=lambda x: x["score"], reverse=True)
    top_results = results[:10]

    # Remove score from output (internal detail)
    for r in top_results:
        del r["score"]

    return json.dumps(top_results)


def _score_doc(doc: dict, svc_data: dict, query_terms: list[str], query_lower: str) -> float:
    """Score a document's relevance to the search query.

    Uses keyword matching against title, description, tags, and service info.
    """
    score = 0.0
    title_lower = doc.get("title", "").lower()
    desc_lower = doc.get("description", "").lower()
    tags_lower = [t.lower() for t in doc.get("tags", [])]
    svc_name_lower = svc_data.get("display_name", "").lower()
    svc_desc_lower = svc_data.get("description", "").lower()

    searchable = f"{title_lower} {desc_lower} {' '.join(tags_lower)} {svc_name_lower} {svc_desc_lower}"

    for term in query_terms:
        if len(term) < 2:
            continue
        if term in title_lower:
            score += 3.0  # Title match is most important
        if term in desc_lower:
            score += 2.0
        if any(term in tag for tag in tags_lower):
            score += 2.5  # Tag match is very relevant
        if term in svc_name_lower:
            score += 1.5
        if term in svc_desc_lower:
            score += 0.5

    return score


def get_docs_by_ids(doc_ids: list[str]) -> list[dict]:
    """Look up full documentation entries by their IDs.

    Returns a list of dicts with id, service, title, url, description.
    """
    kb = load_knowledge_base()
    results = []
    id_set = set(doc_ids)

    for svc_key, svc_data in kb.get("services", {}).items():
        for doc in svc_data.get("docs", []):
            if doc["id"] in id_set:
                results.append({
                    "id": doc["id"],
                    "service": svc_key,
                    "title": doc["title"],
                    "url": doc["url"],
                    "description": doc["description"],
                })

    return results


def get_all_doc_ids() -> set[str]:
    """Get the set of all valid document IDs in the knowledge base."""
    kb = load_knowledge_base()
    ids = set()
    for svc_data in kb.get("services", {}).values():
        for doc in svc_data.get("docs", []):
            ids.add(doc["id"])
    return ids


def get_services_summary() -> str:
    """Generate a formatted string of available services for the system prompt."""
    kb = load_knowledge_base()
    lines = []
    for key, svc in kb.get("services", {}).items():
        doc_count = len(svc.get("docs", []))
        lines.append(f"- {key}: {svc['display_name']} — {svc['description']} ({doc_count} docs)")
    return "\n".join(lines)


# --- KB Management Functions (for the API) ---

def add_entry(service_key: str, entry: dict) -> str | None:
    """Add a new documentation entry to a service.

    Args:
        service_key: The service to add the entry to
        entry: Dict with title, url, description, and optional tags

    Returns:
        The generated doc ID, or None if the service doesn't exist
    """
    kb = load_knowledge_base()
    services = kb.get("services", {})

    if service_key not in services:
        return None

    # Generate a unique ID
    existing_ids = get_all_doc_ids()
    base_id = f"{service_key}_{len(services[service_key].get('docs', [])) + 1:02d}"
    doc_id = base_id
    counter = 1
    while doc_id in existing_ids:
        doc_id = f"{service_key}_{len(services[service_key].get('docs', [])) + counter:02d}"
        counter += 1

    new_doc = {
        "id": doc_id,
        "title": entry["title"],
        "url": entry["url"],
        "description": entry["description"],
        "tags": entry.get("tags", []),
    }

    services[service_key]["docs"].append(new_doc)
    save_knowledge_base(kb)
    return doc_id


def update_entry(doc_id: str, updates: dict) -> bool:
    """Update an existing documentation entry.

    Args:
        doc_id: The ID of the document to update
        updates: Dict of fields to update (title, url, description, tags)

    Returns:
        True if the entry was found and updated, False otherwise
    """
    kb = load_knowledge_base()

    for svc_data in kb.get("services", {}).values():
        for doc in svc_data.get("docs", []):
            if doc["id"] == doc_id:
                for field in ("title", "url", "description", "tags"):
                    if field in updates and updates[field] is not None:
                        doc[field] = updates[field]
                save_knowledge_base(kb)
                return True

    return False


def delete_entry(doc_id: str) -> bool:
    """Remove a documentation entry from the knowledge base.

    Returns True if the entry was found and deleted, False otherwise.
    """
    kb = load_knowledge_base()

    for svc_data in kb.get("services", {}).values():
        docs = svc_data.get("docs", [])
        for i, doc in enumerate(docs):
            if doc["id"] == doc_id:
                docs.pop(i)
                save_knowledge_base(kb)
                return True

    return False


def get_all_entries(service_filter: str | None = None) -> list[dict]:
    """Get all KB entries, optionally filtered by service.

    Returns a list of dicts with id, service_key, title, url, description, tags.
    """
    kb = load_knowledge_base()
    results = []

    for svc_key, svc_data in kb.get("services", {}).items():
        if service_filter and svc_key != service_filter:
            continue
        for doc in svc_data.get("docs", []):
            results.append({
                "id": doc["id"],
                "service_key": svc_key,
                "title": doc["title"],
                "url": doc["url"],
                "description": doc["description"],
                "tags": doc.get("tags", []),
            })

    return results


def get_available_services() -> list[dict]:
    """Get a list of available services with their metadata."""
    kb = load_knowledge_base()
    services = []
    for key, svc in kb.get("services", {}).items():
        services.append({
            "key": key,
            "display_name": svc.get("display_name", key),
            "description": svc.get("description", ""),
            "doc_count": len(svc.get("docs", [])),
        })
    return services
