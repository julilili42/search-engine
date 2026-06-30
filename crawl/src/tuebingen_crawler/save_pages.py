from __future__ import annotations

import csv
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
_PAGEVERDICT_COLUMNS = (
    "pageverdict_score",
    "pageverdict_label",
    "pageverdict_decision",
    "pageverdict_model",
    "pageverdict_snippet",
)
_TIMESTAMP_PAGE_COLUMNS = (
    "fetched_at",
    "indexed_at",
)
_PAGE_COLUMNS = (
    *_BASE_PAGE_COLUMNS,
    *_DEBUG_PAGE_COLUMNS,
    *_PAGEVERDICT_COLUMNS,
    *_TIMESTAMP_PAGE_COLUMNS,
)
_REJECTED_PAGE_COLUMNS = (
    "title",
    "url",
    "host",
    "NULL AS path",
    "status_code",
    "content_type",
    *_DEBUG_PAGE_COLUMNS,
    *_PAGEVERDICT_COLUMNS,
    "fetched_at",
    "NULL AS indexed_at",
    "exclusion_reason",
)
_REQUIRED_PAGE_TABLE_COLUMNS = (
    "id",
    *_PAGE_COLUMNS,
    "created_at",
    "updated_at",
)
_REQUIRED_REJECTED_PAGE_TABLE_COLUMNS = (
    "id",
    "title",
    "url",
    "host",
    "status_code",
    "content_type",
    *_DEBUG_PAGE_COLUMNS,
    *_PAGEVERDICT_COLUMNS,
    "exclusion_reason",
    "created_at",
    "updated_at",
    "fetched_at",
)
_REQUIRED_LINK_CANDIDATE_TABLE_COLUMNS = (
    "id",
    "parent_url",
    "parent_host",
    "parent_depth",
    "parent_pageverdict_score",
    "parent_pageverdict_label",
    "parent_pageverdict_decision",
    "parent_relevance",
    "target_url",
    "target_host",
    "target_depth",
    "anchor",
    "raw_score",
    "linkverdict_score",
    "linkverdict_label",
    "linkverdict_model",
    "should_enqueue",
    "selected",
    "rejection_reason",
    "target_status",
    "target_status_code",
    "target_content_type",
    "target_language",
    "target_relevance",
    "target_token_count",
    "target_pageverdict_score",
    "target_pageverdict_label",
    "target_pageverdict_decision",
    "target_exclusion_reason",
    "target_fetched_at",
    "created_at",
    "updated_at",
)


@dataclass(frozen=True)
class PageVerdictMetadata:
    score: float | None
    label: str | None
    decision: str | None
    model: str | None
    snippet: str | None


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
    pageverdict: PageVerdictMetadata
    fetched_at: str
    indexed_at: str | None
    exclusion_reason: str | None = None


