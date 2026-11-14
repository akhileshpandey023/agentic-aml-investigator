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
from aml_agents import service
from aml_agents.memory import case_store

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
    """Run a new investigation and print the memo, or say the case is waiting
    for a human and why."""

    result = service.start_investigation(build_graph(checkpointer=_get_checkpointer()), args.entity)

    print(f"case_id: {result.case_id}")
    if result.status == "awaiting_review":
        print("PAUSED: awaiting human review before human_gate.")
        print("  Human review required: " + "; ".join(result.review_reasons))
        print(
            f"  Resume with: python -m aml_agents.main resume --case-id {result.case_id} "
            "--decision confirm|override_clear|override_escalate --reviewer NAME"
        )
    if result.risk_memo:
        print(json.dumps(result.risk_memo.model_dump(), indent=2))
    elif result.status == "completed":
        print("No memo was produced; trace:")
        for t in result.trace:
            print(f"  [{t.node_name}] {t.summary_out}")


def cmd_resume(args: argparse.Namespace) -> None:
    """Record a human decision on a paused case, resume past human_gate, save
    and print the memo. Fails clearly if the case is unknown or not waiting."""

    app = build_graph(checkpointer=_get_checkpointer())
    try:
        result = service.resume_investigation(app, args.case_id, args.decision, args.reviewer, args.notes)
    except service.CaseNotFound:
        sys.exit(f"No checkpointed case with id {args.case_id!r}.")
    except service.CaseNotPending as exc:
        sys.exit(str(exc))
    print(json.dumps(result.risk_memo.model_dump(), indent=2))  # type: ignore[union-attr]


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
