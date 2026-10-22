"""Retrieval (RAG) agent.

PLACEHOLDER — see PROJECT_PLAN.md Phase 3, section "retrieval_node".

Reads:  state["entity_name"], state["entity_candidates"], state["adverse_media_findings"]
Writes: state["regulatory_context"], state["trace"]
"""

from __future__ import annotations

from aml_agents.schemas import CaseState, make_trace
from aml_agents.tools.vector_store import VectorStore

import time

_store: VectorStore | None = None

def _get_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store

def _build_query(state: CaseState) -> str:
    """TODO: build a retrieval query string from what's known about the case
    so far (not just the bare entity name) — see PROJECT_PLAN.md Phase 3 for
    what the query should reflect (sanctions programme, whether adverse
    media was found, etc.).
    """
    parts = ["customer due diligence and sanctions screening obligations"]
    if state.get("entity_candidates"):
        programs = {c.program for c in state["entity_candidates"] if c.program}
        if programs:
            parts.append(f"specific to sanctions programme(s): {', '.join(sorted(programs))}")
    if state.get("adverse_media_findings"):
        parts.append("and obligations when adverse media / enforcement history is identified")
    return "; ".join(parts)


def retrieval_node(state: CaseState) -> dict:
    """TODO: build a query via _build_query, call your VectorStore's .query()
    (module-level singleton — see PROJECT_PLAN.md Phase 3 for the pattern),
    handle FileNotFoundError (no guidance corpus ingested yet) by degrading
    to an empty list, and return
    {"regulatory_context": ..., **make_trace(...)}.
    """
    start_time = time.perf_counter()
    query = _build_query(state)
    
    try:
        passages = _get_store().query(query)
    except Exception as e:
        passages = []

    end_time = time.perf_counter()
    
    return {'regulatory_context': passages,
            **make_trace(
                node_name='retrieval',
                summary_in=f"query={query!r}",
                summary_out=f"{len(passages)} passage(s) after rerank",
                duration_ms=(end_time-start_time)*1000
                ),
                }
