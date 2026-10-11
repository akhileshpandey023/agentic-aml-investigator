# Project Plan

This document is the single source of truth for what every placeholder in
this repo needs to do. Code files point here rather than repeating the
spec, so there's exactly one place a requirement can drift out of date.

## How to use this document

Work phase by phase, in order — later phases assume earlier contracts are
stable and earlier files are working. For each phase:

1. Read the "Requirements" section for every file touched in that phase.
2. Implement it.
3. Run the **acceptance criteria** given for that phase. Where a test file
   exists, your goal is to make it pass *without editing the test* — the
   tests encode the contract, not suggestions.
4. Only then move on.

Everything in `aml_agents/` is a placeholder (`raise NotImplementedError`)
except `schemas.py` and `config.py`, which are given contracts — read them
once, carefully, before Phase 2; nearly everything below is specified in
terms of their exact field and constant names. `tests/` is also given —
it's your acceptance criteria, not something to edit to make pass.

Rough pacing is a guide, not a deadline.

---

## Phase 0 — Environment and public data (~0.5 day)

**Build:**
```bash
uv sync
cp .env.example .env
python scripts/download_public_data.py --all
```
Then manually save a handful of FCA Final Notices and the JMLSG/FATF/FCA
guidance documents — see `data/README.md` for exact sources and why these
two aren't bulk-downloadable the way the sanctions lists are.

`scripts/download_public_data.py` and `scripts/ingest_guidance.py` are
given — they're HTTP/PDF plumbing, not agent logic.

**Learning objective:** an agentic system is only as good as the tools and
data under it. Before writing a single agent, you need working, inspectable
ground truth to test against.

**Acceptance criteria:** `data/raw/sanctions/*.csv` exist and are non-empty;
`uv run pytest tests/test_schemas.py -q` passes (sanity-checks your
environment, independent of any data).

---

## Phase 1 — Contracts (read-only, ~0.5 day)

**Build:** nothing — read `aml_agents/schemas.py` end to end. Note:
- Every agent's output is a Pydantic model (`EntityMatch`, `AdverseMediaHit`,
  `RetrievedPassage`, `InvestigationPlan`, `RiskMemo`, `CriticReview`,
  `HumanDecision`, `AgentTrace`).
- `CaseState` is the single TypedDict every node reads/writes. Its
  docstring lists field ownership — which node is expected to set each
  field. Memorise this table; almost every "which node writes what" question
  below is answered by it.
- `trace` is the one field that *accumulates* (`Annotated[..., operator.add]`)
  rather than being overwritten — every node you write ends with
  `**make_trace(...)` merged into its return dict.
- `new_case_state()` and `make_trace()` are given helpers you'll use in
  nearly every node.

**Learning objective:** the single biggest source of "my multi-agent system
is flaky" is un-typed handoffs between agents. A stable, given contract
up front is what keeps everything you write below from contradicting itself.

**Acceptance criteria:** `uv run pytest tests/test_schemas.py -q` passes
(it already does — this just confirms you can run pytest at all).

---

## Phase 2 — Entity Resolution agent (~1–1.5 days)

### Requirements: `aml_agents/tools/sanctions_lookup.py`

