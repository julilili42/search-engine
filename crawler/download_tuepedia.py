#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


DEFAULT_API_URL = "https://www.tuepedia.de/api.php"
DEFAULT_BASE_URL = "https://www.tuepedia.de"
DEFAULT_USER_AGENT = "search-engine-tuepedia-downloader/0.1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch_bytes(
    url: str,
    user_agent: str,
    timeout: float,
    retries: int,
    accept: str,
) -> tuple[bytes, str]:
    headers = {
        "Accept": accept,
        "User-Agent": user_agent,
    }

    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(), response.geturl()
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            if not retryable or attempt >= retries:
                raise
        except urllib.error.URLError:
            if attempt >= retries:
                raise

        time.sleep(min(2**attempt, 30))

    raise RuntimeError(f"Failed to fetch {url}")


def api_get(
    api_url: str,
    params: dict[str, Any],
    user_agent: str,
    timeout: float,
    retries: int,
) -> dict[str, Any]:
    query = dict(params)
    query["format"] = "json"
    url = f"{api_url}?{urllib.parse.urlencode(query)}"
    body, _ = fetch_bytes(
        url,
        user_agent=user_agent,
        timeout=timeout,
        retries=retries,
        accept="application/json",
    )
    data = json.loads(body.decode("utf-8"))

    if "error" in data:
        error = data["error"]
        code = error.get("code", "api-error")
        message = error.get("info", "MediaWiki API error")
        raise RuntimeError(f"{code}: {message}")

    return data


def get_site_namespaces(
    api_url: str,
    user_agent: str,
    timeout: float,
    retries: int,
) -> dict[int, dict[str, Any]]:
    data = api_get(
        api_url,
        {
            "action": "query",
            "meta": "siteinfo",
            "siprop": "namespaces",
        },
        user_agent=user_agent,
        timeout=timeout,
        retries=retries,
    )
    namespaces = data["query"]["namespaces"]
    return {int(ns_id): info for ns_id, info in namespaces.items()}


def parse_namespaces(
    value: str,
    api_url: str,
    user_agent: str,
    timeout: float,
    retries: int,
) -> list[int]:
    normalized = value.strip().lower()
    site_namespaces: dict[int, dict[str, Any]] | None = None

    if normalized in {"all", "content"}:
        site_namespaces = get_site_namespaces(api_url, user_agent, timeout, retries)

    if normalized == "all":
        return sorted(ns_id for ns_id in site_namespaces or {} if ns_id >= 0)

    if normalized == "content":
        return sorted(
            ns_id
            for ns_id, info in (site_namespaces or {}).items()
            if ns_id >= 0 and (ns_id == 0 or "content" in info)
        )

    try:
        return sorted({int(part.strip()) for part in value.split(",") if part.strip()})
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--namespaces must be 'all', 'content', or comma-separated namespace IDs"
        ) from exc


def iter_pages(
    api_url: str,
    namespace_id: int,
    user_agent: str,
    timeout: float,
    retries: int,
    exclude_redirects: bool,
) -> Iterator[dict[str, Any]]:
    params: dict[str, Any] = {
        "action": "query",
        "list": "allpages",
        "apnamespace": namespace_id,
        "aplimit": "max",
    }
    if exclude_redirects:
        params["apfilterredir"] = "nonredirects"

    while True:
        data = api_get(
            api_url,
            params,
            user_agent=user_agent,
            timeout=timeout,
            retries=retries,
        )

        yield from data.get("query", {}).get("allpages", [])

        continuation = data.get("continue")
        if not continuation:
            return

        params.update(continuation)


def page_url(base_url: str, title: str) -> str:
    title_path = title.replace(" ", "_")
    encoded_title = urllib.parse.quote(title_path, safe="/:")
    return f"{base_url.rstrip('/')}/wiki/{encoded_title}"


def safe_filename(page_id: int, title: str) -> str:
    title = (
        title.replace("Ä", "Ae")
        .replace("Ö", "Oe")
        .replace("Ü", "Ue")
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    normalized = unicodedata.normalize("NFKD", title)
    ascii_title = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_title).strip("-._").lower()
    slug = re.sub(r"-{2,}", "-", slug)[:90].strip("-._")
    if not slug:
        slug = "page"
    return f"{page_id:08d}-{slug}.html"


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def load_downloaded_pages(manifest_path: Path, html_dir: Path) -> set[int]:
    downloaded: set[int] = set()
    if not manifest_path.exists():
        return downloaded

    with manifest_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            file_name = record.get("filename")
            page_id = record.get("pageid")
            if page_id is None or file_name is None:
                continue
            if (html_dir.parent / file_name).exists():
                downloaded.add(int(page_id))

    return downloaded


