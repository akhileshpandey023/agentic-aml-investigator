"""CLI entrypoint.

    uv run python -m aml_agents.main investigate --entity "Some Entity Name"
    uv run python -m aml_agents.main resume --case-id <id> --decision confirm --reviewer "you"
    uv run python -m aml_agents.main list-pending

"""

from __future__ import annotations

import argparse
import sys
import json 

from aml_agents.checkpointing import make_serde
from aml_agents.graph import build_graph
from aml_agents.memory import case_store
from aml_agents.schemas import HumanDecision, new_case_state

from aml_agents import config

from langgraph.checkpoint.sqlite import SqliteSaver
import sqlite3


def _get_checkpointer() -> SqliteSaver:
    db_path = config.LANGGRAPH_CHECKPOINT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    checkpointer = SqliteSaver(conn, serde=make_serde())
    checkpointer.setup()
    return checkpointer


def cmd_investigate(args: argparse.Namespace) -> None:
    """Run a new investigation; save the case; print the memo, or say the case
    is waiting for a human and why."""

    app = build_graph(checkpointer=_get_checkpointer())
    state = new_case_state(entity_name=args.entity)
    run_config = {"configurable": {"thread_id": state["case_id"]}}
    app.invoke(state, config=run_config)  # type: ignore
    snapshot = app.get_state(run_config)  # type: ignore
    result = dict(snapshot.values)
    case_store.save_case(result)  # type: ignore

    print(f"case_id: {result['case_id']}")
    memo = result.get("risk_memo")
    if snapshot.next:
        print(f"PAUSED: awaiting human review before {', '.join(snapshot.next)}.")
        for t in result.get("trace", []):
            if t.node_name == "mark_human_review_required":
                print(f"  {t.summary_out}")
        print(
            f"  Resume with: python -m aml_agents.main resume --case-id {result['case_id']} "
            "--decision confirm|override_clear|override_escalate --reviewer NAME"
        )
    if memo:
        print(json.dumps(memo.model_dump(), indent=2))
    elif not snapshot.next:
        print("No memo was produced; trace:")
        for t in result.get("trace", []):
            print(f"  [{t.node_name}] {t.summary_out}")


def cmd_resume(args: argparse.Namespace) -> None:
    """Record a human decision on a paused case, resume past human_gate, save
    and print the result. Fails clearly if the case is unknown or not waiting."""

    app = build_graph(checkpointer=_get_checkpointer())
    run_config = {"configurable": {"thread_id": args.case_id}}
    snapshot = app.get_state(run_config)  # type: ignore
    if not snapshot.values:
        sys.exit(f"No checkpointed case with id {args.case_id!r}.")
    if tuple(snapshot.next) != ("human_gate",):
        sys.exit(f"Case {args.case_id} is not waiting for human review (next steps: {list(snapshot.next) or 'none, already finished'}).")

    human_decision = HumanDecision(decision=args.decision, reviewer=args.reviewer, notes=args.notes)
    app.update_state(run_config, {"human_decision": human_decision})  # type: ignore
    app.invoke(None, config=run_config)  # type: ignore
    result = dict(app.get_state(run_config).values)  # type: ignore
    case_store.save_case(result)  # type: ignore

    print(json.dumps(result["risk_memo"].model_dump(), indent=2))


def cmd_list_pending(_args: argparse.Namespace) -> None:
    """TODO: call case_store.list_cases(pending_human_review=True) and print
    one line per case.
    """

    pending_cases = case_store.list_cases(pending_human_review=True)
    for case in pending_cases:
        print(f"""Case Id: {case['case_id']}, Entity Name: {case['entity_name']}, 
        Risk Score: {case['risk_score']}, Recommended Action: {case['recommended_action']}""")


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
