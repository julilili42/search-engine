
from __future__ import annotations
from dataclasses import field, dataclass
from typing import List, Dict
from pydantic import BaseModel, ConfigDict

# since we read from json, we need to validate the input
class CrawlSite(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, str_strip_whitespace=True)

    url: str = "https://www.tuepedia.de/"
    max_pages: int = 100
    request_timeout: float = 30.0
    retry_delay: float = 10.0
    request_delay: float = 0.01
    retries: int = 3


@dataclass
class Config:
    sites: List[CrawlSite] = field(default_factory=list)
    accept: str = "text/html"
    user_agent: str = "SimpleLinkCrawler/0.1"
    save_dir: str = "../data2"
    save_state_every: int = 10


@dataclass
class Statistics:
    fetched: int = 0
    discovered: int = 0
    failed: int = 0
    saved: int = 0

    def print(self) -> None:
        print(f"Fetched:    {self.fetched}")
        print(f"Discovered: {self.discovered}")
        print(f"Failed:     {self.failed}")
        print(f"Saved:      {self.saved}")

    def reset(self) -> None:
        self.fetched = 0
        self.discovered = 0
        self.failed = 0
        self.saved = 0

    def inc_fetched(self) -> None:
        self.fetched += 1

    def inc_discovered(self) -> None:
        self.discovered += 1

    def inc_failed(self) -> None:
        self.failed += 1

    def inc_saved(self) -> None:
        self.saved += 1


@dataclass
class CrawlState:
    queue: List[str] = field(default_factory=list)
    head: int = 0
    seen: Dict[str, bool] = field(default_factory=dict)
    index: Dict[str, str] = field(default_factory=dict)
    statistics: Statistics = field(default_factory=Statistics)

