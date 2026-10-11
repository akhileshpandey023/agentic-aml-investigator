"""Manual diagnostic script for after Phase 5 (Planner): runs the
evidence-gathering half of the pipeline — planner -> entity_resolution ->
adverse_media -> retrieval — against two entity names (one expected to be
on the UK sanctions list, one not) and prints every agent's output to the
terminal, including the RAG/retrieval search results.

Placement: this lives in scripts/, not tests/, even though it's named
test_case_rag.py. pytest's testpaths (see pyproject.toml) only looks inside
tests/, so putting it there and naming it test_* would make `uv run pytest`
pick it up and try to execute it as an automated test on every run — which
would fail for anyone who hasn't downloaded the sanctions CSVs or ingested
the guidance corpus yet (Phase 0), breaking the "tests should pass before
you write any agent logic" promise in README.md. This script is meant to be
read, not asserted on in CI.

Why it bypasses graph.py entirely: risk_analyst and critic (Phase 6-7)
still raise NotImplementedError, so invoking the compiled LangGraph graph
via build_graph().invoke() would crash partway through. This script calls
the four already-implemented node functions directly, in the same order
graph.py wires them, and merges their outputs into CaseState by hand —
including replicating the operator.add reducer LangGraph applies to the
`trace` field (see schemas.CaseState) in _merge() below, since we're not
going through LangGraph's own state-merge machinery at all here.

Usage:
    uv run python scripts/test_case_rag.py
    uv run python scripts/test_case_rag.py --present "Exact Name From Your CSV" --absent "Some Clean Name"

With no args: --present is auto-picked from your own downloaded
data/raw/sanctions/gb_hmt_sanctions.csv (the first real name in the file),
so nothing here is hardcoded against a snapshot of a public list that moves
over time (see the same caution in data/README.md and
aml_agents/evaluation/test_cases.py). --absent defaults to the first
fictional name already defined in evaluation/test_cases.py's CLEARLY_CLEAN
set, for consistency with the Phase 10 golden set.
"""

from __future__ import annotations

import argparse

import pandas as pd

from aml_agents import config
from aml_agents.evaluation.test_cases import CLEARLY_CLEAN
from aml_agents.nodes import retrieval as retrieval_module
from aml_agents.nodes.adverse_media import adverse_media_node
from aml_agents.nodes.entity_resolution import entity_resolution_node
from aml_agents.nodes.planner import planner_node
from aml_agents.nodes.retrieval import retrieval_node
from aml_agents.schemas import CaseState, new_case_state

# Same order graph.py wires these in, up to (not including) risk_analyst.
PIPELINE = [
    ("planner", planner_node),
    ("entity_resolution", entity_resolution_node),
    ("adverse_media", adverse_media_node),
    ("retrieval", retrieval_node),
]


def _merge(state: CaseState, update: dict) -> CaseState:
    """Mirrors LangGraph's per-key state merge for the fields this pipeline
    touches: every field is last-write-wins EXCEPT `trace`, which CaseState
    annotates with operator.add (see schemas.py) — LangGraph concatenates
    that field across node calls instead of overwriting it. We're not going
    through LangGraph here, so we replicate that one special case by hand;
    every other key behaves like a normal dict.update().
    """

    merged = dict(state)
    for key, value in update.items():
        if key == "trace":
            merged["trace"] = merged.get("trace", []) + value
        else:
            merged[key] = value
    return merged  # type: ignore # CaseState is a TypedDict -> plain dict at runtime


def _pick_present_name() -> str | None:
    """Auto-select a real name straight from the downloaded OFSI CSV rather
    than hardcoding one. Using the literal name guarantees a ~100 fuzzy-match
    score against itself, so this is a reliable true-positive case as long
    as Phase 0's download has been run — if it hasn't, this returns None and
    main() skips the present-case run rather than inventing fake data.
    """

    path = config.SANCTIONS_DIR / "gb_hmt_sanctions.csv"
    if not path.exists():
        print(
            f"WARNING: {path} not found -- skipping the 'present' case.\n"
            f"  Run `python scripts/download_public_data.py --sanctions` first (see data/README.md),\n"
            f"  or pass --present \"Some Name\" explicitly."
        )
        return None
    df = pd.read_csv(path, dtype=str).fillna("")
    non_empty = df[df["name"] != ""]
    if non_empty.empty:
        print(f"WARNING: {path} has no usable 'name' values -- skipping the 'present' case.")
        return None
    return non_empty.iloc[0]["name"]


def _pick_absent_name() -> str:
    if CLEARLY_CLEAN:
        return CLEARLY_CLEAN[0]["entity_name"]
    return "Alderbrook Community Bakery Ltd"  # fallback if that list is ever emptied


