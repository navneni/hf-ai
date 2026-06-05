"""
One-time utility: build config/moat_idf.json from a corpus of annual reports.

Usage:
    python scripts/build_moat_idf.py --corpus-dir /path/to/10k-texts/

The corpus directory should contain .txt files, one per annual report.
If run without a corpus, writes the default pre-computed weights to config/moat_idf.json.
"""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path

MOAT_KEYWORDS = [
    "switching cost", "switching costs", "lock-in", "mission-critical",
    "network effect", "network effects", "two-sided", "ecosystem",
    "marketplace", "platform", "lowest cost", "cost leadership",
    "scale advantage", "cost advantage", "trade secret", "trade secrets",
    "proprietary technology", "patent", "patents", "brand loyalty",
    "brand recognition", "regulatory approval", "fda clearance",
    "fcc license", "exclusive", "exclusive license", "proprietary",
    "integrated", "intangible", "intangible assets",
]

DEFAULT_WEIGHTS = {
    "switching cost": 3.8, "switching costs": 3.8, "lock-in": 3.6,
    "mission-critical": 3.5, "network effect": 4.0, "network effects": 4.0,
    "two-sided": 4.2, "ecosystem": 2.8, "marketplace": 2.3, "platform": 2.0,
    "lowest cost": 3.2, "cost leadership": 3.5, "scale advantage": 3.4,
    "cost advantage": 3.3, "trade secret": 3.8, "trade secrets": 3.8,
    "proprietary technology": 3.2, "patent": 2.5, "patents": 2.5,
    "brand loyalty": 3.0, "brand recognition": 2.8, "regulatory approval": 3.0,
    "fda clearance": 4.0, "fcc license": 4.2, "exclusive": 2.5,
    "exclusive license": 3.5, "proprietary": 2.2, "integrated": 1.8,
    "intangible": 2.0, "intangible assets": 2.5,
}

OUT_PATH = Path(__file__).parent.parent / "config" / "moat_idf.json"


def compute_from_corpus(corpus_dir: str) -> dict[str, float]:
    texts = list(Path(corpus_dir).glob("*.txt"))
    if not texts:
        print("No .txt files found. Writing defaults.")
        return DEFAULT_WEIGHTS

    N = len(texts)
    doc_freq: dict[str, int] = {kw: 0 for kw in MOAT_KEYWORDS}

    for path in texts:
        text = path.read_text(errors="ignore").lower()
        for kw in MOAT_KEYWORDS:
            if kw in text:
                doc_freq[kw] += 1

    idf = {}
    for kw in MOAT_KEYWORDS:
        df = max(doc_freq[kw], 1)
        idf[kw] = round(math.log(N / df) + 1, 4)

    print(f"Computed IDF from {N} documents.")
    return idf


def main():
    parser = argparse.ArgumentParser(description="Build moat IDF weights.")
    parser.add_argument("--corpus-dir", default=None)
    args = parser.parse_args()

    if args.corpus_dir:
        weights = compute_from_corpus(args.corpus_dir)
    else:
        print("No corpus dir provided. Writing default pre-computed weights.")
        weights = DEFAULT_WEIGHTS

    OUT_PATH.write_text(json.dumps(weights, indent=2))
    print(f"Written to {OUT_PATH}")


if __name__ == "__main__":
    main()
