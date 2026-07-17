
from __future__ import annotations

import heapq
import json
import logging
import os
import threading
from dataclasses import asdict
from pathlib import Path
from .models import CrawlSite, CrawlState, FrontierEntry, Statistics
from .urls import normalize_host, url_slug
from .frontier import count_frontier_hosts
import hashlib
import tomllib
import httpx
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from pydantic import TypeAdapter, ValidationError

logger = logging.getLogger(__name__)


def save_html(hostname: str, base_dir: Path, page_url: str, body: bytes) -> str:
    digest = hashlib.sha256(page_url.encode("utf-8")).hexdigest()[:8]
    file_name = f"{digest}-{url_slug(page_url)}.html"

    directory = base_dir / normalize_host(hostname)
    directory.mkdir(parents=True, exist_ok=True)

    path = directory / file_name
    path.write_bytes(body)
    return str(path)


# loads the `robots.txt` covering `url` and returns its parser
def load_robots(client: httpx.Client, url: str) -> RobotFileParser:
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid site URL: {url}")

    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    parser = RobotFileParser()
    parser.set_url(robots_url)

    try:
        response = client.get(robots_url, timeout=5.0, follow_redirects=True)
        if response.is_success:
            parser.parse(response.text.splitlines())
        else:
            logger.warning(
                "robots.txt for %s returned %s; allowing all",
                url,
                response.status_code,
            )
            parser.parse([])
        return parser

    except (httpx.RequestError, httpx.InvalidURL, UnicodeError) as exc:
        logger.warning("Could not fetch robots.txt for %s: %s", url, exc)
        parser.parse([])
        return parser


# robots.txt parsers per origin, shared across all seeds and threads
class RobotsCache:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client
        self._parsers: dict[str, RobotFileParser] = {}
        self._reported_missing_sitemaps: set[str] = set()
        self._lock = threading.Lock()

    def can_fetch(self, user_agent: str, url: str) -> bool:
        parser = self._parser_for(url)
        return parser is not None and parser.can_fetch(user_agent, url)

    def site_maps(self, url: str) -> list[str]:
        parser = self._parser_for(url)
        if parser is None:
            return []
        site_maps = parser.site_maps() or []
        if site_maps:
            return site_maps
        origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        with self._lock:
            if origin not in self._reported_missing_sitemaps:
                logger.info("No sitemap declared in robots.txt for %s", origin)
                self._reported_missing_sitemaps.add(origin)
        return []

    def _parser_for(self, url: str) -> RobotFileParser | None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        origin = f"{parsed.scheme}://{parsed.netloc}"
        with self._lock:
            parser = self._parsers.get(origin)
            if parser is None:
                parser = load_robots(self._client, url)
                self._parsers[origin] = parser
        return parser


# load and validate seed toml list
def load_seed_toml(path: Path) -> list[CrawlSite]:
    seed_adapter = TypeAdapter(list[CrawlSite])
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


def generate_global_state_path(state_dir: Path) -> Path:
    return state_dir / "state" / "global_frontier.json"


def generate_global_shared_state_path(state_dir: Path) -> Path:
    return state_dir / "state" / "global_seen.json"


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp_path, path)


# saving of intermediate state
def save_state(path: Path, state: CrawlState) -> None:
    data = {
        "frontier": [asdict(entry) for entry in state.frontier],
        "queued_urls_by_host": dict(state.queued_urls_by_host),
        "counter": state.counter,
        "statistics": asdict(state.statistics),
        "seen_sitemaps": sorted(state.seen_sitemaps),
        "seed_statistics": {
            str(seed_index): asdict(statistics)
            for seed_index, statistics in state.seed_statistics.items()
        },
    }
    _write_json(path, data)


def save_shared_state(path: Path, seen_urls: set[str], seen_texts: set[int]) -> None:
    _write_json(
        path,
        {
            "seen_urls": sorted(seen_urls.copy()),
            "seen_texts": sorted(seen_texts.copy()),
        },
    )


def load_shared_state(path: Path) -> tuple[set[str], set[int]]:
    if not path.exists():
        return set(), set()

    data = json.loads(path.read_text(encoding="utf-8"))
    seen_urls = {url for url in data.get("seen_urls", []) if isinstance(url, str)}
    seen_texts = {fingerprint for fingerprint in data.get("seen_texts", []) if isinstance(fingerprint, int)}
    return seen_urls, seen_texts


# loading of intermediate state, to continue crawling process where it was stopped
def load_state(path: Path) -> tuple[CrawlState, bool]:
    path = Path(path)
    if not path.exists():
        logger.info("No intermediate state found %s.", path)
        return CrawlState(), False

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        frontier = [_frontier_entry(entry) for entry in data.get("frontier", [])]
        heapq.heapify(frontier)
        seen_texts = {
            fingerprint
            for fingerprint in data.get("seen_texts", [])
            if isinstance(fingerprint, int)
        }
        state = CrawlState(
            frontier=frontier,
            seen_urls=set(data.get("seen_urls", [])),
            seen_texts=seen_texts,
            seen_sitemaps={
                sitemap for sitemap in data.get("seen_sitemaps", []) if isinstance(sitemap, str)
            },
            queued_urls_by_host=count_frontier_hosts(frontier),
            counter=data.get("counter", 0),
            statistics=Statistics(**data.get("statistics", {})),
            seed_statistics={
                int(seed_index): Statistics(**statistics)
                for seed_index, statistics in data.get("seed_statistics", {}).items()
                if isinstance(statistics, dict)
            },
        )
        logger.info("Intermediate state was loaded successfully.")
        return state, True
    except Exception as exc:
        logger.error("Failed to load intermediate state %s.", exc)
        raise


def _frontier_entry(entry: object) -> FrontierEntry:
    if isinstance(entry, dict):
        return FrontierEntry(
            heap_priority=float(entry["heap_priority"]),
            sequence=int(entry["sequence"]),
            url=str(entry["url"]),
            depth=int(entry["depth"]),
            seed_index=int(entry.get("seed_index", 0)),
        )

    if isinstance(entry, (list, tuple)) and len(entry) in {4, 5}:
        heap_priority, sequence, url, depth, *rest = entry
        return FrontierEntry(
            heap_priority=float(heap_priority),
            sequence=int(sequence),
            url=str(url),
            depth=int(depth),
            seed_index=int(rest[0]) if rest else 0,
        )

    raise ValueError(f"Invalid frontier entry: {entry!r}")