@dataclass(frozen=True)
class LinkCandidateRecord:
    parent_url: str
    parent_host: str
    parent_depth: int
    parent_pageverdict: PageVerdictMetadata
    parent_relevance: float | None
    target_url: str
    target_host: str
    target_depth: int
    anchor: str
    raw_score: float
    should_enqueue: bool
    selected: bool
    linkverdict_score: float | None = None
    linkverdict_label: str | None = None
    linkverdict_model: str | None = None
    rejection_reason: str | None = None


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
                pageverdict_score REAL,
                pageverdict_label TEXT,
                pageverdict_decision TEXT,
                pageverdict_model TEXT,
                pageverdict_snippet TEXT,
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
                pageverdict_score REAL,
                pageverdict_label TEXT,
                pageverdict_decision TEXT,
                pageverdict_model TEXT,
                pageverdict_snippet TEXT,
                exclusion_reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            )
            """
        )
        self._validate_schema()

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

    def _validate_schema(self) -> None:
        self._validate_table_columns("pages", _REQUIRED_PAGE_TABLE_COLUMNS)
        self._validate_table_columns(
            "rejected_pages", _REQUIRED_REJECTED_PAGE_TABLE_COLUMNS
        )

    def _validate_table_columns(self, table: str, required_columns: tuple[str, ...]) -> None:
        columns = {
            row["name"]
            for row in self.con.execute(f"PRAGMA table_info({table})").fetchall()
        }
        missing = [column for column in required_columns if column not in columns]
        if missing:
            missing_columns = ", ".join(missing)
            raise RuntimeError(
                f"Existing crawl database {self.db_path} has an incompatible "
                f"{table} schema; missing columns: {missing_columns}. Delete the "
                "old database and start a fresh crawl."
            )

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
        pageverdict_score: float | None = None,
        pageverdict_label: str | None = None,
        pageverdict_decision: str | None = None,
        pageverdict_model: str | None = None,
        pageverdict_snippet: str | None = None,
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
                    pageverdict_score,
                    pageverdict_label,
                    pageverdict_decision,
                    pageverdict_model,
                    pageverdict_snippet,
                    created_at,
                    updated_at,
                    fetched_at,
                    indexed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
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
                    pageverdict_score = excluded.pageverdict_score,
                    pageverdict_label = excluded.pageverdict_label,
                    pageverdict_decision = excluded.pageverdict_decision,
                    pageverdict_model = excluded.pageverdict_model,
                    pageverdict_snippet = excluded.pageverdict_snippet,
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
                    pageverdict_score,
                    pageverdict_label,
                    pageverdict_decision,
                    pageverdict_model,
                    pageverdict_snippet,
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
        pageverdict_score: float | None = None,
        pageverdict_label: str | None = None,
        pageverdict_decision: str | None = None,
        pageverdict_model: str | None = None,
        pageverdict_snippet: str | None = None,
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
                    pageverdict_score,
                    pageverdict_label,
                    pageverdict_decision,
                    pageverdict_model,
                    pageverdict_snippet,
                    exclusion_reason,
                    created_at,
                    updated_at,
                    fetched_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    title = excluded.title,
                    host = excluded.host,
                    status_code = excluded.status_code,
                    content_type = excluded.content_type,
                    crawl_depth = excluded.crawl_depth,
                    language = excluded.language,
                    relevance = excluded.relevance,
                    token_count = excluded.token_count,
                    pageverdict_score = excluded.pageverdict_score,
                    pageverdict_label = excluded.pageverdict_label,
                    pageverdict_decision = excluded.pageverdict_decision,
                    pageverdict_model = excluded.pageverdict_model,
                    pageverdict_snippet = excluded.pageverdict_snippet,
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
                    pageverdict_score,
                    pageverdict_label,
                    pageverdict_decision,
                    pageverdict_model,
                    pageverdict_snippet,
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
        self, *, columns: tuple[str, ...], table: str, where: str | None = None
    ) -> Iterator[PageRecord]:
        where_clause = f"WHERE {where}" if where is not None else ""
        selected_columns = ", ".join(columns)
        rows = self.con.execute(
            f"""
            SELECT {selected_columns}
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
            pageverdict=PageVerdictMetadata(
                score=row["pageverdict_score"],
                label=row["pageverdict_label"],
                decision=row["pageverdict_decision"],
                model=row["pageverdict_model"],
                snippet=row["pageverdict_snippet"],
            ),
            fetched_at=row["fetched_at"],
            indexed_at=row["indexed_at"],
            exclusion_reason=(
                row["exclusion_reason"] if "exclusion_reason" in row.keys() else None
            ),
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


