"""CLI entrypoint.

    uv run python -m aml_agents.main investigate --entity "Some Entity Name"
    uv run python -m aml_agents.main resume --case-id <id> --decision confirm --reviewer "you"
    uv run python -m aml_agents.main list-pending

The argparse wiring in main() is GIVEN (plain CLI boilerplate). The command
functions and _get_checkpointer are PLACEHOLDERS — see PROJECT_PLAN.md
Phase 10, section "main.py".
"""

from __future__ import annotations

import argparse
import sys
import json 

from aml_agents.graph import build_graph
from aml_agents.memory import case_store
from aml_agents.schemas import HumanDecision, new_case_state

from aml_agents import config

from langgraph.checkpoint.sqlite import SqliteSaver


def _get_checkpointer():
    """TODO (PROJECT_PLAN.md Phase 10): return a real LangGraph checkpointer,
    e.g. langgraph.checkpoint.sqlite.SqliteSaver pointed at
    config.LANGGRAPH_CHECKPOINT_DB_PATH, so investigate()/resume() below can
    actually pause and resume at human_gate.
    """

    return SqliteSaver.from_conn_string(str(config.LANGGRAPH_CHECKPOINT_DB_PATH))
    


def cmd_investigate(args: argparse.Namespace) -> None:
    """TODO: build the graph with a real checkpointer, build a fresh
    CaseState via new_case_state(entity_name=args.entity), invoke the graph
    with a thread_id config keyed on the case_id, save the result via
    case_store.save_case, and print either the risk memo or the trace (if
    the run paused before producing one). See PROJECT_PLAN.md Phase 10.
    """

    app = build_graph(checkpointer=_get_checkpointer())
    state = new_case_state(entity_name=args.entity)
    run_config = {"configurable": {"thread_id": state["case_id"]}}
    result = app.invoke(state, config=run_config) # type: ignore
    case_store.save_case(result) # type: ignore

    print(f"case_id: {result['case_id']}")
    if result.get("risk_memo"):
        print(json.dumps(result["risk_memo"].model_dump(), indent=2))
    else:
        print("(paused before human_gate, or no memo produced — inspect the trace)")
        for t in result.get("trace", []):
            print(f"  [{t.node_name}] {t.summary_out}")


def cmd_resume(args: argparse.Namespace) -> None:
    """TODO: build the graph with the same checkpointer/thread_id as the
    original run, build a HumanDecision from args, call
    app.update_state(...) to record it, then app.invoke(None, config=...) to
    resume execution past human_gate, save the result, and print the memo.
    """

    app = build_graph(checkpointer=_get_checkpointer())
    run_config = {"configurable": {"thread_id": args.case_id}}
    human_decision = HumanDecision(decision= args.decision, reviewer= args.reviewer, notes= args.notes)

    app.update_state(run_config, {"human_decision": human_decision}) # type: ignore
    result = app.invoke(None, config=run_config) # type: ignore

    case_store.save_case(result) # type: ignore

    print(result.get('memo'))

def cmd_list_pending(_args: argparse.Namespace) -> None:
    """TODO: call case_store.list_cases(pending_human_review=True) and print
    one line per case.
    """

    pending_cases = case_store.list_cases(pending_human_review=True)
    for case in pending_cases:
        print(f"""Case Id: {case['case_id']}, Entity Name: {case['entity_name']}, 
        Risk Case: {case['risk_score']}, Recommended Action: {case['recommended_action']}""")


def main() -> None:
    """GIVEN. Plain argparse wiring."""

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_investigate = sub.add_parser("investigate", help="Run a new investigation")
    p_investigate.add_argument("--entity", required=True)
    p_investigate.set_defaults(func=cmd_investigate)

    p_resume = sub.add_parser("resume", help="Record a human decision and resume a paused case")
    p_resume.add_argument("--case-id", required=True)
    p_resume.add_argument("--decision", required=True, choices=["confirm", "override_clear", "override_escalate"])
    p_resume.add_argument("--reviewer", required=True)
    p_resume.add_argument("--notes", default="")
    p_resume.set_defaults(func=cmd_resume)

    p_pending = sub.add_parser("list-pending", help="List cases awaiting human review")
    p_pending.set_defaults(func=cmd_list_pending)

    args = parser.parse_args()
    try:
        args.func(args)
    except NotImplementedError as exc:
        print(f"\nNot implemented yet: {exc}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
