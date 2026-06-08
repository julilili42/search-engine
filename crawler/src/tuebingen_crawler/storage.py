
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Tuple
from .models import CrawlState, Statistics

# saving of intermediate state
def save_state(path: str | Path, state: CrawlState) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(asdict(state), indent=1), encoding="utf-8")
    os.replace(tmp_path, path)

# loading of intermediate state, to continue crawling process where it was stopped
def load_state(path: str | Path) -> Tuple[CrawlState, bool]:
    path = Path(path)
    if not path.exists():
        print(f"INFO: no intermediate state found {path}.")
        return CrawlState(), False

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        state = CrawlState(
            queue=data.get("queue", []),
            head=data.get("head", 0),
            seen=data.get("seen", {}),
            index=data.get("index", {}),
            statistics=Statistics(**data.get("statistics", {})),
        )
        print("INFO: intermediate state was loaded successfully.")
        return state, True
    except Exception as exc:
        print(f"ERROR: failed to load intermediate state {exc}, start with new state.")
        raise