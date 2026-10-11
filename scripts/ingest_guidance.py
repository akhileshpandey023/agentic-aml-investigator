"""Extract text from the regulatory guidance PDFs and index them via your
VectorStore implementation.

GIVEN / fully implemented — PDF text extraction is plain utility code, not
agent logic. This script calls `aml_agents.tools.vector_store.VectorStore`,
which you implement in Phase 3 (see PROJECT_PLAN.md) — running this before
that's done will raise the NotImplementedError you left in `ingest_dir()`,
which is expected.

PDFs may be organised into subdirectories under config.GUIDANCE_DIR (e.g.
guidance/fatf/, guidance/fca/, guidance/jmlsg/) — extraction recurses, and
writes each .txt next to its source .pdf, so the subdirectory (and the
regulator it names) survives into ingest_dir()'s source_document metadata.

Usage:
    python scripts/ingest_guidance.py
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from aml_agents import config
from aml_agents.tools.vector_store import VectorStore


def extract_pdfs_to_text(guidance_dir: Path = config.GUIDANCE_DIR) -> int:
    # rglob, not glob: PDFs are expected to be organised into subdirectories
    # by source regulator (guidance/fatf/, guidance/fca/, guidance/jmlsg/, ...)
    # — grouping by source is good practice, not a layout VectorStore.ingest_dir
    # should have to fight against. Each .txt is written next to its .pdf, so
    # the subdirectory structure (and therefore the source regulator) is
    # preserved for ingest_dir to pick up.
    pdfs = sorted(guidance_dir.rglob("*.pdf"))
    count = 0
    for pdf_path in pdfs:
        txt_path = pdf_path.with_suffix(".txt")
        if txt_path.exists() and txt_path.stat().st_mtime >= pdf_path.stat().st_mtime:
            continue  # already extracted, PDF unchanged since
        reader = PdfReader(str(pdf_path))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        txt_path.write_text(text, encoding="utf-8")
        print(f"extracted {pdf_path.name} -> {txt_path.name} ({len(text):,} chars)")
        count += 1
    return count


def main() -> None:
    if not config.GUIDANCE_DIR.exists() or not any(config.GUIDANCE_DIR.rglob("*.pdf")):
        print(
            f"No PDFs found in {config.GUIDANCE_DIR}. See data/README.md section 3 "
            f"for what to put there before running this."
        )
        return
    
    extracted = extract_pdfs_to_text()
    print(f"Extracted text from {extracted} new/updated PDF(s).")

    store = VectorStore()
    chunk_count = store.ingest_dir(config.GUIDANCE_DIR)
    print(f"Indexed {chunk_count} chunks into the vector store at {config.VECTOR_STORE_DIR}.")

    if not config.FCA_NOTICES_DIR.exists() or not any(config.FCA_NOTICES_DIR.rglob("*.pdf")):
        print(
            f"No PDFs found in {config.FCA_NOTICES_DIR}. See data/README.md section 2 "
            f"for what to put there before running this."
        )
        return

    extracted = extract_pdfs_to_text(config.FCA_NOTICES_DIR)
    print(f"Extracted text from {extracted} new/updated PDF(s).")
    

if __name__ == "__main__":
    main()