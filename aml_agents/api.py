"""HTTP API over the investigator (PROJECT_PLAN.md Phase 13).

    uvicorn aml_agents.api:app --host 0.0.0.0 --port 8000 --workers 1

One worker on purpose: the case store and checkpoints are SQLite files (see
DEPLOYMENT_GUIDE.md section 6.4). Handlers are plain `def` because a graph run
blocks; FastAPI runs them in a thread pool so one slow case does not stall the
others. Set API_KEY to require an `X-API-Key` header on every route except
/health.
"""

from __future__ import annotations

import hmac
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from aml_agents import config, service
from aml_agents.llm_client import LLMBackendError

log = logging.getLogger("aml_agents.api")


class InvestigationRequest(BaseModel):
    entity_name: str = Field(min_length=1, max_length=300)

    @field_validator("entity_name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("entity_name must not be blank")
        return v


class DecisionRequest(BaseModel):
    decision: Literal["confirm", "override_clear", "override_escalate"]
    reviewer: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=5000)


def _build_default_graph() -> Any:
    # Imported here so importing this module (e.g. in tests) does not load
    # the checkpointer or touch disk.
    from aml_agents.graph import build_graph
    from aml_agents.main import _get_checkpointer

    return build_graph(checkpointer=_get_checkpointer())


def create_app(graph: Any | None = None, db_path: Path | None = None) -> FastAPI:
    """Build the app. `graph` and `db_path` can be injected for tests; in
    normal use the graph is built once at startup."""

    store_path = db_path or config.CASE_STORE_DB_PATH

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
        app.state.graph = graph if graph is not None else _build_default_graph()
        yield

    app = FastAPI(title="Agentic AML Investigator", version="0.1.0", lifespan=lifespan)

    def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
        expected = os.getenv("API_KEY", "")
        if expected and not hmac.compare_digest(x_api_key or "", expected):
            raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")

    def get_graph(request: Request) -> Any:
        return request.app.state.graph

    protected = [Depends(require_api_key)]

    @app.exception_handler(LLMBackendError)
    async def _llm_down(_request: Request, exc: LLMBackendError):
        from fastapi.responses import JSONResponse

        log.error("LLM backend error: %s", exc)
        return JSONResponse(status_code=502, content={"detail": f"LLM backend unavailable: {exc}"})

    @app.exception_handler(FileNotFoundError)
    async def _data_missing(_request: Request, exc: FileNotFoundError):
        from fastapi.responses import JSONResponse

        log.error("required data missing: %s", exc)
        return JSONResponse(status_code=503, content={"detail": f"Required data not loaded: {exc}"})

    @app.get("/health")
    def health() -> dict:
        try:
            service.check_store(store_path)
        except Exception as exc:  # any failure to open the store means not healthy
            raise HTTPException(status_code=503, detail=f"case store unavailable: {exc}") from exc
        return {"status": "ok"}

    @app.post("/investigations", response_model=service.CaseResult, dependencies=protected)
    def create_investigation(body: InvestigationRequest, graph: Any = Depends(get_graph)):
        return service.start_investigation(graph, body.entity_name, db_path=store_path)

    @app.get("/investigations", response_model=list[service.CaseSummary], dependencies=protected)
    def list_investigations(pending: bool = Query(default=False)):
        return service.list_cases(pending=pending, db_path=store_path)

    @app.get("/investigations/{case_id}", response_model=service.CaseResult, dependencies=protected)
    def read_investigation(case_id: str):
        try:
            return service.get_case(case_id, db_path=store_path)
        except service.CaseNotFound:
            raise HTTPException(status_code=404, detail=f"Unknown case {case_id!r}") from None

    @app.post("/investigations/{case_id}/decision", response_model=service.CaseResult, dependencies=protected)
    def decide(case_id: str, body: DecisionRequest, graph: Any = Depends(get_graph)):
        try:
            return service.resume_investigation(
                graph, case_id, body.decision, body.reviewer, body.notes, db_path=store_path
            )
        except service.CaseNotFound:
            raise HTTPException(status_code=404, detail=f"Unknown case {case_id!r}") from None
        except service.CaseNotPending as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None

    return app


app = create_app()