class LinkStore:
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

    def __enter__(self) -> "LinkStore":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def init_schema(self) -> None:
        self.con.execute(
            """
            CREATE TABLE IF NOT EXISTS link_candidates (
                id INTEGER PRIMARY KEY,
                parent_url TEXT NOT NULL,
                parent_host TEXT NOT NULL,
                parent_depth INTEGER NOT NULL,
                parent_pageverdict_score REAL,
                parent_pageverdict_label TEXT,
                parent_pageverdict_decision TEXT,
                parent_relevance REAL,
                target_url TEXT NOT NULL,
                target_host TEXT NOT NULL,
                target_depth INTEGER NOT NULL,
                anchor TEXT NOT NULL DEFAULT '',
                raw_score REAL NOT NULL,
                linkverdict_score REAL,
                linkverdict_label TEXT,
                linkverdict_model TEXT,
                should_enqueue INTEGER NOT NULL,
                selected INTEGER NOT NULL,
                rejection_reason TEXT,
                target_status TEXT,
                target_status_code INTEGER,
                target_content_type TEXT,
                target_language TEXT,
                target_relevance REAL,
                target_token_count INTEGER,
                target_pageverdict_score REAL,
                target_pageverdict_label TEXT,
                target_pageverdict_decision TEXT,
                target_exclusion_reason TEXT,
                target_fetched_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(parent_url, target_url, anchor)
            )
            """
        )
        self._validate_schema()
        self.con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_link_candidates_target_url
            ON link_candidates(target_url)
            """
        )
        self.con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_link_candidates_parent_url
            ON link_candidates(parent_url)
            """
        )
        self.con.commit()

    def _validate_schema(self) -> None:
        columns = {
            row["name"]
            for row in self.con.execute("PRAGMA table_info(link_candidates)").fetchall()
        }
        missing = [
            column
            for column in _REQUIRED_LINK_CANDIDATE_TABLE_COLUMNS
            if column not in columns
        ]
        if missing:
            missing_columns = ", ".join(missing)
            raise RuntimeError(
                f"Existing crawl database {self.db_path} has an incompatible "
                "link_candidates schema; missing columns: "
                f"{missing_columns}. Delete the old database and start a fresh crawl."
            )

    def upsert_link_candidates(self, records: list[LinkCandidateRecord]) -> None:
        if not records:
            return

        now = self._now()
        with self.con:
            for record in records:
                self.con.execute(
                    """
                    INSERT INTO link_candidates (
                        parent_url,
                        parent_host,
                        parent_depth,
                        parent_pageverdict_score,
                        parent_pageverdict_label,
                        parent_pageverdict_decision,
                        parent_relevance,
                        target_url,
                        target_host,
                        target_depth,
                        anchor,
                        raw_score,
                        linkverdict_score,
                        linkverdict_label,
                        linkverdict_model,
                        should_enqueue,
                        selected,
                        rejection_reason,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(parent_url, target_url, anchor) DO UPDATE SET
                        parent_host = excluded.parent_host,
                        parent_depth = excluded.parent_depth,
                        parent_pageverdict_score = excluded.parent_pageverdict_score,
                        parent_pageverdict_label = excluded.parent_pageverdict_label,
                        parent_pageverdict_decision = excluded.parent_pageverdict_decision,
                        parent_relevance = excluded.parent_relevance,
                        target_host = excluded.target_host,
                        target_depth = excluded.target_depth,
                        raw_score = excluded.raw_score,
                        linkverdict_score = excluded.linkverdict_score,
                        linkverdict_label = excluded.linkverdict_label,
                        linkverdict_model = excluded.linkverdict_model,
                        should_enqueue = excluded.should_enqueue,
                        selected = excluded.selected,
                        rejection_reason = excluded.rejection_reason,
                        updated_at = excluded.updated_at
                    """,
                    (
                        record.parent_url,
                        record.parent_host,
                        record.parent_depth,
                        record.parent_pageverdict.score,
                        record.parent_pageverdict.label,
                        record.parent_pageverdict.decision,
                        record.parent_relevance,
                        record.target_url,
                        record.target_host,
                        record.target_depth,
                        record.anchor,
                        record.raw_score,
                        record.linkverdict_score,
                        record.linkverdict_label,
                        record.linkverdict_model,
                        int(record.should_enqueue),
                        int(record.selected),
                        record.rejection_reason,
                        now,
                        now,
                    ),
                )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def update_link_target(
        self,
        *,
        url: str,
        target_status: str,
        status_code: int | None,
        content_type: str | None,
        language: str | None,
        relevance: float | None,
        token_count: int | None,
        pageverdict_score: float | None,
        pageverdict_label: str | None,
        pageverdict_decision: str | None,
        exclusion_reason: str | None,
        fetched_at: str | None,
    ) -> None:
        with self.con:
            self.con.execute(
                """
                UPDATE link_candidates
                SET
                    target_status = ?,
                    target_status_code = ?,
                    target_content_type = ?,
                    target_language = ?,
                    target_relevance = ?,
                    target_token_count = ?,
                    target_pageverdict_score = ?,
                    target_pageverdict_label = ?,
                    target_pageverdict_decision = ?,
                    target_exclusion_reason = ?,
                    target_fetched_at = ?,
                    updated_at = ?
                WHERE target_url = ?
                """,
                (
                    target_status,
                    status_code,
                    content_type,
                    language,
                    relevance,
                    token_count,
                    pageverdict_score,
                    pageverdict_label,
                    pageverdict_decision,
                    exclusion_reason,
                    fetched_at,
                    self._now(),
                    url,
                ),
            )


