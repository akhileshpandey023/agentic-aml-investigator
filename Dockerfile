# syntax=docker/dockerfile:1
# Build:  docker build -t aml-investigator:dev .
# Skip the model download at build time:  --build-arg WARM_MODELS=false
# See DEPLOYMENT_GUIDE.md for what each line is for.

FROM python:3.12-slim

# uv, copied from its official image. Pinned so builds are repeatable.
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

# A non-root user. Fixed uid so file ownership is predictable.
RUN useradd --create-home --uid 10001 --home-dir /home/appuser appuser

ENV HOME=/home/appuser \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH" \
    UV_LINK_MODE=copy

WORKDIR /app

# 1. Dependencies first: these two files change rarely, so this (slow) layer
#    is cached across code edits. --frozen installs exactly what uv.lock says.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2. State directory (compose mounts a volume over it), then drop root.
RUN mkdir -p /app/data/processed && chown -R appuser:appuser /app/data
USER appuser

# 3. Model downloads, as the app user so the caches under ~/.cache belong to it.
#    Needs network at build time, not at run time.
ARG WARM_MODELS=true
COPY scripts/warm_models.py scripts/warm_models.py
RUN if [ "$WARM_MODELS" = "true" ]; then python scripts/warm_models.py; fi \
 && mkdir -p /home/appuser/.cache && chmod -R a+rX /home/appuser

# 4. Application code last: changes on every commit, cheap to rebuild.
COPY aml_agents ./aml_agents
COPY scripts ./scripts

EXPOSE 8000

# Healthcheck without curl (not in the slim image).
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/health', timeout=4)"

# --host 0.0.0.0: otherwise the server only accepts connections from inside the container.
# --workers 1: the case store and checkpoints are SQLite files (DEPLOYMENT_GUIDE.md 6.4).
CMD ["uvicorn", "aml_agents.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
