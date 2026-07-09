from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .metrics import Metrics


def crawl_id(db_path: Path) -> str:
    timestamp = datetime.fromtimestamp(db_path.stat().st_mtime)
    return "crawl-" + timestamp.strftime("%Y%m%d-%H%M")


def slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-")
    return text or "run"


def save_run(
    *,
    runs_dir: Path,
    db_path: Path,
    index_path: Path,
    queries_path: Path,
    qrels_path: Path,
    top_n: int,
    metrics: Metrics,
    name: str,
) -> Path:
    crawl = crawl_id(db_path)
    run_dir = runs_dir / crawl
    run_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = run_dir / f"{timestamp}-{slug(name)}.json"
    payload = {
        "name": name,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "crawl": crawl,
        "db_path": str(db_path),
        "index_path": str(index_path),
        "queries_path": str(queries_path),
        "qrels_path": str(qrels_path),
        "top_n": top_n,
        "metrics": asdict(metrics),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_run(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_runs(runs_dir: Path, count: int = 2) -> list[Path]:
    return sorted(runs_dir.glob("crawl-*/*.json"), key=lambda path: path.stat().st_mtime)[-count:]
