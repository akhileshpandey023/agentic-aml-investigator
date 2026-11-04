"""Evaluation harness (Phase 11) — golden cases, deepeval metrics, SQLite results.

See EVAL_PLAN.md for the strategy and PROJECT_PLAN.md Phase 11 for the
requirements.

deepeval phones home by default. Evaluation inputs here include sanctions
screening evidence, so telemetry is switched off before anything imports
deepeval. Results stay local, in SQLite (see eval_store.py); nothing is sent
to Confident AI unless you add a CONFIDENT_API_KEY yourself.
"""

import os

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "1")
