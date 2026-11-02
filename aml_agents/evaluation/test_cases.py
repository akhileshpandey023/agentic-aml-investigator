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


# Supplied sanctioned-entity sample. Verify these against the locally
# downloaded sanctions snapshot whenever it is refreshed.
KNOWN_SANCTIONED: list[GoldenCase] = [
    {
        "entity_name": "Denis Igorevich Gusev",
        "category": "known_sanctioned",
        "expected_entity_resolved": True,
        "notes": "Individual; exact-name sanctions-screening control.",
    },
    {
        "entity_name": "S-MIKRON ELEKTRONIK ELEKTRIK SANAYI TAAHHUT TICARET ANONIM SIRKETI",
        "category": "known_sanctioned",
        "expected_entity_resolved": True,
        "notes": "Corporate entity; long-form legal-name control.",
    },
    {
        "entity_name": "Ilia Vladimirovich Sidorov",
        "category": "known_sanctioned",
        "expected_entity_resolved": True,
        "notes": "Individual; exact-name sanctions-screening control.",
    },
    {
        "entity_name": "Eliav LIBI",
        "category": "known_sanctioned",
        "expected_entity_resolved": True,
        "notes": "Individual; case-insensitive name-matching control.",
    },
    {
        "entity_name": "KOREA UNITED DEVELOPMENT BANK",
        "category": "known_sanctioned",
        "expected_entity_resolved": True,
        "notes": "Financial institution; exact-name sanctions-screening control.",
    },
]

# TODO: deliberate typos/reorderings/transliterations of entries above, to
# test the fuzzy-match threshold in sanctions_lookup.py isn't too strict or
# too loose.
NAME_VARIANTS: list[GoldenCase] = [
    {
        "entity_name": "Gusev Denis Igorevich",
        "category": "name_variant",
        "expected_entity_resolved": True,
        "notes": "Reordered personal-name tokens.",
    },
    {
        "entity_name": "S-Mikron Elektronik Elektrik Sanayi Taahhut Ticaret AS",
        "category": "name_variant",
        "expected_entity_resolved": True,
        "notes": "Shortened legal suffix and normalised casing.",
    },
    {
        "entity_name": "Ilya Vladimirovich Sidorov",
        "category": "name_variant",
        "expected_entity_resolved": True,
        "notes": "Common transliteration variant of Ilia.",
    },
    {
        "entity_name": "Eliav Libi",
        "category": "name_variant",
        "expected_entity_resolved": True,
        "notes": "Casing-only variation.",
    },
    {
        "entity_name": "Korea United Development Bnk",
        "category": "name_variant",
        "expected_entity_resolved": True,
        "notes": "Single-character deletion in institution name.",
    },
]

# TODO: a handful of clearly fictional, unremarkable names that should
# resolve to no hits. Keep them clearly fictional (see data/README.md).
CLEARLY_CLEAN: list[GoldenCase] = [
    {
        "entity_name": "Willowbrook Stationery Cooperative",
        "category": "clearly_clean",
        "expected_entity_resolved": False,
        "notes": "Fictional local business.",
    },
    {
        "entity_name": "Juniper Lantern Workshop Ltd",
        "category": "clearly_clean",
        "expected_entity_resolved": False,
        "notes": "Fictional small business.",
    },
    {
        "entity_name": "Marta Ellison",
        "category": "clearly_clean",
        "expected_entity_resolved": False,
        "notes": "Fictional individual.",
    },
    {
        "entity_name": "Northmere Community Bakery",
        "category": "clearly_clean",
        "expected_entity_resolved": False,
        "notes": "Fictional local business.",
    },
    {
        "entity_name": "Alderfield Garden Services",
        "category": "clearly_clean",
        "expected_entity_resolved": False,
        "notes": "Fictional local business.",
    },
]


def all_cases() -> list[GoldenCase]:
    return [*KNOWN_SANCTIONED, *NAME_VARIANTS, *CLEARLY_CLEAN]
