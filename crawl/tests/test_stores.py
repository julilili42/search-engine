import sqlite3

# SQLite store tests.
import pytest

from tuebingen_crawler.stores import (
    LinkCandidateRecord,
    LinkStore,
    PageStore,
    PageVerdictMetadata,
)
from tuebingen_crawler.models import FetchResult, Language
from tuebingen_crawler.page_classifier import PageVerdict


def test_page_store_creates_fetched_and_indexed_at_as_last_columns(tmp_path):
    with PageStore(tmp_path / "pages.sqlite") as store:
        columns = [
            row["name"]
            for row in store.con.execute("PRAGMA table_info(pages)").fetchall()
        ]

    assert columns[-2:] == ["fetched_at", "indexed_at"]


def test_page_store_creates_rejected_pages_table(tmp_path):
    with PageStore(tmp_path / "pages.sqlite") as store:
        columns = [
            row["name"]
            for row in store.con.execute(
                "PRAGMA table_info(rejected_pages)"
            ).fetchall()
        ]

    assert columns == [
        "id",
        "title",
        "url",
        "host",
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
        "pageverdict_snippet",
        "exclusion_reason",
        "created_at",
        "updated_at",
        "fetched_at",
    ]


def test_page_store_rejects_existing_db_with_incompatible_schema(tmp_path):
    db_path = tmp_path / "pages.sqlite"
    con = sqlite3.connect(db_path)
    con.execute(
        """
        CREATE TABLE pages (
            id INTEGER PRIMARY KEY,
            url TEXT NOT NULL UNIQUE,
            host TEXT NOT NULL,
            path TEXT NOT NULL,
            status_code INTEGER,
            content_type TEXT,
            fetched_at TEXT NOT NULL,
            indexed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    con.execute(
        """
        INSERT INTO pages (
            url, host, path, status_code, content_type, fetched_at, indexed_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "https://host/",
            "host",
            str(tmp_path / "host" / "index.html"),
            200,
            "text/html",
            "2026-01-01T00:00:00+00:00",
            None,
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:00+00:00",
        ),
    )
    con.commit()
    con.close()

    with pytest.raises(RuntimeError, match="incompatible pages schema"):
        PageStore(db_path)


def test_page_store_upsert_persists_page_metadata(tmp_path):
    with PageStore(tmp_path / "pages.sqlite") as store:
        store.upsert_page(
            title="Tuebingen",
            url="https://host/",
            host="host",
            path=tmp_path / "host" / "index.html",
            crawl_depth=2,
            fetch_result=FetchResult(b"", 200, "text/html"),
            verdict=PageVerdict(
                language=Language.EN,
                relevance=7.5,
                token_count=123,
                score=0.91,
                label="positive",
                model="ml/artifacts/page_verdict.joblib",
                snippet="A useful English Tübingen page.",
            ),
        )

        [page] = list(store.iter_html_pages())

    assert page.title == "Tuebingen"
    assert page.crawl_depth == 2
    assert page.language == "en"
    assert page.relevance == 7.5
    assert page.token_count == 123
    assert page.pageverdict.score == 0.91
    assert page.pageverdict.label == "positive"
    assert page.pageverdict.decision == "index_strong"
    assert page.pageverdict.model == "ml/artifacts/page_verdict.joblib"
    assert page.pageverdict.snippet == "A useful English Tübingen page."


def test_page_store_upsert_persists_rejected_page_metadata(tmp_path):
    with PageStore(tmp_path / "pages.sqlite") as store:
        store.upsert_rejected_page(
            title="Old Newsletter",
            url="https://host/newsletter/2019",
            host="host",
            exclusion_reason="path_trap",
            status_code=200,
            content_type="text/html",
            fetched_at="2026-01-01T00:00:00+00:00",
            crawl_depth=3,
            language="en",
            relevance=1.25,
            token_count=80,
            pageverdict=PageVerdictMetadata(
                score=0.21,
                label="negative",
                decision="reject_follow",
                model="ml/artifacts/page_verdict.joblib",
                snippet="A weak regional page.",
            ),
        )

        [page] = list(store.iter_rejected_pages())

    assert page.title == "Old Newsletter"
    assert page.url == "https://host/newsletter/2019"
    assert page.host == "host"
    assert page.path is None
    assert page.status_code == 200
    assert page.content_type == "text/html"
    assert page.fetched_at == "2026-01-01T00:00:00+00:00"
    assert page.indexed_at is None
    assert page.crawl_depth == 3
    assert page.language == "en"
    assert page.relevance == 1.25
    assert page.token_count == 80
    assert page.pageverdict.score == 0.21
    assert page.pageverdict.label == "negative"
    assert page.pageverdict.decision == "reject_follow"
    assert page.pageverdict.model == "ml/artifacts/page_verdict.joblib"
    assert page.pageverdict.snippet == "A weak regional page."
    assert page.exclusion_reason == "path_trap"


def test_page_store_upsert_rejected_page_updates_existing_url(tmp_path):
    with PageStore(tmp_path / "pages.sqlite") as store:
        store.upsert_rejected_page(
            title="First",
            url="https://host/archive",
            host="host",
            exclusion_reason="thin_page",
            relevance=0.5,
        )
        store.upsert_rejected_page(
            title="Updated",
            url="https://host/archive",
            host="host",
            exclusion_reason="archive",
            status_code=404,
            relevance=0.1,
        )

        pages = list(store.iter_rejected_pages())

    assert len(pages) == 1
    assert pages[0].title == "Updated"
    assert pages[0].status_code == 404
    assert pages[0].relevance == 0.1
    assert pages[0].exclusion_reason == "archive"


