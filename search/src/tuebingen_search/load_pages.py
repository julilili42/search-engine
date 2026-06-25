from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

_BASE_PAGE_COLUMNS = (
    "title",
    "url",
    "host",
    "path",
    "status_code",
    "content_type",
)
_DEBUG_PAGE_COLUMNS = (
    "crawl_depth",
    "language",
    "relevance",
    "token_count",
)
_TIMESTAMP_PAGE_COLUMNS = (
    "fetched_at",
    "indexed_at",
)
_PAGE_COLUMNS = ", ".join(
    (*_BASE_PAGE_COLUMNS, *_DEBUG_PAGE_COLUMNS, *_TIMESTAMP_PAGE_COLUMNS)
)


@dataclass(frozen=True)
class PageRecord:
    title: str
    url: str
    host: str
    path: Path | None
    status_code: int | None
    content_type: str | None
    crawl_depth: int | None
    language: str | None
    relevance: float | None
    token_count: int | None
    fetched_at: str
    indexed_at: str | None
    exclusion_reason: str | None = None


class PageLoad:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.con = sqlite3.connect(self.db_path)
        self.con.row_factory = sqlite3.Row

    @staticmethod
    def _row_to_page(row: sqlite3.Row) -> PageRecord:
        path = row["path"]
        return PageRecord(
            title=row["title"],
            url=row["url"],
            host=row["host"],
            path=Path(path) if path is not None else None,
            status_code=row["status_code"],
            content_type=row["content_type"],
            crawl_depth=row["crawl_depth"],
            language=row["language"],
            relevance=row["relevance"],
            token_count=row["token_count"],
            fetched_at=row["fetched_at"],
            indexed_at=row["indexed_at"],
        )

    def get_page_by_file_path(self, path: Path) -> PageRecord | None:
        row = self.con.execute(
            f"""
            SELECT {_PAGE_COLUMNS}
            FROM pages
            WHERE path = ?
            """,
            (str(path),),
        ).fetchone()

        if row is None:
            return None

        return self._row_to_page(row)

    def iter_html_pages(self) -> Iterator[PageRecord]:
        rows = self.con.execute(
            f"""
            SELECT {_PAGE_COLUMNS}
            FROM pages
            WHERE content_type IS NULL OR content_type LIKE 'text/html%'
            ORDER BY id
            """
        )

        for row in rows:
            yield self._row_to_page(row)
