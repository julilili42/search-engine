
from __future__ import annotations
from dataclasses import field, dataclass
from pydantic import BaseModel, ConfigDict, Field
from pathlib import Path

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
    max_pages: int | None = None
    request_timeout: float = 30.0
    retry_delay: float = 10.0
    request_delay: float = 0.01
    retries: int = Field(default=3, ge=1)

@dataclass
class CrawlState:
    frontier: list[list[float, int, int]] = field(default_factory=list)
    seen_urls: set[str] = field(default_factory=set)
    seen_texts: set[int] = field(default_factory=set)
    counter: int = 0
    statistics: Statistics = field(default_factory=Statistics)

