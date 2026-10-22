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

# --- Data paths ---
SANCTIONS_DIR = REPO_ROOT / "data" / "raw" / "sanctions"
FCA_NOTICES_DIR = REPO_ROOT / "data" / "raw" / "regulatory" / "fca_notices"
GUIDANCE_DIR = REPO_ROOT / "data" / "raw" / "regulatory" / "guidance"

VECTOR_STORE_DIR = Path(os.getenv("VECTOR_STORE_DIR", REPO_ROOT / "data" / "processed" / "chroma"))
CASE_STORE_DB_PATH = Path(os.getenv("CASE_STORE_DB_PATH", REPO_ROOT / "data" / "processed" / "case_store.sqlite"))
LANGGRAPH_CHECKPOINT_DB_PATH = Path(
    os.getenv("LANGGRAPH_CHECKPOINT_DB_PATH", REPO_ROOT / "data" / "processed" / "checkpoints.sqlite")
)

# --- Entity resolution ---
ENTITY_MATCH_MIN_SCORE = 85  # rapidfuzz score (0-100) below which a candidate isn't a "hit"
ENTITY_MATCH_TOP_K = 5

# --- Retrieval ---
RETRIEVAL_TOP_K = 8
RETRIEVAL_RERANK_TOP_K = 4  # after cross-encoder rerank, how many passages to keep
CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-4B"

# --- Adverse media ---
ADVERSE_MEDIA_TOP_K = 5
ADVERSE_MEDIA_RELEVANCE_SCORE = 0.15

# --- Risk / reflection loop ---
MAX_REVISIONS = 2  # bound on the critic -> risk_analyst loop
RISK_ESCALATION_THRESHOLD = 70  # risk_score (0-100) at or above which human_gate is required
CRITIC_MIN_CONFIDENCE = 0.6  # below this, escalate to human regardless of risk score

# --- Misc ---
RANDOM_SEED = 13
