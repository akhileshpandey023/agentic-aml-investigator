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
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

from aml_agents import config
from aml_agents.schemas import EntityMatch

_SOURCE_FILES: dict[str, Path] = {
    "us_ofac_sdn": config.SANCTIONS_DIR / "us_ofac_sdn.csv",
    "gb_hmt_sanctions": config.SANCTIONS_DIR / "gb_hmt_sanctions.csv",
}


@functools.lru_cache(maxsize=None)
def _load_list(source_list: str) -> pd.DataFrame:
    # TODO (PROJECT_PLAN.md Phase 2): load _SOURCE_FILES[source_list] with
    # pandas, fillna(""), and return the DataFrame. Raise FileNotFoundError
    # with a message mentioning "download_public_data.py" if the file isn't
    # there yet — tests/test_sanctions_lookup.py::test_missing_file_raises_clear_error
    # checks for that exact phrase. 
    if source_list not in _SOURCE_FILES.keys():
        raise FileNotFoundError(f"Incorrect input or no list with the name {source_list}. Run download_public_data.py to import data.")

    try:
        source_dataframe = pd.read_csv(_SOURCE_FILES[source_list]).fillna('')
    except Exception as e:
        raise FileNotFoundError(f"The sanction data file file is not preent in the directory. Run download_public_data.py to get the data.")
    return source_dataframe


def _row_to_match(row: pd.Series, source_list: str, score: float) -> EntityMatch:
    # TODO: map a DataFrame row + its source_list + its fuzzy-match score
    # into an EntityMatch. See the EntityMatch fields in schemas.py for what
    # each OpenSanctions CSV column should map to.
    return EntityMatch(matched_name=row['name'],
                       source_list=source_list,
                       source_id=row['id'],
                       match_score=score,
                       program=row['program_ids'],
                       country=row['countries'])


def lookup(
    name: str,
    *,
    source_lists: tuple[str, ...] = ("us_ofac_sdn", "gb_hmt_sanctions"),
    top_k: int = config.ENTITY_MATCH_TOP_K,
    min_score: float = config.ENTITY_MATCH_MIN_SCORE,
) -> list[EntityMatch]:
    """TODO (PROJECT_PLAN.md Phase 2): fuzzy-match `name` against every list
    in `source_lists`, filter to matches scoring >= min_score, and return
    the top_k across all lists combined, sorted by score descending.
    """
    all_matches: list[EntityMatch] = []
    for source_list in source_lists:
        df = _load_list(source_list)
        choices = df["name"].tolist()
        results = process.extract(query=name, choices=choices, scorer=fuzz.WRatio, limit=top_k)
        for _ , score, idx in results:
            if score < min_score:
                continue
            all_matches.append(_row_to_match(df.iloc[idx], source_list, float(score)))

    all_matches.sort(key=lambda m: m.match_score, reverse=True)
    return all_matches[:top_k]