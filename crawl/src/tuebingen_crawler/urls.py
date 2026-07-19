from __future__ import annotations

from urllib.parse import urljoin, urlparse, urlunparse


def normalize_host(host: str | None) -> str:
    if not host:
        return ""
    return host.lower().removeprefix("www.")


def host_from_url(url: str) -> str:
    try:
        return normalize_host(urlparse(url).hostname)
    except ValueError:
        return ""


def origin(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def same_origin(left: str, right: str) -> bool:
    left_parsed, right_parsed = urlparse(left), urlparse(right)
    return (
        left_parsed.scheme == right_parsed.scheme
        and left_parsed.netloc.lower() == right_parsed.netloc.lower()
    )


# wrapper around canonical_url
def validate_start_url(url: str) -> str:
    canonical_start, is_valid = canonical_url(url, url)
    if not is_valid:
        raise ValueError(f"ERROR: invalid starting url {url}")
    return canonical_start

# normalizes url
def canonical_url(raw_url: str, base_url: str) -> tuple[str, bool]:
    try:
        absolute = urljoin(base_url, raw_url)
        parsed = urlparse(absolute)
        hostname = parsed.hostname
    except ValueError:
        return "", False

    if parsed.scheme not in {"http", "https"} or not hostname:
        return "", False

    path = parsed.path
    if path != "/":
        path = path.rstrip("/")

    final_url = urlunparse((
        parsed.scheme,
        parsed.netloc.lower(),
        path,
        "",  # params
        "",  # query ignored
        "",  # fragment ignored
    ))
    return final_url, True


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
