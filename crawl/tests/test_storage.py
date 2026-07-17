import json
from pathlib import Path

import httpx
import pytest

from tuebingen_crawler.models import CrawlState, FrontierEntry, Statistics
from tuebingen_crawler.storage import (
    RobotsCache,
    generate_global_shared_state_path,
    load_robots,
    load_shared_state,
    load_seed_toml,
    load_state,
    save_html,
    save_shared_state,
    save_state,
)


def test_load_seed_toml_parses_sites(tmp_path):
    seeds = tmp_path / "seeds.toml"
    seeds.write_text(
        '[[sites]]\nurl = "https://a.example/"\n\n'
        '[[sites]]\nurl = "https://b.example/"\n',
        encoding="utf-8",
    )

    sites = load_seed_toml(seeds)

    assert [s.url for s in sites] == ["https://a.example/", "https://b.example/"]


@pytest.mark.parametrize("status_code", [403, 500])
def test_load_robots_allows_all_when_robots_txt_is_unavailable(status_code):
    def handler(request):
        return httpx.Response(status_code, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        parser = load_robots(client, "https://host/")

    assert parser.can_fetch("*", "https://host/private")


def test_load_robots_allows_all_for_unencodable_hostname():
    # a malformed href (e.g. stray zero-width-space characters) can produce a
    # netloc that httpx refuses to IDNA-encode; this must not crash the seed
    with httpx.Client() as client:
        parser = load_robots(client, "https://​host/")

    assert parser.can_fetch("*", "https://​host/private")


def test_load_robots_allows_all_for_oversized_hostname_label():
    # a garbage href with a too-long label makes stdlib getaddrinfo() raise a
    # raw UnicodeEncodeError deep inside socket.create_connection, which
    # httpx does not wrap into httpx.InvalidURL; this must not crash the seed
    url = "https://" + "a" * 100 + ".example/"
    with httpx.Client() as client:
        parser = load_robots(client, url)

    assert parser.can_fetch("*", url + "private")


def test_robots_cache_is_per_origin():
    requests = []

    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(200, text="User-agent: *\nDisallow: /private\n", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        cache = RobotsCache(client)

        assert not cache.can_fetch("*", "https://host/private")
        assert not cache.can_fetch("*", "http://host/private")

    assert requests == ["https://host/robots.txt", "http://host/robots.txt"]


def test_robots_cache_returns_stdlib_sitemap_directives():
    def handler(request):
        return httpx.Response(
            200,
            text="User-agent: *\nSitemap: https://host/sitemap.xml\n",
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        cache = RobotsCache(client)
        assert cache.site_maps("https://host/page") == ["https://host/sitemap.xml"]


def test_robots_cache_logs_a_missing_sitemap_once(caplog):
    def handler(request):
        return httpx.Response(200, text="User-agent: *\n", request=request)

    caplog.set_level("INFO", logger="tuebingen_crawler.storage")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        cache = RobotsCache(client)
        assert cache.site_maps("https://host/first") == []
        assert cache.site_maps("https://host/second") == []

    assert [record.message for record in caplog.records] == [
        "No sitemap declared in robots.txt for https://host"
    ]


def test_generate_global_shared_state_path(tmp_path):
    assert generate_global_shared_state_path(tmp_path) == tmp_path / "state" / "global_seen.json"


def test_save_html_writes_file_under_normalized_hostname(tmp_path):
    body = b"<html>content</html>"
    path = save_html("www.tuepedia.de", tmp_path, "https://www.tuepedia.de/wiki/a", body)

    saved = Path(path)
    assert saved.parent == tmp_path / "tuepedia.de"
    assert saved.suffix == ".html"
    assert "wiki-a" in saved.name
    assert saved.read_bytes() == body


def test_save_state_omits_shared_sets_but_keeps_seen_sitemaps(tmp_path):
    path = tmp_path / "state" / "crawl_state.json"
    state = CrawlState(
        frontier=[
            FrontierEntry(-5.0, 1, "https://host/", 0),
            FrontierEntry(-3.0, 2, "https://host/a", 1),
        ],
        seen_urls={"https://host/", "https://host/a"},
        seen_texts={123, 456},
        seen_sitemaps={"https://host/sitemap.xml"},
        queued_urls_by_host={"host": 2},
        counter=2,
        statistics=Statistics(fetched=1, discovered=2, failed=0, saved=1),
    )

    save_state(path, state)
    loaded, ok = load_state(path)

    assert ok
    assert loaded.frontier == state.frontier
    assert loaded.seen_urls == set()
    assert loaded.seen_texts == set()
    assert loaded.seen_sitemaps == {"https://host/sitemap.xml"}
    assert loaded.queued_urls_by_host == state.queued_urls_by_host
    assert loaded.counter == state.counter
    assert loaded.statistics == state.statistics


def test_save_and_load_shared_state_roundtrip(tmp_path):
    path = generate_global_shared_state_path(tmp_path)
    save_shared_state(path, {"https://host/a", "https://host/b"}, {123, 456})

    assert load_shared_state(path) == ({"https://host/a", "https://host/b"}, {123, 456})


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
