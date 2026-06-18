import sqlite3

from tuebingen_crawler.save_pages import PageStore


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
            content_hash TEXT,
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
            url, host, path, status_code, content_type, content_hash,
            fetched_at, indexed_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "https://host/",
            "host",
            str(tmp_path / "host" / "index.html"),
            200,
            "text/html",
            "abc",
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


def test_page_store_upsert_persists_title(tmp_path):
    with PageStore(tmp_path / "pages.sqlite") as store:
        store.upsert_page(
            title="Tuebingen",
            url="https://host/",
            host="host",
            path=tmp_path / "host" / "index.html",
            status_code=200,
            content_type="text/html",
            content_hash="abc",
        )

        [page] = list(store.iter_html_pages())

    assert page.title == "Tuebingen"
