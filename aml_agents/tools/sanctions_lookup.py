"""Fuzzy-match a name against the downloaded public sanctions CSVs.

PLACEHOLDER — see PROJECT_PLAN.md Phase 2, section "sanctions_lookup.py",
for detailed requirements, the expected CSV schema, and edge cases.

Structure below (imports, _SOURCE_FILES, the @lru_cache on _load_list) is
given because tests/test_sanctions_lookup.py depends on it directly
(it monkeypatches _SOURCE_FILES and calls _load_list.cache_clear()) — keep
these names and decorators exactly as they are; implement the bodies.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process, utils

from aml_agents import config
from aml_agents.schemas import EntityMatch

_SOURCE_FILES: dict[str, Path] = {
    "us_ofac_sdn": config.SANCTIONS_DIR / "us_ofac_sdn.csv",
    "gb_hmt_sanctions": config.SANCTIONS_DIR / "gb_hmt_sanctions.csv",
}

_ALIAS_SEPARATORS = re.compile(r"[;|]")


@functools.lru_cache(maxsize=None)
def _load_list(source_list: str) -> pd.DataFrame:
    """Load one sanctions CSV (all columns as text, blanks as ""), plus a flat
    index of every name and alias on the frame's `attrs` so lookup can match
    aliases without rebuilding it. Cached; tests clear it with cache_clear().

    Raises FileNotFoundError mentioning download_public_data.py if the file is
    missing, and ValueError (naming the file) if it exists but cannot be read,
    so a corrupt download is not reported as a missing one.
    """

    if source_list not in _SOURCE_FILES:
        raise FileNotFoundError(
            f"Unknown sanctions list {source_list!r}; expected one of {sorted(_SOURCE_FILES)}. "
            "Run download_public_data.py to import data."
        )
    path = _SOURCE_FILES[source_list]
    try:
        df = pd.read_csv(path, dtype=str).fillna("")
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Sanctions data file {path} is not present. Run download_public_data.py to get the data."
        ) from exc
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        raise ValueError(f"Could not read sanctions data file {path}: {exc}") from exc

    names: list[str] = []
    rows: list[int] = []
    aliases = df["aliases"] if "aliases" in df.columns else [""] * len(df)
    for row_idx, (primary, alias_field) in enumerate(zip(df["name"], aliases, strict=True)):
        names.append(primary)
        rows.append(row_idx)
        for alias in _ALIAS_SEPARATORS.split(alias_field):
            if alias.strip():
                names.append(alias.strip())
                rows.append(row_idx)
    df.attrs["names"], df.attrs["rows"] = names, rows
    return df


def _row_to_match(row: pd.Series, source_list: str, score: float, matched_alias: str | None = None) -> EntityMatch:
    name = row["name"]
    return EntityMatch(
        matched_name=f"{name} (alias: {matched_alias})" if matched_alias else name,
        source_list=source_list,
        source_id=row["id"],
        match_score=score,
        program=row["program_ids"],
        country=row["countries"],
    )


def lookup(
    name: str,
    *,
    source_lists: tuple[str, ...] = ("us_ofac_sdn", "gb_hmt_sanctions"),
    top_k: int = config.ENTITY_MATCH_TOP_K,
    min_score: float = config.ENTITY_MATCH_MIN_SCORE,
) -> list[EntityMatch]:
    """Fuzzy-match `name` against the names and aliases on every list in
    `source_lists`; keep entries scoring >= min_score (one result per entry,
    its best-scoring name) and return the top_k across all lists, best first.

    Matching ignores case, punctuation and extra whitespace (rapidfuzz's
    default_process). Without that, "Eliav Libi" scores 70 against "ELIAV
    LIBI", under the threshold, although the lists are often upper-case.
    """

    all_matches: list[EntityMatch] = []
    for source_list in source_lists:
        df = _load_list(source_list)
        names, rows = df.attrs["names"], df.attrs["rows"]
        best: dict[int, tuple[float, int]] = {}  # row index -> (score, index into names)
        for _, score, choice_idx in process.extract(
            name, names, scorer=fuzz.WRatio, processor=utils.default_process, limit=None, score_cutoff=min_score
        ):
            row_idx = rows[choice_idx]
            if row_idx not in best or score > best[row_idx][0]:
                best[row_idx] = (float(score), choice_idx)
        for row_idx, (score, choice_idx) in best.items():
            row = df.iloc[row_idx]
            matched = names[choice_idx]
            all_matches.append(_row_to_match(row, source_list, score, None if matched == row["name"] else matched))

    all_matches.sort(key=lambda m: m.match_score, reverse=True)
    return all_matches[:top_k]
