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

from aml_agents.graph import build_graph
from aml_agents.memory import case_store
from aml_agents.schemas import HumanDecision, new_case_state


def _get_checkpointer():
    """TODO (PROJECT_PLAN.md Phase 10): return a real LangGraph checkpointer,
    e.g. langgraph.checkpoint.sqlite.SqliteSaver pointed at
    config.LANGGRAPH_CHECKPOINT_DB_PATH, so investigate()/resume() below can
    actually pause and resume at human_gate.
    """

    raise NotImplementedError("_get_checkpointer: see PROJECT_PLAN.md Phase 10")


def cmd_investigate(args: argparse.Namespace) -> None:
    """TODO: build the graph with a real checkpointer, build a fresh
    CaseState via new_case_state(entity_name=args.entity), invoke the graph
    with a thread_id config keyed on the case_id, save the result via
    case_store.save_case, and print either the risk memo or the trace (if
    the run paused before producing one). See PROJECT_PLAN.md Phase 10.
    """

    raise NotImplementedError("cmd_investigate: see PROJECT_PLAN.md Phase 10")


def cmd_resume(args: argparse.Namespace) -> None:
    """TODO: build the graph with the same checkpointer/thread_id as the
    original run, build a HumanDecision from args, call
    app.update_state(...) to record it, then app.invoke(None, config=...) to
    resume execution past human_gate, save the result, and print the memo.
    """

    raise NotImplementedError("cmd_resume: see PROJECT_PLAN.md Phase 10")


def cmd_list_pending(_args: argparse.Namespace) -> None:
    """TODO: call case_store.list_cases(pending_human_review=True) and print
    one line per case.
    """

    raise NotImplementedError("cmd_list_pending: see PROJECT_PLAN.md Phase 10")


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
