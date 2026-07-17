from __future__ import annotations

import gzip
import logging
import time
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx

from .frontier import GlobalFrontier
from .models import CrawlState
from .urls import canonical_url

logger = logging.getLogger(__name__)

SITEMAP_SCORE = 2.5
MAX_SITEMAPS = 10
MAX_SITEMAP_URLS = 1_000
MAX_SITEMAP_BYTES = 5_000_000


def ingest_sitemaps(
    client: httpx.Client,
    sitemap_urls: list[str],
    source_url: str,
    state: CrawlState,
    frontier: GlobalFrontier,
    seed_index: int,
    request_delay: float,
    request_timeout: float,
) -> int:
    pending = list(sitemap_urls)
    queued_urls = 0
    fetched_sitemaps = 0
    while (
        pending
        and fetched_sitemaps < MAX_SITEMAPS
        and queued_urls < MAX_SITEMAP_URLS
    ):
        sitemap_url = _same_origin_url(pending.pop(), source_url)
        if sitemap_url is None:
            continue
        with frontier.lock:
            if sitemap_url in state.seen_sitemaps:
                continue
            state.seen_sitemaps.add(sitemap_url)
        body = _fetch_sitemap(
            client, sitemap_url, source_url, request_delay, request_timeout
        )
        if body is None:
            continue
        fetched_sitemaps += 1
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError:
            logger.debug("Invalid sitemap XML: %s", sitemap_url)
            continue
        if _tag(root) == "sitemapindex":
            pending.extend(_locs(root, "sitemap"))
            continue
        for location in _locs(root, "url"):
            page_url = _same_origin_url(location, sitemap_url)
            if page_url is None:
                continue
            if frontier.submit(SITEMAP_SCORE, page_url, 1, seed_index):
                queued_urls += 1
                if queued_urls >= MAX_SITEMAP_URLS:
                    break
    return queued_urls


def _fetch_sitemap(
    client: httpx.Client,
    sitemap_url: str,
    source_url: str,
    request_delay: float,
    request_timeout: float,
) -> bytes | None:
    try:
        with client.stream(
            "GET", sitemap_url, follow_redirects=True, timeout=request_timeout
        ) as response:
            if not response.is_success or not _same_origin(str(response.url), source_url):
                return None
            content_length = response.headers.get("Content-Length")
            if (
                content_length
                and content_length.isdigit()
                and int(content_length) > MAX_SITEMAP_BYTES
            ):
                return None
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_SITEMAP_BYTES:
                    return None
    except httpx.RequestError as exc:
        logger.debug("Could not fetch sitemap %s: %s", sitemap_url, exc)
        return None
    if request_delay:
        time.sleep(request_delay)
    if sitemap_url.endswith(".gz"):
        try:
            body = gzip.decompress(body)
        except OSError:
            pass  # httpx may already have decoded Content-Encoding: gzip.
    return bytes(body) if len(body) <= MAX_SITEMAP_BYTES else None


def _same_origin_url(raw_url: str, base_url: str) -> str | None:
    url, valid = canonical_url(raw_url.strip(), base_url)
    return url if valid and _same_origin(url, base_url) else None


def _same_origin(left: str, right: str) -> bool:
    left_parsed, right_parsed = urlparse(left), urlparse(right)
    return (
        left_parsed.scheme == right_parsed.scheme
        and left_parsed.netloc.lower() == right_parsed.netloc.lower()
    )


def _locs(root: ElementTree.Element, child_tag: str) -> list[str]:
    locations = []
    for child in root:
        if _tag(child) != child_tag:
            continue
        for element in child:
            if _tag(element) == "loc" and element.text:
                locations.append(element.text)
    return locations


def _tag(element: ElementTree.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]
