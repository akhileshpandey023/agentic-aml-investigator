# Evaluation plan (deepeval)

How the investigator is evaluated, what each metric is for, and the order to
adopt it in. Code lives in `aml_agents/evaluation/`; the requirements entry
is Phase 11 in `PROJECT_PLAN.md`.

## 1. Role of deepeval

deepeval is the metric engine: it turns a test case into scored results.
SQLite (`eval_store.py`) stays the system of record, so runs can be compared
after a config or prompt change. Nothing is sent to Confident AI: telemetry
is switched off in `evaluation/__init__.py`, and there is no API key.

The point of using it is the split between two kinds of metric.

- **Deterministic** (custom `BaseMetric`, no LLM). Used whenever code can
  decide the answer. Free, repeatable, never flaky. These are the gates.
- **LLM-judged** (`FaithfulnessMetric`, `GEval`). Used only for what code
  cannot check: is each claim in the narrative supported by the evidence, and
  does it admit gaps. These depend on the judge model and are a trend signal
  until calibrated (section 4).

## 2. What is measured

Three levels, cheapest first. Each CLI run is one level and one stored run.

| Level | Runs | Needs LLM | Metrics |
|---|---|---|---|
| `entity` | `entity_resolution_node` on the golden cases | no | Entity Resolution Match per case; accuracy, precision, recall |
| `e2e` | the full graph on the golden cases, stopping at the human gate | yes | Entity Resolution Match, Escalation Routing, Citation Validity, Policy Consistency; with `--judge`: Faithfulness, Gap Disclosure, Match Strength Calibration; plus error rate, pause rate, latency |
| `critic` | the Critic on 2 clean and 6 seeded-defect memos | yes | Critic Verdict Match per case; catch rate and false-positive rate |

What each custom metric checks:

- **Entity Resolution Match**: `entity_resolved` equals the golden label.
- **Escalation Routing**: a sanctions hit reached the human gate and a clean
  entity did not. The expectation is derived from the label in
  `adapters.expected_human_review`, not from the LLM's score.
- **Citation Validity**: every citation is an evidence ID the analyst was
  given; a memo with findings cites something.
- **Policy Consistency**: level and action match the score under the bands,
  and a match of 90 or more respects the floor of 70. The bands are parsed
  from `prompts/risk_policy.py`, so the check cannot drift from the prompt;
  a test fails if the wording stops parsing.
- **Critic catch rate / false-positive rate**: always read as a pair. A critic
  that says "revise" every time catches everything and is useless; the
  false-positive rate exposes it (there is a test for exactly this).

Citation Validity and Policy Consistency audit the Risk Analyst and also
act as an independent check on the Critic, since they test the same things
the Critic is prompted to test.

## 3. Golden data

- `test_cases.py` is unchanged: known sanctioned, name variants, clean. The
  escalation label is derived, so there is no second column to keep in sync.
- `critic_cases.py` holds seeded memos. The evidence is synthetic, so these
  need no downloaded data. A test checks the seeded cases against the code
  metrics, so a "control" that is secretly defective gets caught.
- 15 entity cases is small. One case moves recall by several points, so treat
  differences under about 10 points as noise. Grow the set before trusting
  fine threshold tuning.

## 4. Using the LLM judge

Setup: `EVAL_JUDGE_BACKEND` (`same`, `anthropic`, `local`) and
`EVAL_JUDGE_MODEL` in `.env`. Default is `same`, which is the weakest choice
because a small local model grades its own output. Use a different, stronger
model for the judge when you can.

Calibrate before trusting it:

1. Run `e2e --judge` on the golden cases.
2. Read 20 memos yourself and label each faithful or not.
3. Compare to the judge's pass/fail. Aim for 85% agreement or better before
   using Faithfulness numbers to make decisions. If it is lower, change the
   judge model first, then the criteria text in `deepeval_metrics.py`.
4. Re-calibrate whenever the judge model changes.

Judge calls that fail or return bad JSON are recorded as errors and left out
of means and pass rates (`.errors` metric), so a flaky judge shows up as a
count, not as a low score.

## 5. Workflow

