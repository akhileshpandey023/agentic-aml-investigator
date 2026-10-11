"""Tool schemas for turning a fixed-pipeline node into a true tool-calling agent.

TOOL_SCHEMAS and TOOL_DISPATCH below are GIVEN (declarative data, not logic).
Not used by the default graph — see ARCHITECTURE.md: the default design has
the *graph* decide which tool each node calls, not the LLM. This exists for
the Phase 13 stretch exercise, detailed in PROJECT_PLAN.md: give an LLM this
tool list and let it decide which to call and in what order, then compare
its behaviour against the fixed pipeline on your golden set.
"""

from __future__ import annotations

from typing import Any, Callable

from aml_agents.tools import adverse_media_search, sanctions_lookup

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "sanctions_lookup",
        "description": "Fuzzy-match a name against the US OFAC SDN and UK OFSI consolidated sanctions lists.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Entity name to search for"},
                "top_k": {"type": "integer", "description": "Max candidates to return", "default": 5},
            },
            "required": ["name"],
        },
    },
    {
        "name": "adverse_media_search",
        "description": "Search the local FCA enforcement-notice corpus for mentions of an entity name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_name": {"type": "string"},
                "top_k": {"type": "integer", "default": 5},
            },
            "required": ["entity_name"],
        },
    },
]

TOOL_DISPATCH: dict[str, Callable[..., Any]] = {
    "sanctions_lookup": sanctions_lookup.lookup,
    "adverse_media_search": adverse_media_search.search,
}


def run_tool_calling_agent(task: str, *, max_turns: int = 6) -> str:
    """TODO (Phase 13, stretch — see PROJECT_PLAN.md): implement a multi-turn
    tool-calling loop:
        1. Start messages = [{"role": "user", "content": task}]
        2. Call the Anthropic API with tools=TOOL_SCHEMAS
        3. If stop_reason != "tool_use", return the final text
        4. Otherwise dispatch the requested tool via TOOL_DISPATCH, append
           both the assistant's tool_use turn and a tool_result turn to
           messages, and loop (up to max_turns)
    Not wired into aml_agents/llm_client.py's single-turn complete() — this
    is a separate, self-contained loop for the stretch exercise.
    """

    raise NotImplementedError("run_tool_calling_agent is a Phase 13 stretch exercise")
