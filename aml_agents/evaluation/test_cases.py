"""Golden test cases for Phase 11 evaluation. See PROJECT_PLAN.md Phase 11,
section "test_cases.py" for the full requirement.

The GoldenCase type and all_cases() are GIVEN. The lists themselves are data
for you to populate (not logic) — see PROJECT_PLAN.md for what each category
needs and why real public sanctioned names are normal/expected here.
"""

from __future__ import annotations

from typing import Literal, TypedDict


class GoldenCase(TypedDict):
    entity_name: str
    category: Literal["known_sanctioned", "name_variant", "clearly_clean"]
    expected_entity_resolved: bool
    notes: str


# TODO (PROJECT_PLAN.md Phase 11): sample 5-10 real names from your own
# data/raw/sanctions/*.csv after Phase 0 — don't hardcode names here that
# may not be in whatever snapshot you've downloaded.
KNOWN_SANCTIONED: list[GoldenCase] = []

# TODO: deliberate typos/reorderings/transliterations of entries above, to
# test the fuzzy-match threshold in sanctions_lookup.py isn't too strict or
# too loose.
NAME_VARIANTS: list[GoldenCase] = []

# TODO: a handful of clearly fictional, unremarkable names that should
# resolve to no hits. Keep them clearly fictional (see data/README.md).
CLEARLY_CLEAN: list[GoldenCase] = []


def all_cases() -> list[GoldenCase]:
    return [*KNOWN_SANCTIONED, *NAME_VARIANTS, *CLEARLY_CLEAN]
