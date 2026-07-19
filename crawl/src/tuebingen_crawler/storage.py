
from __future__ import annotations

import heapq
import json
import logging
import os
import threading
from dataclasses import asdict
from pathlib import Path
from .models import CrawlSite, CrawlState, Statistics
from .urls import normalize_host, origin, url_slug
from .frontier import count_frontier_hosts
import hashlib
import tomllib
import httpx
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


def _load_robots(client: httpx.Client, origin: str, url: str) -> RobotFileParser:
    robots_url = f"{origin}/robots.txt"

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


# robots.txt parsers and missing-sitemap logs, cached per origin
class RobotsCache:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client
        self._parsers: dict[str, RobotFileParser] = {}
        self._reported_missing_sitemaps: set[str] = set()
        self._lock = threading.Lock()

    def can_fetch(self, user_agent: str, url: str) -> bool:
        cached = self._cached_parser(url)
        if cached is None:
            return False
        _, parser = cached
        return parser.can_fetch(user_agent, url)

    def site_maps(self, url: str) -> list[str]:
        cached = self._cached_parser(url)
        if cached is None:
            return []
        origin, parser = cached
        site_maps = parser.site_maps() or []
        if site_maps:
            return site_maps
        with self._lock:
            if origin not in self._reported_missing_sitemaps:
                logger.info("No sitemap declared in robots.txt for %s", origin)
                self._reported_missing_sitemaps.add(origin)
        return []

    def _cached_parser(self, url: str) -> tuple[str, RobotFileParser] | None:
        site_origin = origin(url)
        if site_origin is None:
            return None
        with self._lock:
            parser = self._parsers.get(site_origin)
            if parser is None:
                parser = _load_robots(self._client, site_origin, url)
                self._parsers[site_origin] = parser
        return site_origin, parser


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


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp_path, path)


# saving of intermediate state
def save_crawl_state(path: Path, state: CrawlState) -> None:
    data = asdict(state)
    del data["seen_urls"], data["seen_texts"]
    data["seen_sitemaps"] = sorted(state.seen_sitemaps)
    _write_json(path, data)


def save_shared_state(path: Path, seen_urls: set[str], seen_texts: set[int]) -> None:
    _write_json(
        path,
        {
            "seen_urls": sorted(seen_urls),
            "seen_texts": sorted(seen_texts),
        },
    )

# shared deduplication state across all crawl hosts
def load_shared_state(path: Path) -> tuple[set[str], set[int]]:
    if not path.exists():
        logger.info("No shared state found %s.", path)
        return set(), set()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        state = TypeAdapter(CrawlState).validate_python(data)
        logger.info("Shared state was loaded successfully.")
        return state.seen_urls, state.seen_texts
    except Exception as exc:
        logger.error("Failed to load shared state %s.", exc)
        raise


# global crawl state, persisted between crawl runs
def load_crawl_state(path: Path) -> tuple[CrawlState, bool]:
    if not path.exists():
        logger.info("No intermediate state found %s.", path)
        return CrawlState(), False

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        state = TypeAdapter(CrawlState).validate_python(data)
        state.queued_urls_by_host = count_frontier_hosts(state.frontier)
        heapq.heapify(state.frontier)
        logger.info("Intermediate state was loaded successfully.")
        return state, True
    except Exception as exc:
        logger.error("Failed to load intermediate state %s.", exc)
        raise