def write_page(target: Path, content: bytes) -> None:
    temporary_target = target.with_name(f"{target.name}.tmp")
    temporary_target.write_bytes(content)
    temporary_target.replace(target)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download TUEpedia MediaWiki pages as HTML into data/."
    )
    parser.add_argument(
        "--output",
        default="data/tuepedia",
        help="Output directory. Default: data/tuepedia",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"MediaWiki API URL. Default: {DEFAULT_API_URL}",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Wiki base URL. Default: {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--namespaces",
        default="all",
        help=(
            "Namespaces to download: 'all', 'content', or comma-separated IDs. "
            "Use '0' for only article pages. Default: all"
        ),
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Pause between page downloads in seconds. Default: 0.5",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds. Default: 30",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Retry count per request. Default: 3",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of pages, useful for testing.",
    )
    parser.add_argument(
        "--exclude-redirects",
        action="store_true",
        help="Skip MediaWiki redirect pages.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Redownload pages that already exist in the manifest.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List pages that would be downloaded without writing HTML files.",
    )
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_USER_AGENT,
        help=f"HTTP User-Agent. Default: {DEFAULT_USER_AGENT}",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    output_dir = Path(args.output)
    html_dir = output_dir / "html"
    manifest_path = output_dir / "pages.jsonl"
    error_path = output_dir / "errors.jsonl"

    namespaces = parse_namespaces(
        args.namespaces,
        api_url=args.api_url,
        user_agent=args.user_agent,
        timeout=args.timeout,
        retries=args.retries,
    )

    if not args.dry_run:
        html_dir.mkdir(parents=True, exist_ok=True)

    downloaded_pages = set() if args.force else load_downloaded_pages(manifest_path, html_dir)

    seen = 0
    downloaded = 0
    skipped = 0
    failed = 0

    for namespace_id in namespaces:
        print(f"Scanning namespace {namespace_id}...", file=sys.stderr)
        for page in iter_pages(
            args.api_url,
            namespace_id=namespace_id,
            user_agent=args.user_agent,
            timeout=args.timeout,
            retries=args.retries,
            exclude_redirects=args.exclude_redirects,
        ):
            if args.limit is not None and seen >= args.limit:
                break

            seen += 1
            page_id = int(page["pageid"])
            title = str(page["title"])
            url = page_url(args.base_url, title)
            filename = f"html/{safe_filename(page_id, title)}"
            target = output_dir / filename

            if args.dry_run:
                print(f"{page_id}\t{namespace_id}\t{title}\t{url}")
                continue

            if page_id in downloaded_pages or (target.exists() and not args.force):
                skipped += 1
                continue

            try:
                content, final_url = fetch_bytes(
                    url,
                    user_agent=args.user_agent,
                    timeout=args.timeout,
                    retries=args.retries,
                    accept="text/html,application/xhtml+xml",
                )
                write_page(target, content)
                append_jsonl(
                    manifest_path,
                    {
                        "fetched_at": utc_now(),
                        "filename": filename,
                        "final_url": final_url,
                        "namespace": namespace_id,
                        "pageid": page_id,
                        "source_url": url,
                        "title": title,
                    },
                )
                downloaded += 1
                print(f"Downloaded {downloaded}: {title}", file=sys.stderr)
            except Exception as exc:
                failed += 1
                append_jsonl(
                    error_path,
                    {
                        "error": repr(exc),
                        "failed_at": utc_now(),
                        "namespace": namespace_id,
                        "pageid": page_id,
                        "source_url": url,
                        "title": title,
                    },
                )
                print(f"Failed {title}: {exc}", file=sys.stderr)

            if args.delay > 0:
                time.sleep(args.delay)

        if args.limit is not None and seen >= args.limit:
            break

    print(
        f"Done. seen={seen} downloaded={downloaded} skipped={skipped} failed={failed}",
        file=sys.stderr,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
