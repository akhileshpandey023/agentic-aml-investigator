"""Adverse Media agent.

PLACEHOLDER — see PROJECT_PLAN.md Phase 4, section "adverse_media_node".

Reads:  state["entity_name"]
Writes: state["adverse_media_findings"], state["trace"]
"""

from __future__ import annotations

import time

from aml_agents.schemas import CaseState, make_trace
from aml_agents.tools.adverse_media_search import search
from aml_agents import config

def adverse_media_node(state: CaseState) -> dict:
    """TODO: call aml_agents.tools.adverse_media_search.search on
    state["entity_name"], apply a relevance gate (see PROJECT_PLAN.md Phase 4
    for the threshold and the rationale), handle the case where the corpus
    hasn't been populated yet (catch FileNotFoundError, degrade to an empty
    list rather than crashing the graph run), and return
    {"adverse_media_findings": ..., **make_trace(...)}.
    """
    start_time = time.perf_counter()
    try:
        adversial_media_result = search(state["entity_name"])
        subset_result = [item for item in adversial_media_result if item.relevance_score >= config.ADVERSE_MEDIA_RELEVANCE_SCORE] 
    except FileNotFoundError:
        adversial_media_result = []
        subset_result = []
    end_time = time.perf_counter()
    
    return {
        'adverse_media_findings': subset_result,
        **make_trace(
            node_name='adverse_media_search',
            summary_in=state['entity_name'],
            summary_out=(
                f"{len(adversial_media_result)} candidate(s) found in adverse media search of which kept {len(subset_result)} results"
                ),
                duration_ms=end_time-start_time
                ),
        }

    