def run_pipeline(entity_name: str) -> CaseState:
    state = new_case_state(entity_name=entity_name)
    for node_name, node_fn in PIPELINE:
        try:
            update = node_fn(state)
        except Exception as exc:  # noqa: BLE001 - deliberately broad: this is a diagnostic
            # script. One node's missing dependency (Phase 0 data not downloaded, guidance
            # corpus not ingested) shouldn't stop us from showing what the other nodes did.
            print(f"  ! {node_name} raised {type(exc).__name__}: {exc}")
            continue
        state = _merge(state, update)
    return state


def _print_section(title: str) -> None:
    print(f"\n{'-' * 70}\n{title}\n{'-' * 70}")


def print_result(label: str, state: CaseState) -> None:
    print(f"\n{'=' * 70}")
    print(f"ENTITY: {state['entity_name']}  ({label})")
    print(f"{'=' * 70}")

    plan = state.get("plan")
    if plan:
        _print_section("PLAN")
        print(f"steps: {plan.steps}")
        print(f"rationale: {plan.rationale}")

    _print_section(f"ENTITY RESOLUTION  (resolved={state.get('entity_resolved')})")
    candidates = state.get("entity_candidates", [])
    if candidates:
        for c in candidates:
            print(
                f"  [{c.source_list}] {c.matched_name!r}  score={c.match_score:.1f}  "
                f"program={c.program!r}  country={c.country!r}  id={c.source_id}"
            )
    else:
        print("  (no candidates above match threshold)")

    _print_section("ADVERSE MEDIA FINDINGS")
    findings = state.get("adverse_media_findings", [])
    if findings:
        for h in findings:
            print(f"  [{h.source}] relevance={h.relevance_score:.3f}  {h.title}")
            print(f"    {h.snippet[:200].strip()}...")
    else:
        print("  (none found / corpus not populated -- see data/README.md section 2)")

    _print_section("RAG / REGULATORY RETRIEVAL RESULTS")
    passages = state.get("regulatory_context", [])
    if passages:
        for i, p in enumerate(passages, 1):
            print(f"  #{i}  source={p.source_document}  cross_encoder_score={p.score:.4f}")
            print(f"      {p.text[:300].strip()}...")
    else:
        print("  (no passages retrieved -- is data/raw/regulatory/guidance/*.txt ingested?)")

    _print_section("TRACE (node timings)")
    for t in state.get("trace", []):
        dur = f"{t.duration_ms:.1f}ms" if t.duration_ms is not None else "?"
        print(f"  [{t.node_name:<18}] {dur:>10}   {t.summary_out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--present", help="Entity name expected to be ON the sanctions list")
    parser.add_argument("--absent", help="Entity name expected NOT to be on the sanctions list")
    args = parser.parse_args()

    present_name = args.present or _pick_present_name()
    absent_name = args.absent or _pick_absent_name()

    # Ingest the regulatory guidance corpus once, in-process, before either
    # case runs retrieval. This matters even if you've ingested in a
    # previous run of a different process: VectorStore's BM25 half of the
    # hybrid search is rebuilt in memory on ingest and is NOT persisted to
    # disk the way the Chroma embeddings are (see aml_agents/tools/
    # vector_store.py) -- skip this and lexical retrieval silently
    # contributes nothing, degrading to dense-only search with no error.
    # _get_store() is "private" by convention (leading underscore) but is
    # currently the only way to reach the module's cached VectorStore
    # instance; reused here so retrieval_node's later calls see the same
    # already-ingested store rather than a second, empty one.
    store = retrieval_module._get_store()
    try:
        n_chunks = store.ingest_dir()
        print(f"Ingested {n_chunks} chunks from {config.GUIDANCE_DIR}")
    except FileNotFoundError as exc:
        print(f"WARNING: {exc}")

    cases: list[tuple[str, str]] = []
    if present_name:
        cases.append(("expected ON the sanctions list", present_name))
    else:
        print("Skipping present-case run (no name available).")
    if absent_name:
        cases.append(("expected NOT on the sanctions list", absent_name))

    results: list[tuple[str, CaseState]] = []
    for i, (label, name) in enumerate(cases, 1):
        print(f"\nRunning case {i}/{len(cases)} -- {label}: {name!r}")
        results.append((label, run_pipeline(name)))

    for label, state in results:
        print_result(label, state)

    _print_section("SUMMARY")
    for label, state in results:
        print(f"  {state['entity_name']!r:<45} entity_resolved={state.get('entity_resolved')!s:<6} ({label})")


if __name__ == "__main__":
    main()