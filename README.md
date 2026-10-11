# Agentic AML Investigator

A hands-on practice project for learning **agentic AI solution development**
by *implementing* a multi-agent case investigation assistant for
financial-crime alert triage, using only public data.

This is a scaffold, not a finished project you can run out of the box.
Almost every function in `aml_agents/` is a placeholder — a real signature,
type hints, a docstring pointing at its exact requirement, and
`raise NotImplementedError`. **You write the bodies.** The two files that
aren't placeholders (`schemas.py`, `config.py`) are the contracts everything
else is specified against — read those first.

## Start here

1. Read `ARCHITECTURE.md` — the agent taxonomy (nine distinct agent types,
   each with one job) and the target graph shape. This is the *design*;
   nothing here is code yet.
2. Read `PROJECT_PLAN.md` — the actual spec. It's organized into 14 phases,
   and for every placeholder file it tells you, function by function: what
   it must do, the edge cases to handle, and how to check you got it right.
   **This is the single source of truth for requirements** — code docstrings
   deliberately don't repeat the detail, they just point here, so there's
   never two versions of a requirement that can drift apart.
3. Work through the phases in order. Each one has acceptance criteria —
   usually a test file you make pass *without editing it*.

## The problem

Given the name of an entity that has triggered a financial-crime alert,
produce a **case memo**: a structured, cited, risk-scored write-up
recommending clear / escalate / file-SAR — the kind of artifact an AML
analyst produces during alert triage. The finished system:

1. resolves the entity against public sanctions data,
2. gathers adverse-media-style evidence from a public enforcement-notice corpus,
3. retrieves the relevant regulatory guidance passages (RAG),
4. synthesizes a risk memo with citations,
5. critiques its own memo for unsupported claims (reflection),
6. escalates to a human reviewer above a risk/confidence threshold,
7. persists the case so it can be queried or resumed later.

Why this problem: it maps onto AML/transaction-monitoring/sanctions work so
you can judge outputs for realism, every data source is public (see
`data/README.md`), and it naturally needs every major agent archetype
rather than forcing them in artificially.

## Given vs. placeholder — what you're actually implementing

**Given (don't need to touch, and the test suite assumes they're exactly as
provided):**
- `aml_agents/schemas.py`, `aml_agents/config.py` — the contracts
- `tests/` — your acceptance criteria
- `scripts/download_public_data.py`, `scripts/ingest_guidance.py` — HTTP/PDF
  plumbing, not agent logic
- `aml_agents/main.py`'s `main()` function (the argparse wiring) and
  `aml_agents/tools/tool_registry.py`'s `TOOL_SCHEMAS`/`TOOL_DISPATCH` (data,
  not logic)

**Placeholder — this is the project:**
- `aml_agents/llm_client.py` — both backend implementations
- `aml_agents/tools/sanctions_lookup.py`, `adverse_media_search.py`,
  `vector_store.py` — the tool layer
- `aml_agents/nodes/*.py` — all seven agent nodes
- `aml_agents/graph.py` — the LangGraph wiring and routing logic
- `aml_agents/memory/case_store.py` — the durable case record
- `aml_agents/main.py`'s command functions
- `aml_agents/evaluation/metrics.py`, `test_cases.py`

## Tech choices (and why)

- **LangGraph** for orchestration — nodes are agents, edges (including
  conditional edges) are routing logic, and the graph's state is the agents'
  shared memory.
- **Pydantic** for every agent's input/output contract.
- **Chroma + BM25 + cross-encoder rerank** for retrieval — the same pattern
  as your compliance Q&A assistant, reused here as one agent's tool.
- A pluggable `llm_client.py` so the same graph runs against the Anthropic
  API or an OpenAI-compatible local endpoint (Ollama/vLLM on your own
  hardware) by changing one env var.
- **uv** for environment/dependency management. The project pins Python 3.12
  via `.python-version` — some of the heavier compiled dependencies here
  (`chromadb`, `sentence-transformers`'s `torch`) don't reliably have
  prebuilt wheels for brand-new Python releases yet.

## Setup

```bash
uv sync
cp .env.example .env          # fill in ANTHROPIC_API_KEY or LOCAL_LLM_BASE_URL
python scripts/download_public_data.py --all
uv run pytest -q              # almost everything fails right now — that's expected
```

Every test failing with `NotImplementedError` right after setup is the
correct starting state, not a bug. `PROJECT_PLAN.md` Phase 0 and Phase 1
cover what to do before writing any code; Phase 2 is where you start turning
tests green.

If `uv sync` or `pytest` can't find a dependency that's clearly in
`pyproject.toml`, re-run with a clean venv (`rm -rf .venv && uv sync`) and
watch for red error lines — a partial dependency-resolution failure can
silently leave packages missing rather than erroring loudly, especially
around the heavier ML packages.
