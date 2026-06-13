
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Tuple, List
from .models import CrawlState, Statistics, CrawlSite
import hashlib
import tomllib
import httpx
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from pydantic import TypeAdapter, ValidationError

logger = logging.getLogger(__name__)

# before we crawl a url we have to load the `robots.txt` file
def load_robots(client: httpx.Client, site: CrawlSite) -> RobotFileParser:
    parsed = urlparse(site.url)

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid site URL: {site.url}")
    
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    parser = RobotFileParser()
    parser.set_url(robots_url)

    try:
        response = client.get(robots_url, timeout=5.0, follow_redirects=True)
        if response.status_code == 404:
                parser.parse([])
                return parser

        response.raise_for_status()
        parser.parse(response.text.splitlines())
        return parser

    except httpx.RequestError as exc:
        logger.warning("Could not fetch robots.txt for %s: %s", site.url, exc)
        parser.parse([])
        return parser

# load and validate seed toml list
def load_seed_toml(path: Path) -> List[CrawlSite]:
    seed_adapter = TypeAdapter(List[CrawlSite])
    try:
        toml_text = path.read_text(encoding="utf-8")
        data = tomllib.loads(toml_text)
        entries = seed_adapter.validate_python(data["sites"])
        return entries
    except ValidationError as exc:
        logger.error("Invalid TOML seed entries: %s", exc)
        return []
    except KeyError:
        logger.error("TOML seed list must contain a 'sites' field")
        return []
    except tomllib.TOMLDecodeError as exc:
        logger.error("Invalid TOML seed list: %s", exc)
        return []
    except FileNotFoundError:
        logger.error("TOML seed list not found")
        return []

# creates unique state path, s.t. multiple hostnames can be distinguished
def generate_state_path(save_dir: Path, host: str, canonical_start_url: str) -> Path:
    digest = hashlib.sha256(canonical_start_url.encode("utf-8")).hexdigest()[:12]
    return save_dir / host / f"crawl_state-{digest}.json"

# saving of crawling progress dependend on save_state_every, wrapper around `save_state`
def maybe_save_state(
    save_state_every: int,
    state_path: Path,
    state: CrawlState
) -> None:
    if save_state_every <= 0:
        return

    if state.head % save_state_every == 0:
        save_state(state_path, state)

# saving of intermediate state
def save_state(path: Path, state: CrawlState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(asdict(state), indent=1), encoding="utf-8")
    os.replace(tmp_path, path)

# loading of intermediate state, to continue crawling process where it was stopped
def load_state(path: Path) -> Tuple[CrawlState, bool]:
    path = Path(path)
    if not path.exists():
        logger.info("No intermediate state found %s.", path)
        return CrawlState(), False

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        state = CrawlState(
            queue=data.get("queue", []),
            head=data.get("head", 0),
            seen=data.get("seen", {}),
            statistics=Statistics(**data.get("statistics", {})),
        )
        logger.info("Intermediate state was loaded successfully.")
        return state, True
    except Exception as exc:
        logger.error("Failed to load intermediate state %s.", exc)
        raise