def test_rejected_pages_do_not_count_as_saved_pages(tmp_path):
    with PageStore(tmp_path / "pages.sqlite") as store:
        store.upsert_page(
            title="Kept",
            url="https://host/",
            host="host",
            path=tmp_path / "host" / "index.html",
            crawl_depth=0,
            fetch_result=FetchResult(b"", 200, "text/html"),
            verdict=PageVerdict(
                language=Language.EN,
                relevance=7.5,
                token_count=123,
                score=0.91,
                label="positive",
                model="test",
                snippet="",
            ),
        )
        store.upsert_rejected_page(
            title="Rejected",
            url="https://host/newsletter",
            host="host",
            exclusion_reason="path_trap",
            content_type="text/html",
        )

        saved_pages = list(store.iter_html_pages())
        rejected_pages = list(store.iter_rejected_pages())
        host_counts = store.host_counts()

    assert [page.url for page in saved_pages] == ["https://host/"]
    assert [page.url for page in rejected_pages] == ["https://host/newsletter"]
    assert host_counts == {"host": 1}


def test_link_store_creates_link_candidates_table(tmp_path):
    with LinkStore(tmp_path / "pages.sqlite") as store:
        columns = {
            row["name"]
            for row in store.con.execute(
                "PRAGMA table_info(link_candidates)"
            ).fetchall()
        }

    assert {
        "parent_url",
        "parent_pageverdict_score",
        "target_url",
        "anchor",
        "raw_score",
        "linkverdict_score",
        "should_enqueue",
        "selected",
        "rejection_reason",
        "target_status",
        "target_pageverdict_score",
        "target_exclusion_reason",
    } <= columns


def test_link_store_upserts_link_candidate(tmp_path):
    with LinkStore(tmp_path / "pages.sqlite") as store:
        store.upsert_link_candidates(
            [
                LinkCandidateRecord(
                    parent_url="https://host/",
                    parent_host="host",
                    parent_depth=0,
                    parent_pageverdict=PageVerdictMetadata(
                        score=0.8,
                        label="positive",
                        decision="index_strong",
                        model=None,
                        snippet=None,
                    ),
                    parent_relevance=8.0,
                    target_url="https://host/a",
                    target_host="host",
                    target_depth=1,
                    anchor="Tübingen A",
                    raw_score=6.5,
                    should_enqueue=True,
                    selected=True,
                    linkverdict_score=0.77,
                    linkverdict_label="positive",
                    linkverdict_model="ml/artifacts/link_verdict.joblib",
                )
            ]
        )

        [row] = store.con.execute("SELECT * FROM link_candidates").fetchall()

    assert row["parent_url"] == "https://host/"
    assert row["parent_pageverdict_score"] == 0.8
    assert row["target_url"] == "https://host/a"
    assert row["anchor"] == "Tübingen A"
    assert row["raw_score"] == 6.5
    assert row["linkverdict_score"] == 0.77
    assert row["linkverdict_label"] == "positive"
    assert row["linkverdict_model"] == "ml/artifacts/link_verdict.joblib"
    assert row["should_enqueue"] == 1
    assert row["selected"] == 1


def test_link_store_updates_target_metadata(tmp_path):
    with LinkStore(tmp_path / "pages.sqlite") as store:
        store.upsert_link_candidates(
            [
                LinkCandidateRecord(
                    parent_url="https://host/",
                    parent_host="host",
                    parent_depth=0,
                    parent_pageverdict=PageVerdictMetadata(
                        score=None,
                        label=None,
                        decision=None,
                        model=None,
                        snippet=None,
                    ),
                    parent_relevance=5.0,
                    target_url="https://host/a",
                    target_host="host",
                    target_depth=1,
                    anchor="Tübingen A",
                    raw_score=6.5,
                    should_enqueue=True,
                    selected=True,
                )
            ]
        )
        store.update_link_target(
            url="https://host/a",
            target_status="rejected",
            fetch_result=FetchResult(b"", 404, "text/html"),
            language="en",
            relevance=1.2,
            token_count=42,
            pageverdict=PageVerdictMetadata(
                score=0.2,
                label="negative",
                decision="reject_follow",
                model=None,
                snippet=None,
            ),
            exclusion_reason="bad_status",
            fetched_at="2026-06-30T12:00:00+00:00",
        )

        [row] = store.con.execute("SELECT * FROM link_candidates").fetchall()

    assert row["target_status"] == "rejected"
    assert row["target_status_code"] == 404
    assert row["target_content_type"] == "text/html"
    assert row["target_language"] == "en"
    assert row["target_relevance"] == 1.2
    assert row["target_token_count"] == 42
    assert row["target_pageverdict_score"] == 0.2
    assert row["target_pageverdict_label"] == "negative"
    assert row["target_pageverdict_decision"] == "reject_follow"
    assert row["target_exclusion_reason"] == "bad_status"
    assert row["target_fetched_at"] == "2026-06-30T12:00:00+00:00"


def test_link_store_rejects_existing_db_with_incompatible_schema(tmp_path):
    db_path = tmp_path / "pages.sqlite"
    con = sqlite3.connect(db_path)
    con.execute(
        """
        CREATE TABLE link_candidates (
            id INTEGER PRIMARY KEY,
            parent_url TEXT NOT NULL
        )
        """
    )
    con.commit()
    con.close()

    with pytest.raises(RuntimeError, match="incompatible link_candidates schema"):
        LinkStore(db_path)
