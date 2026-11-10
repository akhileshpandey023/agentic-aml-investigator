"""Search the local FCA-notices corpus as an adverse-media stand-in.

PLACEHOLDER — see PROJECT_PLAN.md Phase 4, section "adverse_media_search.py".

To later swap in live web search instead of the static corpus: implement a
second function with the same return type (list[AdverseMediaHit]) and change
the import in aml_agents/nodes/adverse_media.py. Nothing else needs to
change, because the node only depends on the return type.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from aml_agents import config
from aml_agents.schemas import AdverseMediaHit

_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")

# Words that say what kind of party a name is rather than which one. A notice
# that merely contains "bank" or "ltd" is not about this entity, so they do not
# count towards whether the entity's name appears (see _name_tokens).
_GENERIC_TOKENS = frozenset(
    "the of and for ltd limited llc llp lp inc plc co corp corporation company group holdings holding "
    "bank trading services international sa ag gmbh bv nv".split()
)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _name_tokens(name: str) -> list[str]:
    """The distinctive tokens of an entity name (all of them if it has none)."""

    tokens = _tokenize(name)
    return [t for t in tokens if t not in _GENERIC_TOKENS] or tokens


@functools.lru_cache(maxsize=1)
def _load_corpus() -> tuple[list[str], list[str], BM25Okapi]:
    """Load every .txt file under config.FCA_NOTICES_DIR and build a BM25Okapi
    index over their tokenized text. Returns (filenames, raw_texts, bm25).
    Raises FileNotFoundError if the directory has no .txt files yet (see
    data/README.md section 2: populating it is a manual step).
    """

    list_text_files = sorted(Path(config.FCA_NOTICES_DIR).rglob("*.txt"))
    if not list_text_files:
        raise FileNotFoundError(
            f"No text files found at {config.FCA_NOTICES_DIR}. See data/README.md section 2 "
            "for how to populate the adverse-media corpus."
        )

    filenames, texts = [], []
    for f in list_text_files:
        filenames.append(str(f.relative_to(config.FCA_NOTICES_DIR)))
        texts.append(f.read_text(encoding="utf-8"))
    return filenames, texts, BM25Okapi([_tokenize(t) for t in texts])


def search(entity_name: str, *, top_k: int = config.ADVERSE_MEDIA_TOP_K) -> list[AdverseMediaHit]:
    """BM25-search the corpus for `entity_name`; up to top_k hits, best first.

    A notice is a hit only if it contains at least
    config.ADVERSE_MEDIA_MIN_TOKEN_COVERAGE of the name's distinctive tokens.
    BM25 alone would rank "Marta Smith ... compliance officer" first for the
    query "Marta Ellison", and because scores are normalised to the best
    document that notice would always score 1.0 and pass any relevance gate.
    relevance_score is the BM25 score divided by the best qualifying notice's.
    """

    query_tokens = _tokenize(entity_name)
    if not query_tokens:
        return []
    filenames, texts, bm25 = _load_corpus()
    scores = bm25.get_scores(query_tokens)
    required = _name_tokens(entity_name)

    qualifying: list[tuple[int, float]] = []
    for idx, score in enumerate(scores):
        present = set(_tokenize(texts[idx]))
        if sum(tok in present for tok in required) / len(required) >= config.ADVERSE_MEDIA_MIN_TOKEN_COVERAGE:
            qualifying.append((idx, float(score)))
    if not qualifying:
        return []

    # Ranking only: coverage decides relevance. BM25's IDF is zero or negative
    # for a term in half or more of the documents, so on a small corpus a
    # genuine hit can have a score of 0 and must not be dropped for it.
    qualifying.sort(key=lambda pair: pair[1], reverse=True)
    best_score = qualifying[0][1]
    return [
        AdverseMediaHit(
            title=filenames[idx],
            source=filenames[idx],
            snippet=_best_snippet(text=texts[idx], query=entity_name),
            published_date=None,
            relevance_score=max(0.0, score / best_score) if best_score > 0 else 1.0,
        )
        for idx, score in qualifying[:top_k]
    ]


def _best_snippet(text: str, query: str, window: int = 300) -> str:
    """A ~`window`-char excerpt centred on the first occurrence of the whole
    name, else of its longest distinctive token (case-insensitive), else the
    first `window` characters."""

    if not text or not query or not query.strip():
        return ""
    lowered, phrase = text.lower(), query.strip().lower()
    needle = phrase if phrase in lowered else next(
        (tok for tok in sorted(_name_tokens(query), key=len, reverse=True) if tok in lowered), None
    )
    if needle is None:
        return text[:window].strip()

    middle = lowered.find(needle) + len(needle) // 2
    start = max(0, middle - window // 2)
    end = min(len(text), start + window)
    start = max(0, end - window)
    return text[start:end].strip()
