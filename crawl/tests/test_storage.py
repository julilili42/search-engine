import json
from pathlib import Path

import httpx
import pytest

from tuebingen_crawler.models import CrawlSite, CrawlState, FrontierEntry, Statistics
from tuebingen_crawler.storage import (
    generate_state_path,
    load_or_create_state,
    load_robots,
    load_seed_toml,
    load_state,
    save_html,
    save_state,
)


def test_load_seed_toml_parses_round_robin_weight_and_defaults_to_one(tmp_path):
    seeds = tmp_path / "seeds.toml"
    seeds.write_text(
        '[[sites]]\nurl = "https://a.example/"\nround_robin_weight = 3\n\n'
        '[[sites]]\nurl = "https://b.example/"\n',
        encoding="utf-8",
    )

    sites = load_seed_toml(seeds)

    assert [s.url for s in sites] == ["https://a.example/", "https://b.example/"]
    assert sites[0].round_robin_weight == 3
    assert sites[1].round_robin_weight == 1  # default when omitted


@pytest.mark.parametrize("status_code", [403, 500])
def test_load_robots_allows_all_when_robots_txt_is_unavailable(status_code):
    def handler(request):
        return httpx.Response(status_code, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        parser = load_robots(client, CrawlSite(url="https://host/"))

    assert parser.can_fetch("*", "https://host/private")


def test_generate_state_path_is_deterministic(tmp_path):
    first = generate_state_path(tmp_path, "www.tuepedia.de", "https://www.tuepedia.de/")
    second = generate_state_path(tmp_path, "www.tuepedia.de", "https://www.tuepedia.de/")
    assert first == second
    assert first.parent == tmp_path / "state"
    assert first.name.startswith("crawl_state-")
    assert "tuepedia.de" in first.name
    assert first.suffix == ".json"


def test_generate_state_path_differs_per_start_url(tmp_path):
    first = generate_state_path(tmp_path, "host", "https://host/a")
    second = generate_state_path(tmp_path, "host", "https://host/b")
    assert first != second


def test_generate_state_path_differs_per_host(tmp_path):
    first = generate_state_path(tmp_path, "alpha.example", "https://alpha.example/a")
    second = generate_state_path(tmp_path, "beta.example", "https://beta.example/a")
    assert first != second
    assert first.parent == second.parent == tmp_path / "state"


def test_save_html_writes_file_under_normalized_hostname(tmp_path):
    body = b"<html>content</html>"
    path = save_html("www.tuepedia.de", tmp_path, "https://www.tuepedia.de/wiki/a", body)

    saved = Path(path)
    assert saved.parent == tmp_path / "tuepedia.de"
    assert saved.suffix == ".html"
    assert "wiki-a" in saved.name
    assert saved.read_bytes() == body


def test_save_and_load_state_roundtrip(tmp_path):
    path = tmp_path / "state" / "crawl_state.json"
    state = CrawlState(
        frontier=[
            FrontierEntry(-5.0, 1, "https://host/", 0),
            FrontierEntry(-3.0, 2, "https://host/a", 1),
        ],
        seen_urls={"https://host/", "https://host/a"},
        seen_texts={123, 456},
        queued_urls_by_host={"host": 2},
        counter=2,
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
    save_state(
        path,
        CrawlState(frontier=[FrontierEntry(-1.0, 1, "https://host/old", 0)], counter=1),
    )
    save_state(
        path,
        CrawlState(frontier=[FrontierEntry(-2.0, 1, "https://host/new", 0)], counter=1),
    )

    loaded, ok = load_state(path)
    assert ok
    assert loaded.frontier == [FrontierEntry(-2.0, 1, "https://host/new", 0)]
    assert loaded.queued_urls_by_host == {"host": 1}
    assert loaded.counter == 1


def test_load_state_missing_file_returns_fresh_state(tmp_path):
    state, ok = load_state(tmp_path / "does-not-exist.json")
    assert not ok
    assert state == CrawlState()


def test_load_state_with_missing_keys_uses_defaults(tmp_path):
    path = tmp_path / "crawl_state.json"
    path.write_text(
        json.dumps({"frontier": [[-1.0, 1, "https://host/", 0]]}), encoding="utf-8"
    )

    state, ok = load_state(path)
    assert ok
    assert state.frontier == [FrontierEntry(-1.0, 1, "https://host/", 0)]
    assert state.queued_urls_by_host == {"host": 1}
    assert state.counter == 0
    assert state.seen_urls == set()
    assert state.seen_texts == set()
    assert state.statistics == Statistics()


def test_load_state_ignores_legacy_string_seen_texts(tmp_path):
    path = tmp_path / "crawl_state.json"
    path.write_text(
        json.dumps(
            {
                "seen_texts": [
                    "035d2aadefddc9601f048826a95b029ba24a540f9bf586eab68460e9ce53a15f",
                    123,
                    "9c89bce000af6e97696de173e0765fca34a7fbcc8cad5ff09a32ec409ddeab5e",
                    456,
                ]
            }
        ),
        encoding="utf-8",
    )

    state, ok = load_state(path)

    assert ok
    assert state.seen_texts == {123, 456}


def test_load_state_corrupt_json_raises(tmp_path):
    path = tmp_path / "crawl_state.json"
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(Exception):
        load_state(path)


def test_load_or_create_state_initializes_new_state_with_seed(tmp_path):
    seen_urls: set[str] = set()
    seen_texts: set[int] = set()

    state = load_or_create_state(
        tmp_path / "crawl_state.json",
        "https://host/",
        seen_urls,
        seen_texts,
    )

    assert state.seen_urls is seen_urls
    assert state.seen_texts is seen_texts
    assert state.seen_urls == {"https://host/"}
    assert state.frontier == [FrontierEntry(-1_000_000.0, 1, "https://host/", 0)]
    assert state.counter == 1


def test_load_or_create_state_uses_shared_seen_sets_for_loaded_state(tmp_path):
    path = tmp_path / "crawl_state.json"
    save_state(
        path,
        CrawlState(
            frontier=[FrontierEntry(-1.0, 1, "https://host/a", 1)],
            seen_urls={"https://host/a"},
            seen_texts={123},
        ),
    )
    seen_urls = {"https://other/"}
    seen_texts = {456}

    state = load_or_create_state(path, "https://host/", seen_urls, seen_texts)

    assert state.seen_urls is seen_urls
    assert state.seen_texts is seen_texts
    assert state.seen_urls == {"https://other/", "https://host/a"}
    assert state.seen_texts == {123, 456}
    assert state.frontier == [FrontierEntry(-1.0, 1, "https://host/a", 1)]
    assert state.queued_urls_by_host == {"host": 1}
