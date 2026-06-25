import sqlite3

from tuebingen_crawler.save_pages import PageStore


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
        "exclusion_reason",
        "created_at",
        "updated_at",
        "fetched_at",
    ]


def test_page_store_migrates_existing_db_without_title(tmp_path):
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

    with PageStore(db_path) as store:
        [page] = list(store.iter_html_pages())

    assert page.title == ""
    assert page.url == "https://host/"
    assert page.crawl_depth is None
    assert page.language is None
    assert page.relevance is None
    assert page.token_count is None


def test_page_store_upsert_persists_page_metadata(tmp_path):
    with PageStore(tmp_path / "pages.sqlite") as store:
        store.upsert_page(
            title="Tuebingen",
            url="https://host/",
            host="host",
            path=tmp_path / "host" / "index.html",
            status_code=200,
            content_type="text/html",
            crawl_depth=2,
            language="en",
            relevance=7.5,
            token_count=123,
        )

        [page] = list(store.iter_html_pages())

    assert page.title == "Tuebingen"
    assert page.crawl_depth == 2
    assert page.language == "en"
    assert page.relevance == 7.5
    assert page.token_count == 123


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
            content_type="text/html",
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
