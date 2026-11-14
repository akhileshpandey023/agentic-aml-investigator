"""Download the two ML models the app fetches on first use, so they can be
baked into the Docker image at build time instead of stalling the first
request in a fresh container.

  - Chroma's default embedding model (ONNX MiniLM), cached under ~/.cache/chroma
  - the cross-encoder reranker used by tools/vector_store.py, cached under ~/.cache/huggingface

Deliberately does not import aml_agents, so the Docker layer that runs it is
not invalidated by code changes. The model name must match
config.CROSS_ENCODER_MODEL (tests/test_docker_files.py checks this).
"""

import os

CROSS_ENCODER_MODEL = os.getenv("CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")


def main() -> None:
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    DefaultEmbeddingFunction()(["warm up"])
    print("chroma default embedding model ready")

    from sentence_transformers import CrossEncoder

    CrossEncoder(CROSS_ENCODER_MODEL)
    print(f"cross-encoder {CROSS_ENCODER_MODEL} ready")


if __name__ == "__main__":
    main()
