from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path
from collections.abc import Sequence
from typing import Any

from .paths import DEFAULT_DB_PATH


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _table_columns(con: sqlite3.Connection, name: str) -> set[str]:
    return {row["name"] for row in con.execute(f"PRAGMA table_info({name})").fetchall()}


def _entropy_bits(counts: list[int]) -> float:
    total = sum(counts)
    if total == 0:
        return 0.0
    return -sum((count / total) * math.log2(count / total) for count in counts if count > 0)


def _diversity_at_n(con: sqlite3.Connection, n: int) -> int:
    rows = con.execute("SELECT host FROM pages ORDER BY id LIMIT ?", (n,)).fetchall()
    return len({row["host"] for row in rows})


def _rejection_reasons(con: sqlite3.Connection) -> dict[str, int]:
    if not _table_exists(con, "rejected_pages"):
        return {}
    return {
        row["exclusion_reason"]: row["count"]
        for row in con.execute(
            """
            SELECT exclusion_reason, COUNT(*) AS count
            FROM rejected_pages
            GROUP BY exclusion_reason
            ORDER BY count DESC
            """
        )
    }


def _depth_distribution(con: sqlite3.Connection) -> dict[int, int]:
    return {
        int(row["crawl_depth"]): row["count"]
        for row in con.execute(
            """
            SELECT crawl_depth, COUNT(*) AS count
            FROM pages
            GROUP BY crawl_depth
            ORDER BY crawl_depth
            """
        )
        if row["crawl_depth"] is not None
    }


def _link_frontier_report(con: sqlite3.Connection) -> dict[str, Any] | None:
    if not _table_exists(con, "link_candidates"):
        return None

    columns = _table_columns(con, "link_candidates")
    selected = con.execute(
        "SELECT COUNT(*) AS count FROM link_candidates WHERE selected = 1"
    ).fetchone()["count"]
    same_host = con.execute(
        """
        SELECT COUNT(*) AS count
        FROM link_candidates
        WHERE selected = 1 AND parent_host = target_host
        """
    ).fetchone()["count"]

    report: dict[str, Any] = {
        "enqueued": selected,
        "same_host_share": round(same_host / selected, 4) if selected else None,
    }

    if "target_status" in columns:
        fetched_selected = con.execute(
            """
            SELECT COUNT(*) AS count
            FROM link_candidates
            WHERE selected = 1 AND target_status IS NOT NULL
            """
        ).fetchone()["count"]
        saved_selected = con.execute(
            """
            SELECT COUNT(*) AS count
            FROM link_candidates
            WHERE selected = 1 AND target_status = 'page'
            """
        ).fetchone()["count"]
        report["enqueued_fetched"] = fetched_selected
        report["precision_at_enqueue"] = (
            round(saved_selected / fetched_selected, 4) if fetched_selected else None
        )

    return report


def crawl_report(db_path: Path) -> dict[str, Any]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        saved = con.execute("SELECT COUNT(*) AS count FROM pages").fetchone()["count"]
        rejected = (
            con.execute("SELECT COUNT(*) AS count FROM rejected_pages").fetchone()["count"]
            if _table_exists(con, "rejected_pages")
            else 0
        )
        fetched = saved + rejected
        rejection_reasons = _rejection_reasons(con)
        depth_distribution = _depth_distribution(con)

        host_rows = con.execute(
            """
            SELECT host, COUNT(*) AS count
            FROM pages
            GROUP BY host
            ORDER BY count DESC
            """
        ).fetchall()
        host_counts = [row["count"] for row in host_rows]
        distinct_hosts = len(host_rows)
        entropy = _entropy_bits(host_counts)
        max_entropy = math.log2(distinct_hosts) if distinct_hosts > 1 else 1.0

        report: dict[str, Any] = {
            "db": str(db_path),
            "fetched": fetched,
            "saved": saved,
            "rejected": rejected,
            "harvest_rate": round(saved / fetched, 4) if fetched else 0.0,
            "rejection_reasons": rejection_reasons,
            "duplicate_rate": (
                round(rejection_reasons.get("duplicate_text", 0) / fetched, 4)
                if fetched
                else 0.0
            ),
            "depth_distribution": depth_distribution,
            "deep_share_ge3": (
                round(sum(count for depth, count in depth_distribution.items() if depth >= 3) / saved, 4)
                if saved
                else 0.0
            ),
            "distinct_hosts": distinct_hosts,
            "host_entropy_bits": round(entropy, 3),
            "host_evenness": round(entropy / max_entropy, 4) if max_entropy else 0.0,
            "diversity_at_50": _diversity_at_n(con, 50),
            "diversity_at_100": _diversity_at_n(con, 100),
            "top_hosts": [(row["host"], row["count"]) for row in host_rows[:12]],
        }

        link_frontier = _link_frontier_report(con)
        if link_frontier is not None:
            report["link_frontier"] = link_frontier
        return report
    finally:
        con.close()


def format_report(report: dict[str, Any]) -> str:
    lines = [
        f"Crawl report: {report['db']}",
        "-" * 60,
        f"Fetched:        {report['fetched']}",
        f"Saved:          {report['saved']}  (harvest {report['harvest_rate']:.1%})",
        f"Rejected:       {report['rejected']}",
        f"Duplicate rate: {report['duplicate_rate']:.1%}",
        "",
        "Rejection reasons:",
    ]
    lines.extend(
        f"  {reason:24s} {count}"
        for reason, count in report["rejection_reasons"].items()
    )
    lines.extend(
        [
            "",
            f"Distinct hosts: {report['distinct_hosts']}   "
            f"entropy {report['host_entropy_bits']} bits "
            f"(evenness {report['host_evenness']:.2f})",
            f"Diversity@50:   {report['diversity_at_50']}    "
            f"Diversity@100: {report['diversity_at_100']}",
            f"Deep share (depth>=3): {report['deep_share_ge3']:.1%}",
            "",
            "Depth distribution (saved):",
        ]
    )
    lines.extend(
        f"  depth {depth}: {count}"
        for depth, count in report["depth_distribution"].items()
    )
    lines.extend(["", "Top hosts (saved):"])
    lines.extend(f"  {host:40s} {count}" for host, count in report["top_hosts"])

    if "link_frontier" in report:
        link_frontier = report["link_frontier"]
        same_host_share = link_frontier["same_host_share"]
        lines.extend(
            [
                "",
                "Link frontier:",
                f"  enqueued:            {link_frontier['enqueued']}",
                "  same-host share:     "
                f"{'n/a' if same_host_share is None else f'{same_host_share:.1%}'}",
            ]
        )
        if "precision_at_enqueue" in link_frontier:
            precision = link_frontier["precision_at_enqueue"]
            lines.append(
                "  precision@enqueue:   "
                f"{'n/a' if precision is None else f'{precision:.1%}'} "
                f"(of {link_frontier['enqueued_fetched']} fetched)"
            )

    return "\n".join(lines)


def report_main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="crawl report",
        description="Report crawl quality from pages.sqlite",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    report = crawl_report(args.db)
    print(format_report(report))
    if args.json is not None:
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
