from __future__ import annotations

from html.parser import HTMLParser
from typing import Dict, List, Tuple
from urllib.parse import urljoin, urlparse, urlunparse


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return

        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)



def canonical_url(raw_url: str, base_url: str, allowed_host: str) -> Tuple[str, bool]:
    absolute = urljoin(base_url, raw_url)
    parsed = urlparse(absolute)

    if parsed.scheme not in {"http", "https"}:
        return "", False

    if parsed.hostname != allowed_host:
        return "", False

    path = parsed.path
    if path != "/":
        path = path.rstrip("/")

    netloc = parsed.netloc.lower()

    final_url = urlunparse((
        parsed.scheme,
        netloc,
        path,
        "",  # params
        "",  # query ignored
        "",  # fragment ignored
    ))
    return final_url, True


def extract_urls(
    seen_urls: Dict[str, bool],
    body: bytes,
    current_url: str,
    allowed_host: str,
) -> List[str]:
    parser = LinkExtractor()
    parser.feed(body.decode("utf-8", errors="replace"))

    urls: List[str] = []
    for href in parser.hrefs:
        final_url, is_canonical = canonical_url(href, current_url, allowed_host)
        if not is_canonical:
            continue

        if not seen_urls.get(final_url, False):
            seen_urls[final_url] = True
            urls.append(final_url)

    return urls


def url_slug(page_url: str) -> str:
    parsed = urlparse(page_url)

    slug = parsed.path.strip("/")
    if not slug:
        slug = "index"

    if parsed.query:
        slug += "-" + parsed.query

    for old in ["/", "?", "&", "=", ":", "@", "%", "#"]:
        slug = slug.replace(old, "-")

    slug = slug.strip("-._").lower()

    if len(slug) > 90:
        slug = slug[:90].strip("-._")

    return slug or "page"
