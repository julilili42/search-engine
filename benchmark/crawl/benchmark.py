#!/usr/bin/env python3
"""Deterministically find predominantly German pages in a stored crawl."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sqlite3

from lingua import Language, LanguageDetectorBuilder
from selectolax.lexbor import LexborHTMLParser

MIN_WORDS = 20
GERMAN_SHARE = 0.50
DETECTOR = (
    LanguageDetectorBuilder.from_languages(Language.GERMAN, Language.ENGLISH)
    .with_low_accuracy_mode()
    .build()
)


def visible_text(html: bytes) -> str:
    tree = LexborHTMLParser(html)
    tree.strip_tags(["script", "style", "noscript", "template", "svg"], recursive=True)
    return " ".join(tree.body.text(separator=" ", strip=True).split()) if tree.body else ""


def classify(text: str) -> tuple[str, str, int, int, float | None]:
    counts: Counter[Language] = Counter()
    for segment in DETECTOR.detect_multiple_languages_of(text):
        counts[segment.language] += segment.word_count
    total = sum(counts.values())
    german = counts[Language.GERMAN]
    share = german / total if total else None
    dominant = counts.most_common(1)[0][0].iso_code_639_1.name.lower() if counts else "unknown"
    if total < MIN_WORDS:
        label = "uncertain"
    elif share >= GERMAN_SHARE:
        label = "german"
    else:
        label = "not_german"
    return label, dominant, total, german, share


def arguments() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=root / "data/db/pages.sqlite")
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "output")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    assert visible_text(b"<body>shown<script>hidden</script></body>") == "shown"
    assert classify("Das ist eine deutsche Seite über Tübingen. " * 10)[0] == "german"
    assert classify("This is an English page about Tübingen. " * 10)[0] == "not_german"
    args = arguments()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True).execute(
        "SELECT url, host, path FROM pages ORDER BY url"
    )
    counts: Counter[str] = Counter()
    missing = 0
    output = args.output / "pages.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "url",
                "host",
                "path",
                "label",
                "dominant_language",
                "classified_words",
                "german_words",
                "german_share",
            ]
        )
        for url, host, relative_path in rows:
            path = args.root / relative_path
            if not path.is_file():
                missing += 1
                writer.writerow([url, host, relative_path, "missing", "", 0, 0, ""])
                continue
            label, dominant, total, german, share = classify(visible_text(path.read_bytes()))
            counts[label] += 1
            writer.writerow(
                [
                    url,
                    host,
                    relative_path,
                    label,
                    dominant,
                    total,
                    german,
                    "" if share is None else f"{share:.6f}",
                ]
            )

    summary = {
        "database_sha256": sha256(args.database),
        "documents": sum(counts.values()) + missing,
        "labels": dict(sorted(counts.items())),
        "missing": missing,
        "rule": {
            "detector": f"lingua-language-detector {version('lingua-language-detector')}",
            "candidate_languages": ["de", "en"],
            "low_accuracy_mode": True,
            "minimum_classified_words": MIN_WORDS,
            "german_share_threshold": GERMAN_SHARE,
        },
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
