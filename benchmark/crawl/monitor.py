"""Read-only crawl metrics monitor."""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = REPO_ROOT / "data" / "db" / "pages.sqlite"
DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "metrics"
TOP_N = 8


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def snapshot(db_path: Path, watermarks: dict[str, int]) -> dict:
    conn = _connect(db_path)
    try:
        accepted_total = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        rejected_total = conn.execute("SELECT COUNT(*) FROM rejected_pages").fetchone()[0]
        max_page_id = conn.execute("SELECT COALESCE(MAX(id),0) FROM pages").fetchone()[0]
        max_reject_id = conn.execute("SELECT COALESCE(MAX(id),0) FROM rejected_pages").fetchone()[0]

        new_pages = conn.execute(
            "SELECT host, crawl_depth, pageverdict_score FROM pages WHERE id > ?",
            (watermarks.get("page", max_page_id),),
        ).fetchall() if "page" in watermarks else []
        new_rejects = conn.execute(
            "SELECT host, exclusion_reason, pageverdict_score FROM rejected_pages WHERE id > ?",
            (watermarks.get("reject", max_reject_id),),
        ).fetchall() if "reject" in watermarks else []

        pending = conn.execute(
            "SELECT COUNT(*) FROM link_candidates "
            "WHERE target_status IS NULL OR target_status = ''"
        ).fetchone()[0]
        distinct_hosts = conn.execute("SELECT COUNT(DISTINCT host) FROM pages").fetchone()[0]
        top_hosts_cum = conn.execute(
            "SELECT host, COUNT(*) c FROM pages GROUP BY host ORDER BY c DESC LIMIT ?", (TOP_N,)
        ).fetchall()
    finally:
        conn.close()

    watermarks["page"] = max_page_id
    watermarks["reject"] = max_reject_id

    window_total = len(new_pages) + len(new_rejects)
    model_reject_scores = [
        r["pageverdict_score"] for r in new_rejects
        if r["exclusion_reason"] == "low_pageverdict_score" and r["pageverdict_score"] is not None
    ]
    accept_scores = [p["pageverdict_score"] for p in new_pages if p["pageverdict_score"] is not None]

    return {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "accepted_total": accepted_total,
        "rejected_total": rejected_total,
        "accept_rate_cum": round(accepted_total / (accepted_total + rejected_total), 4)
        if accepted_total + rejected_total else None,
        "distinct_accept_hosts": distinct_hosts,
        "top_hosts_cum": {r["host"]: r["c"] for r in top_hosts_cum},
        "frontier_pending_links": pending,
        "window": {
            "accepts": len(new_pages),
            "rejects": len(new_rejects),
            "accept_rate": round(len(new_pages) / window_total, 4) if window_total else None,
            "accepts_by_host": dict(Counter(p["host"] for p in new_pages).most_common(TOP_N)),
            "rejects_by_reason": dict(Counter(r["exclusion_reason"] for r in new_rejects)),
            "reject_hosts_top": dict(Counter(r["host"] for r in new_rejects).most_common(TOP_N)),
            "avg_accept_score": round(sum(accept_scores) / len(accept_scores), 3)
            if accept_scores else None,
            "avg_accept_depth": round(sum(p["crawl_depth"] for p in new_pages) / len(new_pages), 2)
            if new_pages else None,
            "avg_model_reject_score": round(sum(model_reject_scores) / len(model_reject_scores), 3)
            if model_reject_scores else None,
        },
    }

def status(db_path: Path, window_seconds: int) -> dict:
    watermarks: dict[str, int] = {}
    snapshot(db_path, watermarks)
    time.sleep(window_seconds)
    row = snapshot(db_path, watermarks)
    row["window_seconds"] = window_seconds
    win = row["window"]
    rate = (win["accepts"] + win["rejects"]) / window_seconds if window_seconds else 0
    row["crawler_active"] = rate > 0
    row["pages_per_minute"] = round(rate * 60, 1)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--status", action="store_true",
                        help="Live-Zustand als JSON ausgeben und beenden")
    parser.add_argument("--window", type=int, default=15,
                        help="Messfenster fuer --status in Sekunden")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(status(args.db, args.window), indent=1, ensure_ascii=False))
        return

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"metrics-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    print(f"schreibe Snapshots nach {out_path}")

    watermarks: dict[str, int] = {}
    while True:
        try:
            row = snapshot(args.db, watermarks)
            with out_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"{row['ts']} accepted={row['accepted_total']} "
                  f"window_accept_rate={row['window']['accept_rate']}")
        except sqlite3.OperationalError as exc:
            print(f"Snapshot übersprungen (DB busy?): {exc}")
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
