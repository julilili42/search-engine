import json

import pytest

from tuebingen_crawler.models import CrawlState, Statistics
from tuebingen_crawler.storage import generate_state_path, load_state, save_state


def test_generate_state_path_is_deterministic(tmp_path):
    first = generate_state_path(tmp_path, "www.tuepedia.de", "https://www.tuepedia.de/")
    second = generate_state_path(tmp_path, "www.tuepedia.de", "https://www.tuepedia.de/")
    assert first == second
    assert first.parent == tmp_path / "www.tuepedia.de"
    assert first.name.startswith("crawl_state-")
    assert first.suffix == ".json"


def test_generate_state_path_differs_per_start_url(tmp_path):
    first = generate_state_path(tmp_path, "host", "https://host/a")
    second = generate_state_path(tmp_path, "host", "https://host/b")
    assert first != second


def test_save_and_load_state_roundtrip(tmp_path):
    path = tmp_path / "state" / "crawl_state.json"
    state = CrawlState(
        queue=["https://host/", "https://host/a"],
        head=1,
        seen={"https://host/": True, "https://host/a": True},
        statistics=Statistics(fetched=1, discovered=2, failed=0, saved=1),
    )

    save_state(path, state)
    loaded, ok = load_state(path)

    assert ok
    assert loaded == state


def test_save_state_leaves_no_tmp_file(tmp_path):
    path = tmp_path / "crawl_state.json"
    save_state(path, CrawlState())
    assert path.exists()
    assert not path.with_name(path.name + ".tmp").exists()


def test_save_state_overwrites_existing_file(tmp_path):
    path = tmp_path / "crawl_state.json"
    save_state(path, CrawlState(queue=["https://host/old"], head=1))
    save_state(path, CrawlState(queue=["https://host/new"], head=0))

    loaded, ok = load_state(path)
    assert ok
    assert loaded.queue == ["https://host/new"]
    assert loaded.head == 0


def test_load_state_missing_file_returns_fresh_state(tmp_path):
    state, ok = load_state(tmp_path / "does-not-exist.json")
    assert not ok
    assert state == CrawlState()


def test_load_state_with_missing_keys_uses_defaults(tmp_path):
    path = tmp_path / "crawl_state.json"
    path.write_text(json.dumps({"queue": ["https://host/"]}), encoding="utf-8")

    state, ok = load_state(path)
    assert ok
    assert state.queue == ["https://host/"]
    assert state.head == 0
    assert state.seen == {}
    assert state.statistics == Statistics()


def test_load_state_corrupt_json_raises(tmp_path):
    path = tmp_path / "crawl_state.json"
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(Exception):
        load_state(path)
