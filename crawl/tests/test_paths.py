from tuebingen_crawler.paths import crawl_paths


def test_crawl_paths_group_runtime_data(tmp_path):
    html, db, log = crawl_paths(tmp_path)

    assert html == tmp_path / "html"
    assert db == tmp_path / "db" / "pages.sqlite"
    assert log == tmp_path / "log" / "crawl.log"
