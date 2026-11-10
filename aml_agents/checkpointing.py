"""Checkpoint serialisation for the graph.

LangGraph stores state between steps (and across a human-review pause) with a
msgpack serializer. Our Pydantic models are not on its default allowlist, and
recent LangGraph versions warn that unregistered types will be blocked in a
future release, at which point a paused case could no longer be resumed.
Every checkpointer in this project is built with the allowlist below, derived
from schemas.py so a new model is covered automatically.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import BaseModel

from aml_agents import schemas

ALLOWED_MSGPACK_MODULES = [
    (schemas.__name__, name)
    for name, obj in vars(schemas).items()
    if isinstance(obj, type) and issubclass(obj, BaseModel) and obj.__module__ == schemas.__name__
]


def make_serde() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=ALLOWED_MSGPACK_MODULES)


def new_memory_saver() -> InMemorySaver:
    return InMemorySaver(serde=make_serde())
