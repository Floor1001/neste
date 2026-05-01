#!/usr/bin/env python3
"""PID zoektool - search tool for P&ID (Piping & Instrumentation Diagram) PDFs.

Extracts tags from a P&ID PDF and provides search/listing commands.
Categorizes:
  - equipment   e.g. 53BG-01, 53EA-03, 53FA-10S
  - valve       e.g. 53MV-0005, 53NRV-0004, 53SV-109
  - instrument  e.g. 53LC-101A, 53PI-138, 53AA-005C
  - line        e.g. 4"ES53003-6-1B2NB-NT-H
  - pid_ref     e.g. 082755C-053-PID-0021-0001-03
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PDF = "UNIT 53.pdf"
CACHE_DIR = Path(".pid_cache")

# Equipment tags: 2-3 letters after unit number, dash, digits, optional suffix.
# Excludes well-known instrument and valve prefixes so categories don't overlap.
VALVE_PREFIXES = {"MV", "SV", "NRV", "CV", "GV", "BV", "XV", "PV", "TV", "LV", "FV"}
INSTRUMENT_PREFIXES = {
    "AA", "AI", "AT", "AE", "AC",
    "FI", "FT", "FE", "FC", "FQ", "FY",
    "LI", "LT", "LC", "LG", "LSH", "LSL", "LAH", "LAL",
    "PI", "PT", "PC", "PG", "PSH", "PSL", "PAH", "PAL", "PDI", "PDT",
    "TI", "TT", "TC", "TE", "TG", "TW", "TAH", "TAL",
    "HS", "HC", "ZSH", "ZSL", "ZSC", "ZSO", "SC",
}

RE_TAG = re.compile(r"\b53([A-Z]{2,4})[\s-]?(\d{1,4})([A-Z])?\b")
RE_LINE = re.compile(r'\b\d{1,2}"[A-Z]{1,3}\d{4,6}-\d+-[A-Z0-9]+-[A-Z0-9]+-[A-Z]+\b')
RE_PID_REF = re.compile(r"\b\d{6}C-\d{3}-PID-\d{4}-\d{4}-\d{2}\b")


@dataclass
class Hit:
    tag: str
    category: str
    page: int
    line_no: int
    snippet: str


@dataclass
class Index:
    pages: list[str] = field(default_factory=list)  # raw text per page
    by_tag: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    categories: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))


def require_pdftotext() -> str:
    path = shutil.which("pdftotext")
    if not path:
        sys.exit("pdftotext not found. Install poppler-utils.")
    return path


def extract_pages(pdf: Path) -> list[str]:
    require_pdftotext()
    info = subprocess.run(
        ["pdfinfo", str(pdf)], check=True, capture_output=True, text=True
    ).stdout
    m = re.search(r"^Pages:\s+(\d+)", info, re.M)
    if not m:
        sys.exit("Could not determine page count.")
    n = int(m.group(1))
    pages = []
    for p in range(1, n + 1):
        out = subprocess.run(
            ["pdftotext", "-layout", "-f", str(p), "-l", str(p), str(pdf), "-"],
            check=True, capture_output=True, text=True,
        ).stdout
        pages.append(out)
    return pages


def classify(prefix: str) -> str:
    if prefix in VALVE_PREFIXES:
        return "valve"
    if prefix in INSTRUMENT_PREFIXES:
        return "instrument"
    return "equipment"


def normalize_tag(prefix: str, num: str, suffix: str) -> str:
    return f"53{prefix}-{num}{suffix or ''}"


def build_index(pages: list[str]) -> Index:
    idx = Index(pages=pages)
    by_tag: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for pi, text in enumerate(pages, start=1):
        lines = text.splitlines()
        for li, line in enumerate(lines, start=1):
            for m in RE_TAG.finditer(line):
                prefix, num, suffix = m.group(1), m.group(2), m.group(3) or ""
                tag = normalize_tag(prefix, num, suffix)
                cat = classify(prefix)
                by_tag[tag].append((pi, li))
                idx.categories[cat].add(tag)
            for m in RE_LINE.finditer(line):
                tag = m.group(0)
                by_tag[tag].append((pi, li))
                idx.categories["line"].add(tag)
            for m in RE_PID_REF.finditer(line):
                tag = m.group(0)
                by_tag[tag].append((pi, li))
                idx.categories["pid_ref"].add(tag)
    idx.by_tag = dict(by_tag)
    return idx


def cache_paths(pdf: Path) -> tuple[Path, Path]:
    CACHE_DIR.mkdir(exist_ok=True)
    stem = pdf.stem.replace(" ", "_")
    return CACHE_DIR / f"{stem}.pages.json", CACHE_DIR / f"{stem}.index.json"


def load_or_build(pdf: Path, refresh: bool = False) -> Index:
    pages_path, index_path = cache_paths(pdf)
    if not refresh and pages_path.exists() and index_path.exists():
        if pages_path.stat().st_mtime >= pdf.stat().st_mtime:
            pages = json.loads(pages_path.read_text())
            data = json.loads(index_path.read_text())
            idx = Index(pages=pages)
            idx.by_tag = {k: [tuple(v) for v in vs] for k, vs in data["by_tag"].items()}
            idx.categories = {k: set(v) for k, v in data["categories"].items()}
            return idx
    pages = extract_pages(pdf)
    idx = build_index(pages)
    pages_path.write_text(json.dumps(pages))
    index_path.write_text(json.dumps({
        "by_tag": idx.by_tag,
        "categories": {k: sorted(v) for k, v in idx.categories.items()},
    }))
    return idx


def snippet_for(idx: Index, page: int, line_no: int, query: str | None = None) -> str:
    lines = idx.pages[page - 1].splitlines()
    raw = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
    s = re.sub(r"\s{2,}", "  ", raw).strip()
    if len(s) > 160:
        if query:
            i = s.lower().find(query.lower())
            if i >= 0:
                start = max(0, i - 60)
                end = min(len(s), i + len(query) + 60)
                s = ("..." if start else "") + s[start:end] + ("..." if end < len(s) else "")
            else:
                s = s[:160] + "..."
        else:
            s = s[:160] + "..."
    return s


def cmd_search(idx: Index, args: argparse.Namespace) -> int:
    q = args.query
    needle = q if args.case else q.lower()
    hits: list[Hit] = []
    cats = set(args.category) if args.category else None
    if not args.text:
        # Tag-style search: prefer normalized tag match.
        for tag, locs in idx.by_tag.items():
            hay = tag if args.case else tag.lower()
            if needle in hay:
                cat = next((c for c, ts in idx.categories.items() if tag in ts), "?")
                if cats and cat not in cats:
                    continue
                for page, line_no in locs:
                    if args.page and page != args.page:
                        continue
                    hits.append(Hit(tag, cat, page, line_no,
                                    snippet_for(idx, page, line_no, q)))
    else:
        for pi, text in enumerate(idx.pages, start=1):
            if args.page and pi != args.page:
                continue
            for li, line in enumerate(text.splitlines(), start=1):
                hay = line if args.case else line.lower()
                if needle in hay:
                    hits.append(Hit("-", "text", pi, li,
                                    snippet_for(idx, pi, li, q)))
    if args.limit:
        hits = hits[: args.limit]
    if not hits:
        print(f"No matches for {q!r}.")
        return 1
    for h in hits:
        print(f"p{h.page:>3} L{h.line_no:>4}  [{h.category:<10}] {h.tag:<35} {h.snippet}")
    print(f"\n{len(hits)} match(es).")
    return 0


def cmd_list(idx: Index, args: argparse.Namespace) -> int:
    cat = args.category
    if cat not in idx.categories:
        print(f"Unknown category: {cat}. Choose from: {', '.join(sorted(idx.categories))}")
        return 2
    tags = sorted(idx.categories[cat])
    for t in tags:
        if args.with_pages:
            pages = sorted({p for p, _ in idx.by_tag.get(t, [])})
            print(f"{t:<35} pages: {','.join(map(str, pages))}")
        else:
            print(t)
    print(f"\n{len(tags)} {cat} tag(s).")
    return 0


def cmd_tags(idx: Index, _: argparse.Namespace) -> int:
    total = 0
    for cat in sorted(idx.categories):
        n = len(idx.categories[cat])
        total += n
        print(f"{cat:<12} {n}")
    print(f"{'total':<12} {total}")
    return 0


def cmd_info(idx: Index, args: argparse.Namespace) -> int:
    tag = args.tag
    if tag not in idx.by_tag:
        # Try fuzzy / normalized lookup.
        candidates = [t for t in idx.by_tag if tag.lower() in t.lower()]
        if not candidates:
            print(f"Tag not found: {tag}")
            return 1
        if len(candidates) > 1:
            print(f"Ambiguous, did you mean:")
            for c in candidates[:20]:
                print(f"  {c}")
            return 1
        tag = candidates[0]
    cat = next((c for c, ts in idx.categories.items() if tag in ts), "?")
    locs = idx.by_tag[tag]
    pages = sorted({p for p, _ in locs})
    print(f"tag      : {tag}")
    print(f"category : {cat}")
    print(f"pages    : {', '.join(map(str, pages))}")
    print(f"hits     : {len(locs)}")
    print()
    seen: set[tuple[int, int]] = set()
    for page, line_no in locs:
        key = (page, line_no)
        if key in seen:
            continue
        seen.add(key)
        print(f"p{page:>3} L{line_no:>4}  {snippet_for(idx, page, line_no, tag)}")
    return 0


def cmd_page(idx: Index, args: argparse.Namespace) -> int:
    n = args.page
    if not (1 <= n <= len(idx.pages)):
        print(f"Page {n} out of range (1..{len(idx.pages)}).")
        return 2
    text = idx.pages[n - 1]
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pid-zoektool", description=__doc__.splitlines()[0])
    p.add_argument("--pdf", default=DEFAULT_PDF, help="Path to P&ID PDF (default: %(default)s)")
    p.add_argument("--refresh", action="store_true", help="Rebuild cache")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("search", help="Search tags or full text")
    sp.add_argument("query")
    sp.add_argument("-t", "--text", action="store_true", help="Full-text search instead of tag search")
    sp.add_argument("-c", "--category", action="append",
                    help="Restrict to category (repeatable): equipment/valve/instrument/line/pid_ref")
    sp.add_argument("-p", "--page", type=int, help="Restrict to page")
    sp.add_argument("--case", action="store_true", help="Case-sensitive match")
    sp.add_argument("--limit", type=int, default=200)

    sp = sub.add_parser("list", help="List all tags in a category")
    sp.add_argument("category", choices=["equipment", "valve", "instrument", "line", "pid_ref"])
    sp.add_argument("--with-pages", action="store_true")

    sub.add_parser("tags", help="Show tag count per category")

    sp = sub.add_parser("info", help="Show details for a single tag")
    sp.add_argument("tag")

    sp = sub.add_parser("page", help="Print raw text of a page")
    sp.add_argument("page", type=int)

    args = p.parse_args(argv)
    pdf = Path(args.pdf)
    if not pdf.exists():
        sys.exit(f"PDF not found: {pdf}")
    idx = load_or_build(pdf, refresh=args.refresh)

    return {
        "search": cmd_search,
        "list": cmd_list,
        "tags": cmd_tags,
        "info": cmd_info,
        "page": cmd_page,
    }[args.cmd](idx, args)


if __name__ == "__main__":
    raise SystemExit(main())
