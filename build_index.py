"""Build a per-page text index from one or more PDF files.

Usage:
    python build_index.py <pdf> [<pdf> ...] [-o index.json]

The output is a JSON file with structure:
    {
      "documents": {
        "<pdf_path>": {"num_pages": int, "pages": {"1": "text...", ...}}
      },
      "inverted": {
        "<token>": [["<pdf_path>", page_number], ...]
      }
    }
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader

TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def extract_pages(pdf_path: Path) -> list[str]:
    reader = PdfReader(str(pdf_path))
    return [page.extract_text() or "" for page in reader.pages]


def tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(text)]


def build_index(pdf_paths: list[Path]) -> dict:
    documents: dict = {}
    inverted: dict[str, set[tuple[str, int]]] = {}

    for pdf_path in pdf_paths:
        key = str(pdf_path)
        pages = extract_pages(pdf_path)
        documents[key] = {
            "num_pages": len(pages),
            "pages": {str(i + 1): text for i, text in enumerate(pages)},
        }
        for i, text in enumerate(pages):
            page_no = i + 1
            for token in set(tokenize(text)):
                inverted.setdefault(token, set()).add((key, page_no))

    return {
        "documents": documents,
        "inverted": {
            token: sorted([list(loc) for loc in locs])
            for token, locs in inverted.items()
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a text index from PDFs.")
    parser.add_argument("pdfs", nargs="+", type=Path, help="PDF files to index")
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("index.json"),
        help="Output JSON file (default: index.json)",
    )
    args = parser.parse_args(argv)

    for p in args.pdfs:
        if not p.is_file():
            print(f"error: not a file: {p}", file=sys.stderr)
            return 2

    index = build_index(args.pdfs)
    args.output.write_text(json.dumps(index, ensure_ascii=False, indent=2))

    total_pages = sum(d["num_pages"] for d in index["documents"].values())
    print(
        f"Indexed {len(index['documents'])} document(s), "
        f"{total_pages} page(s), "
        f"{len(index['inverted'])} unique tokens -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
