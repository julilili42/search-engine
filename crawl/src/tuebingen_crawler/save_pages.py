from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
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

# used to store informations (`PageRecord`) about crawled pages in sqlite database
class PageStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.db_path)
        self.con.row_factory = sqlite3.Row

        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA foreign_keys=ON")

        self.init_schema()

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> "PageStore":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def init_schema(self) -> None:
        self.con.execute(
            """
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY,
                url TEXT NOT NULL UNIQUE,
                host TEXT NOT NULL,
                path TEXT NOT NULL,
                status_code INTEGER,
                content_type TEXT,
                content_hash TEXT,
                fetched_at TEXT NOT NULL,
                indexed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        self.con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pages_host
            ON pages(host)
            """
        )

        self.con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pages_path
            ON pages(path)
            """
        )

        self.con.commit()

    def upsert_page(
        self,
        *,
        url: str,
        host: str,
        path: str | Path,
        status_code: int | None = None,
        content_type: str | None = None,
        content_hash: str | None = None,
        fetched_at: str | None = None,
    ) -> None:
        now = self._now()
        fetched_at = fetched_at or now

        with self.con:
            self.con.execute(
                """
                INSERT INTO pages (
                    url,
                    host,
                    path,
                    status_code,
                    content_type,
                    content_hash,
                    fetched_at,
                    indexed_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    host = excluded.host,
                    path = excluded.path,
                    status_code = excluded.status_code,
                    content_type = excluded.content_type,
                    content_hash = excluded.content_hash,
                    fetched_at = excluded.fetched_at,
                    updated_at = excluded.updated_at
                """,
                (
                    url,
                    host,
                    str(path),
                    status_code,
                    content_type,
                    content_hash,
                    fetched_at,
                    now,
                    now,
                ),
            )

    def mark_indexed(self, url: str) -> None:
        now = self._now()

        with self.con:
            self.con.execute(
                """
                UPDATE pages
                SET indexed_at = ?, updated_at = ?
                WHERE url = ?
                """,
                (now, now, url),
            )

    def get_page_by_url(self, url: str) -> PageRecord | None:
        row = self.con.execute(
            """
            SELECT url, host, path, status_code, content_type,
                   content_hash, fetched_at, indexed_at
            FROM pages
            WHERE url = ?
            """,
            (url,),
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

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()