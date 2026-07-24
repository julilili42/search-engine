
from __future__ import annotations
from dataclasses import field, dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    import httpx

    from .stores import LinkStore, PageStore
    from .storage import RobotsCache
    from .verdict_models import VerdictModels

MAX_SAVED_PAGES_PER_HOST = 2000
MAX_SAVED_PAGES = 60_000


class Language(StrEnum):
    EN = "en"
    DE = "de"
    UNKNOWN = "unknown"

@dataclass
class FetchResult:
    body: bytes | None
    status_code: int
    content_type: str
    cooldown_seconds: float = 0.0

@dataclass
class Config:
    sites: list[CrawlSite] = field(default_factory=list)
    accept: str = "text/html"
    user_agent: str = "Crawler/0.1"
    request_delay: float = 0.7
    request_timeout: float = 30.0
    retry_delay: float = 10.0
    retries: int = 2
    save_dir: Path = field(default_factory=lambda: Path("data"))
    state_dir: Path | None = None
    # Seconds between resumable crawl-state checkpoints. Zero disables them.
    save_state_every: float = 300.0
    max_pages: int | None = MAX_SAVED_PAGES
    # Saved-page limit per host; None = unlimited.
    max_pages_per_host: int | None = MAX_SAVED_PAGES_PER_HOST

@dataclass
class Statistics:
    fetched: int = 0
    discovered: int = 0
    failed: int = 0
    saved: int = 0

# since we read from json, we need to validate the input
class CrawlSite(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, str_strip_whitespace=True)

    url: str

@dataclass(order=True)
class FrontierEntry:
    heap_priority: float
    sequence: int
    url: str = field(compare=False)
    depth: int = field(compare=False)
    seed_index: int = field(default=0, compare=False)


@dataclass(frozen=True)
class CrawlLease:
    entry: FrontierEntry
    host: str
    claimed_at: float


@dataclass
class CrawlState:
    frontier: list[FrontierEntry] = field(default_factory=list)
    seen_urls: set[str] = field(default_factory=set)
    seen_texts: set[int] = field(default_factory=set)
    seen_sitemaps: set[str] = field(default_factory=set)
    # limits amount of same host pushes
    queued_urls_by_host: dict[str, int] = field(default_factory=dict)
    counter: int = 0
    statistics: Statistics = field(default_factory=Statistics)


@dataclass
class CrawlContext:
    config: Config
    client: httpx.Client
    state: CrawlState
    page_store: PageStore
    link_store: LinkStore
    robots: RobotsCache
    host_counts: dict[str, int]
    host_reject_counts: dict[str, int]
    verdict_models: VerdictModels
