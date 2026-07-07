import sqlite3

from helpers import make_page_load


def test_page_load_reads_saved_page_metadata(tmp_path):
    site_dir = tmp_path / "html"
    site_dir.mkdir()
    path = site_dir / "page.html"
    path.write_text("<html></html>", encoding="utf-8")

    pages_db = make_page_load(tmp_path / "pages.sqlite", {path: "text/html"})

    [page] = list(pages_db.iter_html_pages())
    same_page = pages_db.get_page_by_file_path(path)

    assert same_page == page
    assert page.title == "page"
    assert page.crawl_depth == 0
    assert page.language == "en"
    assert page.relevance == 5.0
    assert page.token_count == 100


def test_iter_html_pages_skips_low_relevance_pages(tmp_path):
    site_dir = tmp_path / "html"
    site_dir.mkdir()
    path = site_dir / "page.html"
    path.write_text("<html></html>", encoding="utf-8")

    db_path = tmp_path / "pages.sqlite"
    pages_db = make_page_load(db_path, {path: "text/html"})

    con = sqlite3.connect(db_path)
    con.execute(
        "UPDATE pages SET relevance = 3.0 WHERE url = ?",
        ("https://example.test/page.html",),
    )
    con.commit()
    con.close()

    assert list(pages_db.iter_html_pages()) == []
    # below-threshold pages stay reachable by path (debug lookups)
    assert pages_db.get_page_by_file_path(path) is not None


def test_iter_html_pages_uses_stricter_noisy_host_threshold(tmp_path):
    site_dir = tmp_path / "html"
    site_dir.mkdir()
    path = site_dir / "page.html"
    path.write_text("<html></html>", encoding="utf-8")

    db_path = tmp_path / "pages.sqlite"
    pages_db = make_page_load(db_path, {path: "text/html"})

    con = sqlite3.connect(db_path)
    con.execute(
        "UPDATE pages SET host = ?, relevance = ? WHERE url = ?",
        ("komoot.com", 4.9, "https://example.test/page.html"),
    )
    con.commit()
    con.close()

    assert list(pages_db.iter_html_pages()) == []


def test_page_load_ignores_rejected_pages_table(tmp_path):
    site_dir = tmp_path / "html"
    site_dir.mkdir()
    path = site_dir / "page.html"
    path.write_text("<html></html>", encoding="utf-8")

    db_path = tmp_path / "pages.sqlite"
    pages_db = make_page_load(db_path, {path: "text/html"})

    con = sqlite3.connect(db_path)
    con.execute(
        """
        CREATE TABLE rejected_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    con.execute(
        """
        INSERT INTO rejected_pages (
            title, url, host, status_code, content_type, crawl_depth, language,
            relevance, token_count, exclusion_reason, created_at, updated_at,
            fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Rejected",
            "https://example.test/rejected",
            "example.test",
            200,
            "text/html",
            1,
            "en",
            0.1,
            20,
            "path_trap",
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
        ),
    )
    con.commit()
    con.close()

    pages = list(pages_db.iter_html_pages())

    assert [page.url for page in pages] == ["https://example.test/page.html"]
    assert pages[0].exclusion_reason is None
