from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class PageRecord:
    url: str
    host: str
    path: Path
    status_code: int | None
    content_type: str | None
    content_hash: str | None
    fetched_at: str
    indexed_at: str | None


class PageLoad:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.con = sqlite3.connect(self.db_path)
        self.con.row_factory = sqlite3.Row

    @staticmethod
    def _row_to_page(row: sqlite3.Row) -> PageRecord:
        return PageRecord(
            url=row["url"],
            host=row["host"],
            path=Path(row["path"]),
            status_code=row["status_code"],
            content_type=row["content_type"],
            content_hash=row["content_hash"],
            fetched_at=row["fetched_at"],
            indexed_at=row["indexed_at"],
        )
    
    def get_page_by_file_path(self, path: Path) -> PageRecord | None:
        row = self.con.execute(
            """
            SELECT url, host, path, status_code, content_type,
                   content_hash, fetched_at, indexed_at
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
            """
            SELECT url, host, path, status_code, content_type,
                content_hash, fetched_at, indexed_at
            FROM pages
            WHERE content_type IS NULL OR content_type LIKE 'text/html%'
            ORDER BY id
            """
        )

        for row in rows:
            yield self._row_to_page(row)