```bash
uv sync --extra eval

uv run python -m aml_agents.evaluation.run_eval run --level entity --notes "baseline"
uv run python -m aml_agents.evaluation.run_eval run --level critic
uv run python -m aml_agents.evaluation.run_eval run --level e2e --notes "baseline"
uv run python -m aml_agents.evaluation.run_eval run --level e2e --judge

# change one thing (a threshold, a prompt, the model), run again, then:
uv run python -m aml_agents.evaluation.run_eval list
uv run python -m aml_agents.evaluation.run_eval compare <run_a> <run_b>
```

Change one variable between runs. Each run stores a config snapshot
(`eval_runs.config_json`), so a metric change can be traced to a change.

Isolation: no level writes to the case store or the checkpoint database. The
e2e level uses an in-memory checkpointer, one thread per case, and does not
resume at the human gate. Only the eval database persists. deepeval keeps its
own local cache under `.deepeval/` (gitignored); result caching is turned off
so a changed threshold is never hidden by a cached score.

A run where every case fails to run prints a warning and the first error. In
that state the aggregate numbers mean nothing (for example, missing sanctions
data makes every entity case fail).

## 6. Gating policy

| Metric | Treatment |
|---|---|
| Escalation Routing | hard gate: any failure is a bug. A sanctions hit that does not reach a human is the worst failure this system can have |
| Policy Consistency, Citation Validity | hard gate once the analyst prompt is stable |
| Entity recall on known sanctioned and variants | hard gate against a floor you set after the baseline; precision on clean names tracked beside it |
| Critic catch rate and false-positive rate | report both; set targets after the baseline |
| Faithfulness, Gap Disclosure, Match Strength | trend only until the judge is calibrated |
| latency, pause rate | informational |

## 7. Adoption order

1. **Baseline, no LLM.** Download data, run `entity`. Exit: accuracy, precision
   and recall stored; failures read case by case, not just as a number.
2. **Fix, re-run, compare.** The case-insensitive matching fix should move
   recall on the name variants. Use `compare` to confirm it did.
3. **Critic.** Run `critic` with the real Critic. Exit: you know its catch rate
   and false-positive rate, and which seeded defects it misses.
4. **End to end, deterministic only.** Run `e2e` without `--judge`.
   Escalation Routing, Citation Validity and Policy Consistency are expected to
   fail on cases that expose known issues (see section 8). Exit: each failure
   is explained by a defect, not by a bad label.
5. **Add the judge.** Run `--judge`, then calibrate (section 4).
6. **Lock in.** Record floors from the stable baseline and decide which metrics
   gate. Optionally run `e2e` in CI on a small subset with a stub or API judge.

Phase 13 comparisons (dynamic planner, local-hardware model, second critic)
are the same two commands: run the baseline, change one thing, `compare`.

## 8. What the metrics should expose in the current code

From the code review of `main`. These are predictions to check against real
runs, not results.

| Defect | Where it should show |
|---|---|
| Matching is case-sensitive ("Eliav Libi" scores 70) | Entity Resolution Match fails on case-only variants; recall below 1.0 |
| Escalation depends on the LLM's own `risk_score` | Escalation Routing fails when a sanctions hit is scored under the threshold |
| Adverse-media relevance is normalised to the top hit | Escalation Routing or Policy Consistency problems on clean names that share a token with a notice |
| Retry loop returns no memo after two bad outputs | `e2e.errors` or "no memo produced" in Citation Validity and Policy Consistency |
| Critic is shown titles, not snippets | possible misses where the defect is in how adverse-media or guidance text is described; no seeded case tests that yet, so add one |

## 9. Limits

- The e2e level was tested here with stubbed nodes and a stub judge, not
  against real sanctions data, the retrieval corpus or a real LLM.
- `compare_runs` compares aggregates. Per-case differences are in
  `eval_case_scores`; query it when an aggregate moves.
- `latency.<node>` uses trace node names, which are inconsistent in the
  pipeline today (the Critic's trace is labelled `risk_analyst`). Fix the
  labels before reading per-node latency.
- Pinned to deepeval 4.3.x. Its metric internals change between releases, so
  re-run the tests when upgrading.