**`_load_list(source_list: str) -> pd.DataFrame`** (cached via `@lru_cache`,
given decorator — keep it)
- R1: Look up the CSV path for `source_list` in `_SOURCE_FILES`.
- R2: If the file doesn't exist, raise `FileNotFoundError` whose message
  mentions `download_public_data.py` (the test asserts on this substring —
  it's not optional phrasing).
- R3: Otherwise `pd.read_csv(path, dtype=str).fillna("")` and return it.

**`_row_to_match(row, source_list, score) -> EntityMatch`**
- R1: Map OpenSanctions CSV columns to `EntityMatch` fields: `name` ->
  `matched_name`, `id` -> `source_id`, `topics` (fall back to `dataset` if
  absent) -> `program`, `countries` -> `country`.
- R2: `source_list` and `score` (the fuzzy match score) pass through directly.

**`lookup(name, *, source_lists=(...), top_k=..., min_score=...) -> list[EntityMatch]`**
- R1: For each list in `source_lists`, load it via `_load_list`, and fuzzy-match
  `name` against the `name` column using `rapidfuzz.process.extract` with
  `scorer=fuzz.WRatio` and `limit=top_k`.
- R2: Keep only matches scoring `>= min_score`.
- R3: Combine matches across all source lists, sort by score descending,
  truncate to `top_k`.
- **Edge case:** a name with no matches above `min_score` in any list
  returns `[]`, not an error.
- **Edge case:** `rapidfuzz.WRatio` handles partial/reordered tokens
  reasonably (e.g. "Vostok Trading" vs "Trading, Vostok LLC") — don't
  pre-normalise the name yourself beyond what the library already does, or
  you'll fight it. Transliteration/diacritic normalisation is explicitly
  out of scope for this phase (see Phase 13 stretch).

### Requirements: `aml_agents/nodes/entity_resolution.py`

**`entity_resolution_node(state: CaseState) -> dict`**
- R1: Call `sanctions_lookup.lookup(state["entity_name"])`.
- R2: Set `entity_resolved = True` iff **any** candidate scores
  `>= config.ENTITY_MATCH_MIN_SCORE` — note `lookup()` already filters by
  its own `min_score` default, so in practice this means "iff candidates is
  non-empty", but write the explicit check rather than relying on that
  coincidence (it stops being true if you ever call `lookup` with a looser
  `min_score` from this node).
- R3: Time the call (`time.perf_counter()` before/after) and pass the
  duration to `make_trace(..., duration_ms=...)`.
- R4: `summary_out` should include the candidate count and, if any, the top
  match's name and score — this is what you'll be reading in `main.py`'s
  trace printout when the downstream phases aren't done yet.
- R5: Return `{"entity_candidates": ..., "entity_resolved": ..., **make_trace(...)}`.

**Acceptance criteria:** `uv run pytest tests/test_sanctions_lookup.py -q`
passes all 4 tests. (There's no test file for `entity_resolution_node`
itself — verify it manually: `new_case_state("Vostok Trading LLC")` through
the node should produce a non-empty `entity_candidates` and
`entity_resolved=True` once Phase 0's data is downloaded.)

---

## Phase 3 — Retrieval (RAG) agent (~1.5–2 days)

This is the same Chroma + BM25 + cross-encoder-rerank pattern you've built
before. Reapply it; the new part is where it sits in a larger system
(Phase 9), not the technique itself.

### Requirements: `aml_agents/tools/vector_store.py`

**`_chunk(text, chunk_size=800, overlap=120) -> list[str]`**
- R1: Fixed-size sliding-window chunking: `start=0`; while `start < len(text)`,
  take `text[start:start+chunk_size]`, then `start = start + chunk_size - overlap`.
- R2: Strip each chunk and drop empty ones.

**`VectorStore.__init__(persist_dir=..., collection_name="regulatory_guidance")`**
- R1: `chromadb.PersistentClient(path=str(persist_dir))`, then
  `get_or_create_collection(collection_name)`.
- R2: Initialise instance attributes for a lazily-loaded cross-encoder
  (`None` until first used — loading it eagerly slows down every import),
  and a BM25 index + its backing doc list (also `None`/`[]` until ingestion).

**`VectorStore.ingest_dir(guidance_dir=config.GUIDANCE_DIR) -> int`**
- R1: `guidance_dir.rglob("*.txt")`, **not** `glob` — guidance text is organised
  into regulator subdirectories (`guidance/fatf/`, `guidance/fca/`,
  `guidance/jmlsg/`, ...; see `data/README.md`), and `scripts/ingest_guidance.py`
  writes each extracted `.txt` next to its source `.pdf`, so a flat `glob`
  silently indexes nothing from any subdirectory. Raise `FileNotFoundError`
  if the recursive search still finds none.
- R2: Chunk each file via `_chunk`, building parallel `ids` (uuid4 per chunk),
  `docs` (chunk text), `metadatas` (`{"source_document": str(path.relative_to(guidance_dir))}`
  — the path *relative to guidance_dir*, e.g. `"fatf/40_recommendations.txt"`,
  not just the bare filename: two regulators can plausibly use the same
  filename, and the regulator name is itself useful context on a citation in
  the Risk Analyst's memo).
- R3: `self._collection.upsert(ids=ids, documents=docs, metadatas=metadatas)`.
- R4: Call `self._rebuild_bm25(ids, docs, metadatas)`.
- R5: Return the chunk count.
- **Edge case:** re-running `ingest_dir` after adding more files
  re-embeds everything (acceptable for a handful of practice documents —
  don't over-engineer incremental indexing here).

**`VectorStore._rebuild_bm25(ids, docs, metadatas)`**
- R1: Store `[{"id", "text", "source_document"} for each doc]` on `self`.
- R2: Build `BM25Okapi([_tokenize(d["text"]) for d in those docs])` and
  store it on `self`.

**`VectorStore.query(text, top_k=config.RETRIEVAL_TOP_K) -> list[RetrievedPassage]`**
- R1: `dense = self._dense_search(text, top_k)`.
- R2: `sparse = self._sparse_search(text, top_k)`.
- R3: `fused = self._reciprocal_rank_fusion(dense, sparse)`.
- R4: `reranked = self._rerank(text, fused)`.
- R5: Return `reranked[:config.RETRIEVAL_RERANK_TOP_K]`.

**`VectorStore._dense_search(text, top_k) -> list[dict]`**
- R1: `self._collection.query(query_texts=[text], n_results=top_k)` — the
  response carries parallel `ids`, `documents`, and `metadatas` lists
  (each nested one level, e.g. `res["ids"][0]`). Zip the three and map each
  result to `{"id": id_, "text": doc, "source_document": meta["source_document"]}`
  — the **same three keys** `_sparse_search` returns (see its R1 below),
  deliberately: `_reciprocal_rank_fusion` needs a real identity key (`id`),
  not just `text`, to fuse correctly (see the note on R1 there).

**`VectorStore._sparse_search(text, top_k) -> list[dict]`**
- R1: If no BM25 index yet (nothing ingested), return `[]`.
- R2: `self._bm25.get_scores(_tokenize(text))`, take the `top_k` highest-scoring
  indices, return the corresponding stored docs — already
  `{"id", "text", "source_document"}` dicts, from `_rebuild_bm25`.

**`VectorStore._reciprocal_rank_fusion(dense, sparse, k=60) -> list[dict]`** (`@staticmethod`)
- R1: Standard RRF: for each list, for each item at `rank` (0-indexed), add
  `1 / (k + rank + 1)` to a running score keyed by the item's `id`, **not**
  `text`. Regulatory PDFs routinely repeat boilerplate (disclaimers, section
  headers) across *different* source documents — with 800-char chunks, two
  genuinely distinct chunks from two different regulators can end up with
  identical text. Keying on `text` would silently collapse them into one
  fused entry and keep only one `source_document`, corrupting a citation
  without raising anything. `id` is assigned once per chunk at ingest and
  can't collide this way.
- R2: Return items sorted by combined score descending, deduplicated by `id`
  (one dict per unique `id` — `text`/`source_document` along for the ride).

**`VectorStore._rerank(query, candidates) -> list[RetrievedPassage]`**
- R1: Lazily construct `CrossEncoder(config.CROSS_ENCODER_MODEL)` on first
  call, cache on `self`.
- R2: Score every `(query, candidate_text)` pair, sort descending, map to
  `RetrievedPassage(text=..., source_document=..., score=...)`.
- **Edge case:** empty `candidates` returns `[]` without touching the model.

### Requirements: `aml_agents/nodes/retrieval.py`

**`_build_query(state: CaseState) -> str`**
- R1: Base string: a general statement of what's being looked for —
  "customer due diligence and sanctions screening obligations".
- R2: If `state["entity_candidates"]` has any entries with a non-null
  `program`, append a clause naming the distinct programmes.
- R3: If `state["adverse_media_findings"]` is non-empty, append a clause
  about obligations when adverse media is identified.
- This is deliberately simple (string concatenation) — a smarter version
  using an LLM-drafted query (query transformation, which you've used
  before as RAG-Fusion) is a reasonable thing to try once this works, but
  isn't required.

**`retrieval_node(state: CaseState) -> dict`**
- R1: Build the query via `_build_query`.
- R2: Call a **module-level singleton** `VectorStore` instance's `.query()`
  — construct it once (lazy global, same pattern as the cross-encoder
  inside `VectorStore` itself) rather than on every node call, since
  constructing a `VectorStore` opens a Chroma client.
- R3: Catch `FileNotFoundError` (no guidance ingested yet) and degrade to
  `passages = []` rather than crashing the graph run.
- R4: Return `{"regulatory_context": passages, **make_trace(...)}`.

**Acceptance criteria:** no automated test file for this phase (retrieval
quality is judged by reading results, not asserted exactly) — manually
verify: after `scripts/ingest_guidance.py` succeeds,
`VectorStore().query("customer due diligence")` returns up to
`config.RETRIEVAL_RERANK_TOP_K` passages with plausible `source_document`
values and descending `score`.

---

## Phase 4 — Adverse Media agent (~1 day)

### Requirements: `aml_agents/tools/adverse_media_search.py`

**`_tokenize(text) -> list[str]`**
- R1: `[t.lower() for t in _TOKEN_RE.findall(text)]`.

**`_load_corpus() -> tuple[list[str], list[str], BM25Okapi]`** (cached via
`@lru_cache(maxsize=1)`, given decorator — keep it)
- R1: Glob `*.txt` in `config.FCA_NOTICES_DIR`; raise `FileNotFoundError`
  with a message pointing at `data/README.md` section 2 if none found.
- R2: Read each file's text; return `(filenames, texts, BM25Okapi([_tokenize(t) for t in texts]))`.

**`search(entity_name, *, top_k=config.ADVERSE_MEDIA_TOP_K) -> list[AdverseMediaHit]`**
- R1: `filenames, texts, bm25 = _load_corpus()`.
- R2: `scores = bm25.get_scores(_tokenize(entity_name))`; take the `top_k`
  highest-scoring indices (skip any with score `<= 0` — BM25 returns 0 for
  no token overlap at all, which isn't a real hit).
- R3: Normalise `relevance_score` to `0-1` by dividing by the batch's max
  score.
- R4: Build each `AdverseMediaHit` with `title=filename`, `source=filename`,
  `snippet=_best_snippet(text, entity_name)`, `published_date=None` (not
  derivable from plain text without more structure — leave it `None`, a
  reasonable extension is parsing it from a filename convention you adopt).

**`_best_snippet(text, query, window=300) -> str`**
- R1: Find the first occurrence (case-insensitive) of `query`'s first
  whitespace-split word in `text`.
- R2: If found, return `window` characters centred on that position
  (stripped); if not found, return the first `window` characters.

### Requirements: `aml_agents/nodes/adverse_media.py`

**`adverse_media_node(state: CaseState) -> dict`**
- R1: Call `adverse_media_search.search(state["entity_name"])`, catching
  `FileNotFoundError` (corpus not populated yet) and degrading to `hits = []`.
- R2: Apply a relevance gate: keep only hits with `relevance_score >= 0.15`.
  This threshold is a cheap heuristic, not a considered judgment — flag in
  your own notes (or just leave a comment) that an LLM-based relevance
  check (does this hit actually concern the *same* entity, not a namesake?)
  is a stronger version of this step; implementing that upgrade is optional
  and listed in Phase 13.
- R3: Return `{"adverse_media_findings": filtered, **make_trace(...)}`,
  with `summary_out` noting `kept/total` hits.

**Acceptance criteria:** no automated test file — manually verify against
your FCA-notices corpus: a name that appears in one of your saved notices
produces at least one hit; an unrelated name produces none.

---

## Phase 5 — LLM Client (~0.5–1 day)

Needed before Phase 7 (Risk Analyst) can do anything.

### Requirements: `aml_agents/llm_client.py`

**`AnthropicLLMClient.__init__(self, api_key, model)`**
- R1: If `api_key` is falsy, raise `ValueError` with a message pointing at
  `.env.example`/`ANTHROPIC_API_KEY` — this must raise even with no network
  access, since `tests/test_llm_client.py::test_anthropic_client_rejects_empty_api_key`
  checks exactly that.
- R2: Lazily `import anthropic` inside the method (not at module level) so
  the package is only required when this backend is actually selected.
- R3: Construct `anthropic.Anthropic(api_key=api_key)`, store it and `model`
  on `self`.

**`AnthropicLLMClient.complete(self, system, user, *, max_tokens=1024, temperature=0.0) -> LLMResponse`**
- R1: Call `self._client.messages.create(model=self._model, max_tokens=max_tokens,
  temperature=temperature, system=system, messages=[{"role": "user", "content": user}])`.
- R2: Concatenate the `text` of every content block with `type == "text"`
  in the response.
- R3: Return `LLMResponse(text=..., input_tokens=resp.usage.input_tokens,
  output_tokens=resp.usage.output_tokens)`.

**`LocalOpenAICompatLLMClient.__init__(self, base_url, model)`**
- R1: If `model` is falsy, raise `ValueError` — again, must raise without
  needing a running server (`test_local_client_rejects_empty_model` checks
  this).
- R2: Store `base_url.rstrip("/")` and `model` on `self`.

**`LocalOpenAICompatLLMClient.complete(...)`**
- R1: `POST {base_url}/chat/completions` with a standard OpenAI chat
  payload: `{"model": ..., "max_tokens": ..., "temperature": ..., "messages": [
  {"role": "system", "content": system}, {"role": "user", "content": user}]}`.
- R2: Parse `data["choices"][0]["message"]["content"]` as the text, and
  `data.get("usage", {})` for token counts (`prompt_tokens`/`completion_tokens`
  — note these are *different key names* than the Anthropic response).

**Acceptance criteria:** `uv run pytest tests/test_llm_client.py -q` passes
all 3 tests. (Actually calling a real backend needs a live `ANTHROPIC_API_KEY`
or a running local server — test that manually with
`get_llm_client().complete(system="You are terse.", user="Say hi in 3 words.")`.)

---

## Phase 6 — Planner agent (~0.5–1 day)

### Requirements: `aml_agents/nodes/planner.py`

**`build_static_plan(state: CaseState) -> InvestigationPlan`**
- R1: Always `steps=["entity_resolution", "adverse_media", "retrieval", "risk_analyst"]`.
- R2: A short `rationale` string explaining this is the standard full
  investigation sequence.
- Note: this can't actually branch on `entity_candidates` — the planner
  runs *first*, before entity resolution has populated anything. If you
  want a plan that skips steps conditionally, that logic belongs in the
  router (Phase 9), not here — keep this node's one job being "record a plan",
  not "decide live routing."

**`planner_node(state: CaseState) -> dict`**
- R1: Call `build_static_plan`, time it, return
  `{"plan": ..., **make_trace(...)}` with `summary_out` listing the steps.

`build_dynamic_plan` is Phase 13 (stretch) — leave it raising
`NotImplementedError`; it's not called by `planner_node` by default.

**Acceptance criteria:** no automated test — manually verify
`planner_node(new_case_state("X"))` returns a dict with a `plan` whose
`.steps` is the fixed 4-item list.

---

## Phase 7 — Risk Analyst agent (~1.5–2 days)

The first real reasoning agent. This is the exercise worth spending the
most deliberate time on.

### Requirements: `aml_agents/nodes/risk_analyst.py`

**`_format_evidence(state: CaseState) -> str`**
- R1: Render `state["entity_name"]`, then a labelled section per evidence
  type: sanctions candidates (id, name, source list, score, programme),
  adverse media hits (source, title, snippet), regulatory context (source
  document, text excerpt).
- R2: Each section must explicitly say "(none)" / "(none found)" when
  empty — an empty section silently omitted reads to the model as "not
  checked", not "checked and clear", which is a meaningfully different and
  wrong signal for a risk memo to carry.
- R3: If `state["critic_feedback"]` is present, append a clearly-labelled
  "PRIOR CRITIC FEEDBACK TO ADDRESS" section listing `issues` — this is
  what turns a second risk_analyst call into a *revision* rather than a
  fresh, context-free draft.

**`_parse_risk_memo(raw_text, entity_name) -> RiskMemo`**
- R1: `json.loads(raw_text)` (let `JSONDecodeError` propagate).
- R2: `payload.setdefault("entity_name", entity_name)`.
- R3: `RiskMemo.model_validate(payload)` (let `ValidationError` propagate).

**`risk_analyst_node(state: CaseState) -> dict`**
- R1: Build evidence via `_format_evidence`.
- R2: Write a system prompt. It must, at minimum:
  - State the task: produce a `RiskMemo` for the given entity.
  - Make the evidence block the **only** allowed source of fact — no
    outside knowledge, no assumptions about "typical" cases.
  - Require every factual sentence in `narrative` to be traceable to
    `citations`, and require `citations` to reference real evidence
    identifiers (an `EntityMatch.source_id`, an `AdverseMediaHit.source`,
    or a `RetrievedPassage.source_document`) — not vague phrases like
    "public records".
  - Define your own `risk_score -> risk_level -> recommended_action` bands
    explicitly (e.g. what score range means `clear` vs `escalate` vs
    `file_sar`) — don't leave the model to invent its own thresholds
    inconsistently case to case. **Write this policy down somewhere you can
    paste verbatim into the Critic's prompt in Phase 8** — the two prompts
    silently drifting apart (analyst and critic disagreeing about what
    counts as "high risk") is a realistic bug worth avoiding by
    construction, not by hoping you remember.
  - If `critic_feedback` is in the evidence block, instruct the model this
    is a revision: address the specific issues, don't regenerate from
    scratch.
  - Require output as a single JSON object matching `RiskMemo`'s fields,
    nothing else (no prose before/after).
- R3: Call `get_llm_client().complete(system=..., user=evidence)`.
- R4: Parse via `_parse_risk_memo`; on `JSONDecodeError`/`ValidationError`,
  consider one retry with the error message appended to the prompt asking
  the model to fix its JSON (LLM JSON output isn't always perfectly
  well-formed on the first try — a bare retry loop here is reasonable and
  common, just bound it to one retry, not unbounded).
- R5: **Revision-count bookkeeping (this node owns it):** `is_revision =
  state.get("critic_feedback") is not None`; `revision_count =
  state.get("revision_count", 0) + (1 if is_revision else 0)`. See
  ARCHITECTURE.md design principle 3 for why this node (not the critic, not
  the router) owns this counter — "a revision IS another risk_analyst run."
- R6: Return `{"risk_memo": memo, "revision_count": revision_count, **make_trace(...)}`.

**Acceptance criteria:** no automated test (requires a live LLM call) —
manually verify: run the node against a `CaseState` with a clear sanctions
hit and confirm `risk_score`/`recommended_action` are internally consistent
with your own stated bands, and every `citations` entry actually matches
something in the evidence you passed in.

---

## Phase 8 — Critic agent (~1–1.5 days)

The evaluator half of the reflection loop.

### Requirements: `aml_agents/nodes/critic.py`

**`_format_review_context(state: CaseState) -> str`**
- R1: Include the memo under review (`json.dumps(state["risk_memo"].model_dump(), indent=2)`,
  or "(no memo produced)" if absent).
- R2: Include the **same** evidence lists `risk_analyst` saw (sanctions
  candidates, adverse media, regulatory context) — just identifiers/titles
  are enough here (the critic needs to check "does this citation exist",
  not re-read full passage text).

**`_parse_critic_review(raw_text) -> CriticReview`**
- R1: `json.loads` + `CriticReview.model_validate`.

**`critic_node(state: CaseState) -> dict`**
- R1: Build context via `_format_review_context`.
- R2: Write a system prompt that checks **two distinct things** — be
  explicit about both in the prompt, not just "review this memo":
  1. **Groundedness** — does every claim in `narrative` trace back to the
     evidence? Does every entry in `citations` correspond to something that
     actually exists in the evidence block (not a fabricated source)? This
     is the single highest-value check a critic can do, and it's
     mechanically checkable by the model if you ask for it explicitly.
  2. **Internal consistency** — does `recommended_action` follow from
     `risk_score` under the **same bands you wrote into the risk_analyst
     prompt in Phase 7**? Paste that policy text into this prompt verbatim.
  Also require: `issues` entries must be specific and actionable ("the
  narrative claims a Russia-programme match but no candidate in the
  evidence has a Russia-related programme" — not "seems inaccurate"); a
  `confidence` (0-1) reflecting the critic's own certainty; JSON output
  matching `CriticReview`, nothing else.
- R3: Call the LLM, parse via `_parse_critic_review`.
- R4: Return `{"critic_feedback": review, **make_trace(...)}`.
- Note: this node does **not** touch `revision_count` — see the ownership
  note in the file's docstring and ARCHITECTURE.md design principle 3.

**Acceptance criteria:** no automated test (requires a live LLM call) —
build yourself one deliberately-broken `RiskMemo` (e.g. a `citations` entry
that doesn't match any evidence item) and confirm the critic's `verdict` is
`"revise"` and `issues` names the fabricated citation specifically. Keep
this broken example — you'll reuse it in Phase 11's `critic_catch_rate`.

---

## Phase 9 — Graph wiring: Router, Human Gate, full `graph.py` (~1–1.5 days)

### Requirements: `aml_agents/nodes/human_gate.py`

**`human_gate_node(state: CaseState) -> dict`**
- R1: Read `state["human_decision"]`. If `None`, raise `RuntimeError` — by
  the time this node runs (after the interrupt/resume described below),
  it should already be populated; a `None` here means the graph's
  interrupt wiring is wrong, and that should fail loudly, not silently.
- R2: If `state["risk_memo"]` exists: on `decision.decision ==
  "override_clear"`, `memo.model_copy(update={"recommended_action": "clear"})`;
  on `"override_escalate"`, same with `"escalate"`; on `"confirm"`, leave
  the memo as-is.
- R3: Return `{"risk_memo": updated_memo, "human_review_required": True, **make_trace(...)}`.
  Setting `human_review_required = True` here (not anywhere else) is
  deliberate — reaching this node at all **is** the definition of "review
  was required"; a case the router sent straight to `END` keeps the
  `False` default from `new_case_state`.

### Requirements: `aml_agents/graph.py`

**`route_after_critic(state: CaseState) -> str`** — a pure function of
state; it cannot mutate state (LangGraph conditional-edge functions only
choose a destination). Precedence **matters** — check in this exact order:
1. `critic_feedback.verdict == "revise"` **and** `revision_count <
   config.MAX_REVISIONS` -> return `"risk_analyst"`. Check this first, or a
   low-confidence "revise" verdict could get short-circuited to
   `human_gate` before the analyst gets a chance to fix it.
2. Otherwise, if **any** of: (a) verdict was `"revise"` and retries are now
   exhausted, (b) `critic_feedback.confidence < config.CRITIC_MIN_CONFIDENCE`,
   (c) `risk_memo.risk_score >= config.RISK_ESCALATION_THRESHOLD` -> return
   `"human_gate"`. Three different reasons land here for three different
   reasons — "the system couldn't converge", "the critic itself isn't
   sure", and "it converged but the stakes are high enough to want a human
   anyway" — don't collapse them into one unlabelled condition.
3. Otherwise -> return `"__end__"`.

**`build_graph(checkpointer=None)`**
- R1: `graph = StateGraph(CaseState)`.
- R2: Add all 7 nodes: `planner`, `entity_resolution`, `adverse_media`,
  `retrieval`, `risk_analyst`, `critic`, `human_gate`, mapped to their node
  functions.
- R3: Fixed edges: `START -> planner -> entity_resolution -> adverse_media
  -> retrieval -> risk_analyst -> critic`.
- R4: `graph.add_conditional_edges("critic", route_after_critic,
  {"risk_analyst": "risk_analyst", "human_gate": "human_gate", "__end__": END})`.
- R5: `graph.add_edge("human_gate", END)`.
- R6: Compile: if `checkpointer is not None`, pass
  `checkpointer=checkpointer, interrupt_before=["human_gate"]` to
  `graph.compile(...)`; otherwise compile with no extra kwargs (this is
  what lets `tests/test_graph_structure.py` compile the graph without a
  real checkpointer). **Check the LangGraph docs for the version pinned in
  `pyproject.toml`** before relying on `interrupt_before` — this argument's
  exact name/behaviour has moved between LangGraph releases; the pattern
  here is the longer-standing, more broadly documented one, but verify
  against your installed version.

**Acceptance criteria:** `uv run pytest tests/test_graph_structure.py -q`
passes all 7 tests.

---

## Phase 10 — Memory & CLI (~1.5 days)

### Requirements: `aml_agents/memory/case_store.py`

**`_connect(db_path) -> contextmanager yielding sqlite3.Connection`**
- R1: `db_path.parent.mkdir(parents=True, exist_ok=True)`.
- R2: `sqlite3.connect(db_path)`, set `.row_factory = sqlite3.Row`.
- R3: `yield` the connection inside a `try/finally`; `conn.commit()` after
  the `yield` (inside the `try`, so it still runs on the success path),
  `conn.close()` in `finally`.

**`init_db(db_path)`** — open a connection via `_connect`, execute `_SCHEMA`.

**`_state_to_json(state) -> str`** — `json.dumps(dict(state), default=...)`
where `default` calls `.model_dump()` on anything with that attribute
(every evidence/memo/decision object in `CaseState` is a Pydantic model;
plain `json.dumps` can't serialise those on its own) and raises `TypeError`
for anything else.

**`save_case(state, db_path)`**
- R1: Call `init_db(db_path)` first (so this works against a fresh DB).
- R2: Pull `risk_score`/`risk_level`/`recommended_action` from
  `state.get("risk_memo")` (all `None` if no memo yet), `human_decision`
  from `state.get("human_decision")`.
- R3: `INSERT ... ON CONFLICT(case_id) DO UPDATE SET ...` (upsert) —
  running this twice for the same `case_id` should update the row, not
  create a duplicate or error.

**`get_case(case_id, db_path) -> dict | None`** — `SELECT * FROM cases
WHERE case_id = ?`, return a `dict` or `None`.

**`list_cases(*, pending_human_review=None, db_path) -> list[dict]`** —
newest-`updated_at`-first; when `pending_human_review=True`, filter to
`human_review_required = 1 AND human_decision IS NULL`.

### Requirements: `aml_agents/main.py`

**`_get_checkpointer()`** — return a real LangGraph checkpointer, e.g.
`langgraph.checkpoint.sqlite.SqliteSaver.from_conn_string(str(config.LANGGRAPH_CHECKPOINT_DB_PATH))`.
Check the LangGraph docs for the exact import path/API for your pinned
version — this has moved between releases (see the note in Phase 9).

**`cmd_investigate(args)`**
- R1: `app = build_graph(checkpointer=_get_checkpointer())`.
- R2: `state = new_case_state(entity_name=args.entity)`.
- R3: `run_config = {"configurable": {"thread_id": state["case_id"]}}`.
- R4: `result = app.invoke(state, config=run_config)`.
- R5: `case_store.save_case(result)`.
- R6: Print `case_id`; if `result.get("risk_memo")`, pretty-print it as
  JSON; otherwise (paused before `human_gate`, or no memo) print each trace
  entry's `node_name`/`summary_out` so there's something inspectable.

**`cmd_resume(args)`**
- R1: `app = build_graph(checkpointer=_get_checkpointer())`.
- R2: `run_config = {"configurable": {"thread_id": args.case_id}}`.
- R3: Build a `HumanDecision` from `args.decision`/`args.reviewer`/`args.notes`.
- R4: `app.update_state(run_config, {"human_decision": decision})`.
- R5: `result = app.invoke(None, config=run_config)` (resumes from the
  interrupt).
- R6: `case_store.save_case(result)`; print the final memo.

**`cmd_list_pending(_args)`** — `case_store.list_cases(pending_human_review=True)`,
print one line per case (case_id, entity_name, risk_score, recommended_action).

**Acceptance criteria:** no automated tests for this phase (it's
integration-shaped — SQLite + LangGraph checkpointing + a real or local LLM
all have to work together). Manually verify the full loop:
```bash
uv run python -m aml_agents.main investigate --entity "<a high-risk test name>"
# should pause before human_gate and print its trace
uv run python -m aml_agents.main list-pending
# should show the paused case
uv run python -m aml_agents.main resume --case-id <id> --decision confirm --reviewer "you"
# should complete and print the final memo
```

---

## Phase 11 — Evaluation harness (~1.5 days)

### Requirements: `aml_agents/evaluation/test_cases.py`

- Populate `KNOWN_SANCTIONED` with 5-10 `GoldenCase` entries sampled from
  your own `data/raw/sanctions/*.csv` (don't hardcode names you haven't
  verified are in your actual downloaded snapshot).
- Populate `NAME_VARIANTS` with deliberate typos/reorderings/transliterations
  of a few of those names, to probe whether `config.ENTITY_MATCH_MIN_SCORE`
  is well-calibrated.
- Populate `CLEARLY_CLEAN` with a handful of obviously fictional,
  unremarkable names.

### Requirements: `aml_agents/evaluation/metrics.py`

**`entity_resolution_accuracy(cases, results) -> dict`**
- R1: `cases` and `results` are parallel lists (same order, same length) —
  for each pair, compare `case["expected_entity_resolved"]` against
  `result["entity_resolved"]`.
- R2: Count tp/fp/tn/fn in the standard sense (`expected_entity_resolved`
  is the "positive" condition), compute `accuracy`, `precision`, `recall`.
  Handle the zero-denominator case (`float("nan")` is fine) rather than
  raising `ZeroDivisionError`.

**`latency_by_node(results) -> dict[str, dict]`**
- R1: Across every `CaseState` in `results`, group `AgentTrace.duration_ms`
  by `node_name` (skip entries where `duration_ms is None`).
- R2: Per node, return `{"count": ..., "mean_ms": ..., "max_ms": ...}`.

**`critic_catch_rate` / `retrieval_faithfulness`** — stretch (Phase 13);
leave as `NotImplementedError` unless you want to build them now. The
broken `RiskMemo` example you built for Phase 8's manual testing is exactly
the input `critic_catch_rate` needs — build a small list of 3-5 such
examples with known issues and measure what fraction the critic actually
flags.

**Acceptance criteria:** no dedicated test file — write a short script (or
a notebook cell) that runs `entity_resolution_node` over `all_cases()` from
`test_cases.py` and feeds the results into `entity_resolution_accuracy`;
sanity-check the numbers look right given what you know about your golden
set (e.g. `KNOWN_SANCTIONED` should score very high recall if
`ENTITY_MATCH_MIN_SCORE` is reasonable).

---

## Phase 12 — Observability wrap-up (~0.5 day)

No new code — `make_trace()` is given and every node above should already
be calling it. This phase is about *using* what you've already built:

- Run a full `investigate` through `resume`, then `case_store.get_case(case_id)`,
  parse `state_json`, and print every trace entry in order — confirm you
  can answer "which agent produced this specific claim in the memo" purely
  from the trace, without re-running anything.
- If any node's `summary_in`/`summary_out` turns out to be too terse to
  actually answer that question, go back and improve it — this is the kind
  of thing that only becomes obvious once you're staring at a real trace.

**Learning objective:** with one agent, print-debugging works. With seven
agents handing off state, you need a trace of who-did-what-and-why per
case, or debugging becomes guesswork — confirm that's actually true for
what you built, not just in principle.

---

## Phase 13 (stretch) — Beyond the required scaffolding

Pick any:

- **Dynamic planner:** implement `build_dynamic_plan` in `planner.py` (same
  prompt+parse+validate shape as `risk_analyst_node`), wire a
  `PLANNER_MODE` config flag, and compare against the static plan on your
  Phase 11 golden set. Only keep it if it earns its complexity.
- **True tool-calling agent:** implement `run_tool_calling_agent` in
  `tool_registry.py` — a multi-turn loop where the LLM chooses which tools
  to call, rather than the graph deciding for it. Compare its behaviour
  (and cost/latency) against the fixed pipeline.
- **Smarter adverse-media relevance:** replace `adverse_media_node`'s
  score-threshold gate with an LLM call that judges same-entity-ness and
  materiality per hit (see the note left in Phase 4).
- **Local hardware A/B:** point `LocalOpenAICompatLLMClient` at a model
  running on your own hardware and compare its risk memos / critic
  verdicts against the Anthropic API on the same golden set.
- **Second, adversarial critic:** add a differently-prompted second critic
  (multi-agent debate) and compare its catch rate against the single-critic
  setup from Phase 8, using `critic_catch_rate`.
- **`retrieval_faithfulness`:** port your existing RAGAS-based evaluation
  from the compliance Q&A assistant to this project's `RetrievedPassage`/
  `RiskMemo` schemas.