class CrawlExportDB:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.con = sqlite3.connect(self.db_path)
        self.con.row_factory = sqlite3.Row

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> "CrawlExportDB":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def export_pageverdict_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = self.con.execute(
            """
            SELECT *
            FROM (
                SELECT
                    'pages' AS source_table,
                    title,
                    url,
                    host,
                    status_code,
                    content_type,
                    crawl_depth,
                    language,
                    relevance,
                    token_count,
                    pageverdict_score,
                    pageverdict_label,
                    pageverdict_decision,
                    pageverdict_model,
                    pageverdict_snippet,
                    fetched_at,
                    indexed_at,
                    NULL AS exclusion_reason
                FROM pages
                WHERE pageverdict_score IS NOT NULL
                UNION ALL
                SELECT
                    'rejected_pages' AS source_table,
                    title,
                    url,
                    host,
                    status_code,
                    content_type,
                    crawl_depth,
                    language,
                    relevance,
                    token_count,
                    pageverdict_score,
                    pageverdict_label,
                    pageverdict_decision,
                    pageverdict_model,
                    pageverdict_snippet,
                    fetched_at,
                    NULL AS indexed_at,
                    exclusion_reason
                FROM rejected_pages
                WHERE pageverdict_score IS NOT NULL
            )
            ORDER BY fetched_at, url
            """
        ).fetchall()

        fieldnames = [
            "query",
            "page",
            "rank",
            "title",
            "url",
            "display_url",
            "snippet",
            "rating",
            "label",
            "notes",
            "source",
            "source_table",
            "status_code",
            "content_type",
            "crawl_depth",
            "language",
            "relevance",
            "token_count",
            "pageverdict_score",
            "pageverdict_label",
            "pageverdict_decision",
            "pageverdict_model",
            "fetched_at",
            "indexed_at",
            "exclusion_reason",
        ]
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for rank, row in enumerate(rows, start=1):
                writer.writerow(
                    {
                        "query": f"crawler:{row['pageverdict_decision']}",
                        "page": "",
                        "rank": rank,
                        "title": row["title"],
                        "url": row["url"],
                        "display_url": row["host"],
                        "snippet": row["pageverdict_snippet"],
                        "rating": "",
                        "label": "",
                        "notes": "",
                        "source": "crawler_pageverdict",
                        "source_table": row["source_table"],
                        "status_code": row["status_code"],
                        "content_type": row["content_type"],
                        "crawl_depth": row["crawl_depth"],
                        "language": row["language"],
                        "relevance": row["relevance"],
                        "token_count": row["token_count"],
                        "pageverdict_score": row["pageverdict_score"],
                        "pageverdict_label": row["pageverdict_label"],
                        "pageverdict_decision": row["pageverdict_decision"],
                        "pageverdict_model": row["pageverdict_model"],
                        "fetched_at": row["fetched_at"],
                        "indexed_at": row["indexed_at"],
                        "exclusion_reason": row["exclusion_reason"],
                    }
                )

    def export_linkverdict_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = self.con.execute(
            """
            SELECT *
            FROM link_candidates
            ORDER BY
                ABS(COALESCE(linkverdict_score, 0.5) - 0.5),
                target_url,
                parent_url,
                id
            """
        ).fetchall()

        fieldnames = [
            "query",
            "page",
            "rank",
            "parent_url",
            "parent_host",
            "parent_depth",
            "parent_pageverdict_score",
            "parent_pageverdict_label",
            "parent_pageverdict_decision",
            "parent_relevance",
            "anchor",
            "target_url",
            "target_host",
            "target_depth",
            "raw_score",
            "linkverdict_score",
            "linkverdict_label",
            "linkverdict_model",
            "should_enqueue",
            "selected",
            "rejection_reason",
            "target_status",
            "target_status_code",
            "target_content_type",
            "target_language",
            "target_relevance",
            "target_token_count",
            "target_pageverdict_score",
            "target_pageverdict_label",
            "target_pageverdict_decision",
            "target_exclusion_reason",
            "target_fetched_at",
            "rating",
            "label",
            "notes",
            "source",
            "created_at",
            "updated_at",
        ]
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for rank, row in enumerate(rows, start=1):
                writer.writerow(
                    {
                        "query": "crawler:linkverdict",
                        "page": "",
                        "rank": rank,
                        "parent_url": row["parent_url"],
                        "parent_host": row["parent_host"],
                        "parent_depth": row["parent_depth"],
                        "parent_pageverdict_score": row["parent_pageverdict_score"],
                        "parent_pageverdict_label": row["parent_pageverdict_label"],
                        "parent_pageverdict_decision": row[
                            "parent_pageverdict_decision"
                        ],
                        "parent_relevance": row["parent_relevance"],
                        "anchor": row["anchor"],
                        "target_url": row["target_url"],
                        "target_host": row["target_host"],
                        "target_depth": row["target_depth"],
                        "raw_score": row["raw_score"],
                        "linkverdict_score": row["linkverdict_score"],
                        "linkverdict_label": row["linkverdict_label"],
                        "linkverdict_model": row["linkverdict_model"],
                        "should_enqueue": row["should_enqueue"],
                        "selected": row["selected"],
                        "rejection_reason": row["rejection_reason"],
                        "target_status": row["target_status"],
                        "target_status_code": row["target_status_code"],
                        "target_content_type": row["target_content_type"],
                        "target_language": row["target_language"],
                        "target_relevance": row["target_relevance"],
                        "target_token_count": row["target_token_count"],
                        "target_pageverdict_score": row["target_pageverdict_score"],
                        "target_pageverdict_label": row["target_pageverdict_label"],
                        "target_pageverdict_decision": row["target_pageverdict_decision"],
                        "target_exclusion_reason": row["target_exclusion_reason"],
                        "target_fetched_at": row["target_fetched_at"],
                        "rating": "",
                        "label": "",
                        "notes": "",
                        "source": "crawler_linkverdict",
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                    }
                )
