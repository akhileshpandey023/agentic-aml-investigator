"""Agent nodes — the judgment layer on top of aml_agents/tools/.

Every module in this package is a placeholder. Each exposes one function
with signature `(state: CaseState) -> dict`, the LangGraph node convention:
return only the keys you're updating, and LangGraph merges them into the
shared state (see schemas.CaseState's docstring for field ownership, and
note `trace` uses an additive reducer while every other field is
last-write-wins). See PROJECT_PLAN.md for detailed, per-node requirements.
"""
