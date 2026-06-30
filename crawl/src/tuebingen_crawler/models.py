
from __future__ import annotations
from dataclasses import field, dataclass
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field
from pathlib import Path


class Language(StrEnum):
    EN = "en"
    DE = "de"
    UNKNOWN = "unknown"

# score at which a page is relevant
REL_THRESHOLD = 3.0

@dataclass
class FetchResult:
    body: bytes | None
    status_code: int
    content_type: str

@dataclass
class Config:
    sites: list[CrawlSite] = field(default_factory=list)
    accept: str = "text/html"
    user_agent: str = "SimpleLinkCrawler/0.1"
    save_dir: Path = field(default_factory=lambda: Path("data"))
    save_state_every: int = 10
    # global diversity cap on saved pages per host; None = unlimited
    max_pages_per_host: int | None = None

@dataclass
class Statistics:
    fetched: int = 0
    discovered: int = 0
    failed: int = 0
    saved: int = 0

    # TODO: replace print with logging
    def print(self) -> None:
        print(f"Fetched:    {self.fetched}")
        print(f"Discovered: {self.discovered}")
        print(f"Failed:     {self.failed}")
        print(f"Saved:      {self.saved}")

# since we read from json, we need to validate the input
class CrawlSite(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, str_strip_whitespace=True)

    url: str
    max_pages_per_seed: int | None = None
    request_timeout: float = 30.0
    retry_delay: float = 10.0
    request_delay: float = 0.01
    retries: int = Field(default=2, ge=1)
    # pages per scheduler round: 1 = neutral.
    round_robin_weight: int = Field(default=1, ge=1)

@dataclass(order=True)
class FrontierEntry:
    heap_priority: float
    sequence: int
    url: str = field(compare=False)
    depth: int = field(compare=False)

@dataclass
class CrawlState:
    frontier: list[FrontierEntry] = field(default_factory=list)
    seen_urls: set[str] = field(default_factory=set)
    seen_texts: set[int] = field(default_factory=set)
    # limits amount of same host pops
    recent_pop_hosts: list[str] = field(default_factory=list)
    # limits amount of same host pushes
    queued_urls_by_host: dict[str, int] = field(default_factory=dict)
    counter: int = 0
    statistics: Statistics = field(default_factory=Statistics)
