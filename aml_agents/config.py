"""Central configuration — GIVEN, not part of the exercise.

Nothing agent-specific lives here — thresholds, paths, and env-driven
settings only. Nodes and tools import from this module rather than reading
os.environ directly, so every tunable is discoverable in one place, and so
your implementation and PROJECT_PLAN.md's requirements are talking about the
exact same threshold values.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- LLM backend ---
# LLM_BACKEND = os.getenv("LLM_BACKEND", "anthropic")  # "anthropic" | "local"
LLM_BACKEND = os.getenv("LLM_BACKEND", "local")  # "anthropic" | "local"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "qwen2.5:7b")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))  # per request; a hung endpoint must not hang a case

# --- Data paths ---
SANCTIONS_DIR = REPO_ROOT / "data" / "raw" / "sanctions"
FCA_NOTICES_DIR = REPO_ROOT / "data" / "raw" / "regulatory" / "fca_notices"
GUIDANCE_DIR = REPO_ROOT / "data" / "raw" / "regulatory" / "guidance"

VECTOR_STORE_DIR = Path(os.getenv("VECTOR_STORE_DIR", REPO_ROOT / "data" / "processed" / "chroma"))
CASE_STORE_DB_PATH = Path(os.getenv("CASE_STORE_DB_PATH", REPO_ROOT / "data" / "processed" / "case_store.sqlite"))
LANGGRAPH_CHECKPOINT_DB_PATH = Path(
    os.getenv("LANGGRAPH_CHECKPOINT_DB_PATH", REPO_ROOT / "data" / "processed" / "checkpoints.sqlite")
)
# Persistent evaluation results (Phase 11). Kept separate from the case store.
EVAL_DB_PATH = Path(os.getenv("EVAL_DB_PATH", REPO_ROOT / "data" / "processed" / "eval_results.sqlite"))

# --- Entity resolution ---
ENTITY_MATCH_MIN_SCORE = 85  # rapidfuzz score (0-100) below which a candidate isn't a "hit"
ENTITY_MATCH_TOP_K = 5

# --- Retrieval ---
RETRIEVAL_TOP_K = 8
RETRIEVAL_RERANK_TOP_K = 4  # after cross-encoder rerank, how many passages to keep
CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
# NOT currently used: VectorStore relies on Chroma's default embedding function.
# Wiring this in changes every embedding, so it needs a re-ingest into a
# differently named collection; do that deliberately, not by accident.
EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-4B"

# --- Adverse media ---
ADVERSE_MEDIA_TOP_K = 5
ADVERSE_MEDIA_RELEVANCE_SCORE = 0.15
# Share of the entity name's distinctive tokens that must appear in a notice
# for it to count as a hit. BM25 scores are normalised to the best document in
# the batch, so without this the top document always scores 1.0 even when it
# shares a single word with the name.
ADVERSE_MEDIA_MIN_TOKEN_COVERAGE = 1.0

# --- Risk / reflection loop ---
MAX_REVISIONS = 2  # bound on the critic -> risk_analyst loop
RISK_ESCALATION_THRESHOLD = 70  # risk_score (0-100) at or above which human_gate is required
CRITIC_MIN_CONFIDENCE = 0.6  # below this, escalate to human regardless of risk score
# A sanctions candidate at or above this match score is treated as a confirmed
# match: risk_score is floored at SANCTIONS_RISK_FLOOR and the case always goes
# to a human, whatever risk_score the LLM chose. Both are enforced in code
# (policy.py, graph.route_after_critic) and quoted in the prompts.
SANCTIONS_CONFIRMED_MATCH_SCORE = 90
SANCTIONS_RISK_FLOOR = 70

# --- Misc ---
RANDOM_SEED = 13

# --- Evaluation (Phase 11, deepeval) ---
# The judge model grades LLM-reasoning outputs (faithfulness, G-Eval). Keep it
# separate from the pipeline's own backend: a 7B local model grading its own
# output is a weak signal. "same" reuses LLM_BACKEND / its model settings.
EVAL_JUDGE_BACKEND = os.getenv("EVAL_JUDGE_BACKEND", "same")  # "same" | "anthropic" | "local"
EVAL_JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", "")  # empty -> that backend's default model
EVAL_JUDGE_MAX_TOKENS = int(os.getenv("EVAL_JUDGE_MAX_TOKENS", "2048"))
EVAL_FAITHFULNESS_THRESHOLD = 0.8
EVAL_GEVAL_THRESHOLD = 0.7

