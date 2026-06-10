from pathlib import Path

import httpx
import pytest

import tuebingen_crawler.fetcher as fetcher
from tuebingen_crawler.fetcher import fetch_bytes, save_html

HTML_HEADERS = {"Content-Type": "text/html; charset=utf-8"}


@pytest.fixture
def sleep_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(fetcher.time, "sleep", calls.append)
    return calls


def make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_bytes_returns_html_body(sleep_calls):
    def handler(request):
        return httpx.Response(200, headers=HTML_HEADERS, content=b"<html>ok</html>")

    with make_client(handler) as client:
        body = fetch_bytes(client, "https://host/", retry_delay=1.0, retries=3)

    assert body == b"<html>ok</html>"


def test_fetch_bytes_raises_after_retries_on_bad_status(sleep_calls):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(404, headers=HTML_HEADERS)

    with make_client(handler) as client:
        with pytest.raises(RuntimeError):
            fetch_bytes(client, "https://host/missing", retry_delay=1.0, retries=3)

    assert len(requests) == 3


def test_fetch_bytes_skips_non_html_content(sleep_calls):
    def handler(request):
        return httpx.Response(
            200, headers={"Content-Type": "application/pdf"}, content=b"%PDF"
        )

    with make_client(handler) as client:
        with pytest.raises(RuntimeError):
            fetch_bytes(client, "https://host/file.pdf", retry_delay=1.0, retries=2)


def test_fetch_bytes_honors_retry_after_header(sleep_calls):
    attempts = []

    def handler(request):
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(429, headers={"Retry-After": "5"})
        return httpx.Response(200, headers=HTML_HEADERS, content=b"<html>ok</html>")

    with make_client(handler) as client:
        body = fetch_bytes(client, "https://host/", retry_delay=1.0, retries=3)

    assert body == b"<html>ok</html>"
    assert sleep_calls == [5.0]


def test_fetch_bytes_falls_back_to_retry_delay_on_invalid_retry_after(sleep_calls):
    attempts = []

    def handler(request):
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(429, headers={"Retry-After": "soon"})
        return httpx.Response(200, headers=HTML_HEADERS, content=b"<html>ok</html>")

    with make_client(handler) as client:
        fetch_bytes(client, "https://host/", retry_delay=2.0, retries=3)

    assert sleep_calls == [2.0]


def test_fetch_bytes_caps_backoff_delay_at_30s(sleep_calls):
    def handler(request):
        return httpx.Response(429)

    with make_client(handler) as client:
        with pytest.raises(RuntimeError):
            fetch_bytes(client, "https://host/", retry_delay=20.0, retries=3)

    assert sleep_calls == [20.0, 30.0, 30.0]


def test_fetch_bytes_retries_on_request_error(sleep_calls):
    attempts = []

    def handler(request):
        attempts.append(request)
        if len(attempts) == 1:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, headers=HTML_HEADERS, content=b"<html>ok</html>")

    with make_client(handler) as client:
        body = fetch_bytes(client, "https://host/", retry_delay=1.0, retries=3)

    assert body == b"<html>ok</html>"
    assert len(attempts) == 2


def test_save_html_writes_file_under_hostname(tmp_path):
    body = b"<html>content</html>"
    path = save_html("www.tuepedia.de", str(tmp_path), "https://www.tuepedia.de/wiki/a", body)

    saved = Path(path)
    assert saved.parent == tmp_path / "www.tuepedia.de"
    assert saved.suffix == ".html"
    assert "wiki-a" in saved.name
    assert saved.read_bytes() == body


def test_save_html_distinguishes_urls_with_same_slug(tmp_path):
    first = save_html("host", str(tmp_path), "https://host/wiki/a", b"first")
    second = save_html("host", str(tmp_path), "https://host/wiki/a/", b"second")

    assert first != second
    assert Path(first).read_bytes() == b"first"
    assert Path(second).read_bytes() == b"second"
