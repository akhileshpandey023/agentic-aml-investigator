"""Entity Resolution agent.

PLACEHOLDER — see PROJECT_PLAN.md Phase 2, section "entity_resolution_node".

Reads:  state["entity_name"]
Writes: state["entity_candidates"], state["entity_resolved"], state["trace"]
"""

from __future__ import annotations
import time

from aml_agents.schemas import CaseState, make_trace
from aml_agents.tools.sanctions_lookup import lookup

from aml_agents import config


def entity_resolution_node(state: CaseState) -> dict:
    """TODO: call aml_agents.tools.sanctions_lookup.lookup on
    state["entity_name"], decide entity_resolved (True iff at least one
    candidate scores >= config.ENTITY_MATCH_MIN_SCORE), time the call, and
    return {"entity_candidates": ..., "entity_resolved": ..., **make_trace(...)}.
    See PROJECT_PLAN.md Phase 2 for the full requirement and what to put in
    the trace summary.
    """
    start_time = time.perf_counter()
    list_entity_matches = lookup(state['entity_name'], 
                                 source_lists=["us_ofac_sdn", "gb_hmt_sanctions"],
                                 top_k=config.ENTITY_MATCH_TOP_K,
                                 min_score=config.ENTITY_MATCH_MIN_SCORE)

    top_candidates = [item for item in list_entity_matches if item.match_score >= config.ENTITY_MATCH_MIN_SCORE]
    top_one = top_candidates[0] if len(top_candidates) > 0 else None
    end_time = time.perf_counter()

    return {
        'entity_candidates': list_entity_matches, 
        'entity_resolved': True if len(top_candidates)> 0 else False, 
        **make_trace(
            node_name='entity_resolution',
            summary_in=state['entity_name'],
            summary_out=(
                f"{len(list_entity_matches)} candidate(s); top={top_one.matched_name!r} score={top_one.match_score:.1f}" 
                if top_one 
                else "no candidates above threshold"
                ),
                duration_ms=(end_time-start_time)*1000
                ),
            }