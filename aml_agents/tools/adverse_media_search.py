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


def _tokenize(text: str) -> list[str]:

    return [t.lower() for t in _TOKEN_RE.findall(text)]  
config.FCA_NOTICES_DIR

@functools.lru_cache(maxsize=1)
def _load_corpus() -> tuple[list[str], list[str], BM25Okapi]:
    """TODO (PROJECT_PLAN.md Phase 4): load every .txt file from
    config.FCA_NOTICES_DIR, build a BM25Okapi index over their tokenized
    text, and return (filenames, raw_texts, bm25_index). Raise
    FileNotFoundError with a clear message if the directory has no .txt
    files yet (see data/README.md section 2 for why this is a manual step).
    """
    list_text_files = [Path(path) for path in Path(config.FCA_NOTICES_DIR).rglob("*.txt")]

    if len(list_text_files)==0:
        raise FileNotFoundError(f'''No text files found at {config.FCA_NOTICES_DIR}. 
        Please refer to data/README.md section 2 and run scripts/ingest_guidance.py''')

    filenames, texts = [], []
    for f in list_text_files:
        with open(f, "r", encoding="utf-8") as file:
            content = file.read()
            filenames.append(str(f.relative_to(config.FCA_NOTICES_DIR)))
            texts.append(content)
            
    return (filenames, texts, BM25Okapi([_tokenize(t) for t in texts]))


def search(entity_name: str, *, top_k: int = config.ADVERSE_MEDIA_TOP_K) -> list[AdverseMediaHit]:
    """TODO (PROJECT_PLAN.md Phase 4): BM25-search the corpus for
    `entity_name`, return up to top_k hits with relevance_score normalised
    to 0-1 (divide by the top score in the batch), skipping zero-score hits.
    """
    filenames, text, bm25= _load_corpus()

    bm25_scores = bm25.get_scores(_tokenize(entity_name))
    
    if max(bm25_scores) <= 0:
        return []
    
    bm25_scores_norm = [score / max(bm25_scores) for score in bm25_scores]

    filtered_pairs = [(idx, score) for idx, score in enumerate(bm25_scores_norm) if score >= 0]
    sorted_pairs = sorted(filtered_pairs, key=lambda item: item[1], reverse=True)
    final_indices = [idx for idx, _ in sorted_pairs[:top_k]]

    if len(final_indices) == 0:
        return []
    else:
        return [
            AdverseMediaHit(title=filenames[idx], source=filenames[idx], snippet=_best_snippet(text=text[idx], query=entity_name), 
                            published_date=None, relevance_score=bm25_scores_norm[idx]) for idx in final_indices
                            ] 


def _best_snippet(text: str, query: str, window: int = 300) -> str:
    # TODO: return a ~`window`-char excerpt of `text` centred on the first
    # occurrence of query's first word (case-insensitive), falling back to
    # the first `window` characters if the word isn't found.
    if not text:
        return ""
    if not query or not query.strip():
        return ""
    
    match_index = text.lower().find(query.strip().lower())

    if match_index != -1:
        # Center the window around the middle of the matched phrase
        phrase_middle = match_index + (len(query.strip().lower()) // 2)
        
        half_window = window // 2
        start = max(0, phrase_middle - half_window)
        end = start + window
        
        if end > len(text):
            end = len(text)
            start = max(0, end - window)
            
        return text[start:end].strip()
    else:
        return text[:window].strip()
