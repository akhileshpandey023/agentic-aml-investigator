"""Download the public datasets this project needs (Phase 0).

GIVEN / fully implemented — this is plain HTTP plumbing, not agent logic,
so it isn't part of the practice exercise. See PROJECT_PLAN.md Phase 0.

Usage:
    python scripts/download_public_data.py --sanctions
    python scripts/download_public_data.py --fetch-url <url> --out data/raw/regulatory/guidance/some_doc.pdf
    python scripts/download_public_data.py --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"

SANCTIONS_SOURCES = {
    "us_ofac_sdn.csv": "https://data.opensanctions.org/datasets/latest/us_ofac_sdn/targets.simple.csv",
    "gb_hmt_sanctions.csv": "https://data.opensanctions.org/datasets/latest/gb_hmt_sanctions/targets.simple.csv",
}


def download(url: str, dest: Path, timeout: int = 60) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"GET {url}")
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    print(f"  -> saved {dest} ({len(resp.content):,} bytes)")


def download_sanctions() -> None:
    out_dir = RAW_DIR / "sanctions"
    for filename, url in SANCTIONS_SOURCES.items():
        try:
            download(url, out_dir / filename)
        except requests.RequestException as exc:
            print(
                f"  ! failed to fetch {filename}: {exc}\n"
                f"    OpenSanctions occasionally changes dataset URLs — check the "
                f"dataset page in data/README.md and update SANCTIONS_SOURCES if so.",
                file=sys.stderr,
            )


def fetch_single_url(url: str, out: Path) -> None:
    download(url, out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Download everything automatable (sanctions data)")
    parser.add_argument("--sanctions", action="store_true", help="Download sanctions CSVs from OpenSanctions")
    parser.add_argument("--fetch-url", metavar="URL", help="Fetch a single public document URL")
    parser.add_argument("--out", metavar="PATH", help="Destination path for --fetch-url")
    args = parser.parse_args()

    if args.fetch_url:
        if not args.out:
            parser.error("--fetch-url requires --out")
        fetch_single_url(args.fetch_url, Path(args.out))
        return

    if args.all or args.sanctions:
        download_sanctions()

    if not any([args.all, args.sanctions, args.fetch_url]):
        parser.print_help()


if __name__ == "__main__":
    main()
