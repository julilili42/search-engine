
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

@dataclass(frozen=True)
class PageVerdict:
    language: Language
    relevance: float

    @property
    def keep(self) -> bool:
        return self.is_english and self.is_relevant

    @property
    def is_english(self) -> bool:
        return self.language is Language.EN

    @property
    def is_relevant(self) -> bool:
        return self.relevance >= REL_THRESHOLD

@dataclass(frozen=True)
class LinkVerdict:
    url: str
    score: float
    enqueue: bool

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

@dataclass
class CrawlState:
    frontier: list[list[float, int, int]] = field(default_factory=list)
    seen_urls: set[str] = field(default_factory=set)
    seen_texts: set[int] = field(default_factory=set)
    counter: int = 0
    statistics: Statistics = field(default_factory=Statistics)
