# Data sources (all public)

This project uses only publicly available data. Nothing here requires a
bank relationship, a paid API key, or non-public material.

## 1. Sanctions data (for the Entity Resolution agent)

Primary route (recommended — clean bulk CSV/JSON, updated daily, no key
required): **OpenSanctions**, a public, well-known open-data project that
mirrors official government sanctions lists in a consistent schema.

- US OFAC SDN list mirror: `https://www.opensanctions.org/datasets/us_ofac_sdn/`
- UK OFSI consolidated list mirror: `https://www.opensanctions.org/datasets/gb_hmt_sanctions/`
- Download the `targets.simple.csv` file from each dataset page into
  `data/raw/sanctions/`.

Authoritative originals (for reference / to cite in your write-up):
- US Treasury OFAC SDN list: `https://ofac.treasury.gov/specially-designated-nationals-and-blocked-persons-list-sdn-human-readable-lists`
- UK HM Treasury / OFSI consolidated list: `https://www.gov.uk/government/publications/financial-sanctions-consolidated-list-of-targets`

`scripts/download_public_data.py` automates the OpenSanctions CSV downloads
(this script is given — it's plain HTTP plumbing, not agent logic).

## 2. Adverse-media stand-in (for the Adverse Media agent)

Real adverse-media screening uses live news search. For a reproducible
practice corpus without needing a search API key, use published **FCA
Final Notices and enforcement press releases** — public, structured,
UK-relevant, and directly analogous in shape to a news hit: an entity name,
a date, a narrative of what went wrong.

- Landing page: `https://www.fca.org.uk/news/final-notices`
- Save 10–20 Final Notice PDFs (mix of individuals and firms, a few
  different years) as plain text into `data/raw/regulatory/fca_notices/`.
  There's no single bulk-download endpoint for these, so this step is
  manual/curated by design — treat it as building your own small,
  known-good test corpus.

## 3. Regulatory guidance corpus (for the Retrieval / RAG agent)

- **JMLSG guidance** (the UK's HM-Treasury-approved AML guidance):
  `https://www.jmlsg.org.uk/guidance/current-guidance/`
- **FATF Recommendations** (the international AML/CFT standard):
  `https://www.fatf-gafi.org/en/topics/fatf-recommendations.html`
- **FCA Financial Crime Guide**: search `FCA Financial Crime Guide FCG` on
  `https://www.fca.org.uk` — it's part of the public FCA Handbook.

Save the PDFs you want to index into `data/raw/regulatory/guidance/` —
organising them into one subdirectory per regulator is expected and
encouraged, e.g.:

```
data/raw/regulatory/guidance/
├── fatf/
│   └── fatf_recommendations.pdf
├── fca/
│   └── financial_crime_guide.pdf
└── jmlsg/
    └── jmlsg_guidance_part_i.pdf
```

`scripts/ingest_guidance.py` and `VectorStore.ingest_dir()` both search this
tree recursively, and the subdirectory name is preserved into each chunk's
`source_document` metadata (e.g. `"fatf/fatf_recommendations.txt"`) — so a
citation in a risk memo tells you which regulator it came from, not just
which file. Once
you've saved a few, and once you've implemented `aml_agents/tools/vector_store.py`
(Phase 3 in `PROJECT_PLAN.md`), run:

```bash
uv run python scripts/ingest_guidance.py
```

which extracts text from each PDF (this script is given) and calls your
`VectorStore.ingest_dir()` implementation to index it.

## Directory layout once populated

```
data/raw/
├── sanctions/
│   ├── us_ofac_sdn.csv
│   └── gb_hmt_sanctions.csv
└── regulatory/
    ├── fca_notices/       # adverse-media stand-in corpus (.txt, flat)
    └── guidance/          # regulatory corpus — one subdirectory per regulator
        ├── fatf/          #   .pdf -> .txt, extracted in place
        ├── fca/
        └── jmlsg/
data/processed/            # chunked/embedded artifacts, case store, checkpoints
```

## A note on using real public names in your golden test set

The sanctions lists and FCA notices are public record — using real
designated entities as test cases in `aml_agents/evaluation/test_cases.py`
is normal practice in AML tooling. Keep any *made-up* "clean" comparison
names clearly fictional so you're not implying anything about a real,
non-designated person or firm.