from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
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
_REJECTED_PAGE_COLUMNS = ", ".join(
    (
        "title",
        "url",
        "host",
        "NULL AS path",
        "status_code",
        "content_type",
        *_DEBUG_PAGE_COLUMNS,
        "fetched_at",
        "NULL AS indexed_at",
        "exclusion_reason",
    )
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


# used to store informations PageRecord about crawled pages in sqlite database
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
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                host TEXT NOT NULL,
                path TEXT NOT NULL,
                status_code INTEGER,
                content_type TEXT,
                crawl_depth INTEGER,
                language TEXT,
                relevance REAL,
                token_count INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                indexed_at TEXT
            )
            """
        )
        self.con.execute(
            """
            CREATE TABLE IF NOT EXISTS rejected_pages (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL UNIQUE,
                host TEXT NOT NULL,
                status_code INTEGER,
                content_type TEXT,
                crawl_depth INTEGER,
                language TEXT,
                relevance REAL,
                token_count INTEGER,
                exclusion_reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
            """
        )
        self._migrate_schema()

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
        self.con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_rejected_pages_host
            ON rejected_pages(host)
            """
        )
        self.con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_rejected_pages_exclusion_reason
            ON rejected_pages(exclusion_reason)
            """
        )

        self.con.commit()

    def _migrate_schema(self) -> None:
        columns = {
            row["name"]
            for row in self.con.execute("PRAGMA table_info(pages)").fetchall()
        }

        migrations = {
            "title": "TEXT NOT NULL DEFAULT ''",
            "crawl_depth": "INTEGER",
            "language": "TEXT",
            "relevance": "REAL",
            "token_count": "INTEGER",
        }

        for name, definition in migrations.items():
            if name not in columns:
                self.con.execute(f"ALTER TABLE pages ADD COLUMN {name} {definition}")

    def upsert_page(
        self,
        *,
        title: str,
        url: str,
        host: str,
        path: str | Path,
        status_code: int | None = None,
        content_type: str | None = None,
        fetched_at: str | None = None,
        crawl_depth: int | None = None,
        language: str | None = None,
        relevance: float | None = None,
        token_count: int | None = None,
    ) -> None:
        now = self._now()
        fetched_at = fetched_at or now

        with self.con:
            self.con.execute(
                """
                INSERT INTO pages (
                    title,
                    url,
                    host,
                    path,
                    status_code,
                    content_type,
                    crawl_depth,
                    language,
                    relevance,
                    token_count,
                    created_at,
                    updated_at,
                    fetched_at,
                    indexed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(url) DO UPDATE SET
                    title = excluded.title,
                    host = excluded.host,
                    path = excluded.path,
                    status_code = excluded.status_code,
                    content_type = excluded.content_type,
                    crawl_depth = excluded.crawl_depth,
                    language = excluded.language,
                    relevance = excluded.relevance,
                    token_count = excluded.token_count,
                    fetched_at = excluded.fetched_at,
                    updated_at = excluded.updated_at
                """,
                (
                    title,
                    url,
                    host,
                    str(path),
                    status_code,
                    content_type,
                    crawl_depth,
                    language,
                    relevance,
                    token_count,
                    now,
                    now,
                    fetched_at,
                ),
            )

    def upsert_rejected_page(
        self,
        *,
        title: str = "",
        url: str,
        host: str,
        exclusion_reason: str,
        status_code: int | None = None,
        content_type: str | None = None,
        fetched_at: str | None = None,
        crawl_depth: int | None = None,
        language: str | None = None,
        relevance: float | None = None,
        token_count: int | None = None,
    ) -> None:
        now = self._now()
        fetched_at = fetched_at or now

        with self.con:
            self.con.execute(
                """
                INSERT INTO rejected_pages (
                    title,
                    url,
                    host,
                    status_code,
                    content_type,
                    crawl_depth,
                    language,
                    relevance,
                    token_count,
                    exclusion_reason,
                    created_at,
                    updated_at,
                    fetched_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    title = excluded.title,
                    host = excluded.host,
                    status_code = excluded.status_code,
                    content_type = excluded.content_type,
                    crawl_depth = excluded.crawl_depth,
                    language = excluded.language,
                    relevance = excluded.relevance,
                    token_count = excluded.token_count,
                    exclusion_reason = excluded.exclusion_reason,
                    fetched_at = excluded.fetched_at,
                    updated_at = excluded.updated_at
                """,
                (
                    title,
                    url,
                    host,
                    status_code,
                    content_type,
                    crawl_depth,
                    language,
                    relevance,
                    token_count,
                    exclusion_reason,
                    now,
                    now,
                    fetched_at,
                ),
            )

    # saved-page count per host
    def host_counts(self) -> dict[str, int]:
        rows = self.con.execute("SELECT host, COUNT(*) FROM pages GROUP BY host")
        return {row[0]: row[1] for row in rows}

    def iter_html_pages(self) -> Iterator[PageRecord]:
        return self._iter_pages(
            columns=_PAGE_COLUMNS,
            table="pages",
            where="content_type IS NULL OR content_type LIKE 'text/html%'",
        )

    def iter_rejected_pages(self) -> Iterator[PageRecord]:
        return self._iter_pages(
            columns=_REJECTED_PAGE_COLUMNS,
            table="rejected_pages",
        )

    def _iter_pages(
        self, *, columns: str, table: str, where: str | None = None
    ) -> Iterator[PageRecord]:
        where_clause = f"WHERE {where}" if where is not None else ""
        rows = self.con.execute(
            f"""
            SELECT {columns}
            FROM {table}
            {where_clause}
            ORDER BY id
            """
        )

        for row in rows:
            yield self._row_to_page(row)

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
            exclusion_reason=(
                row["exclusion_reason"] if "exclusion_reason" in row.keys() else None
            ),
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
