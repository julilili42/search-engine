from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict
from urllib.parse import urlparse
from .models import Statistics, CrawlState, Config
from .storage import save_state, load_state
from .urls import canonical_url, extract_urls
from .fetcher import fetch_bytes, save_html
import httpx

def crawl(
    client: httpx.Client,
    starting_url: str,
    seen_urls: Dict[str, bool],
    config: Config,
    statistics: Statistics,
) -> Dict[str, str]:
    parsed_start = urlparse(starting_url)
    if not parsed_start.hostname:
        raise ValueError(f"ERROR: failed to parse starting url {starting_url}")

    allowed_host = parsed_start.hostname
    state_path = Path(config.save_dir) / allowed_host / "crawl_state.json"

    state, loaded = load_state(state_path)

    canonical_start, is_canonical = canonical_url(starting_url, starting_url, allowed_host)
    if not is_canonical:
        raise ValueError(f"ERROR: starting url {starting_url} is not canonical")

    if loaded:
        queue = state.queue
        head = state.head
        seen_urls = state.seen
        index = state.index
        statistics.fetched = state.statistics.fetched
        statistics.discovered = state.statistics.discovered
        statistics.failed = state.statistics.failed
        statistics.saved = state.statistics.saved

        if head < len(queue):
            print(f"INFO: Resuming crawl at {queue[head]}")
        else:
            print("INFO: Crawl state is already complete")
    else:
        queue = [canonical_start]
        head = 0
        seen_urls[canonical_start] = True
        index: Dict[str, str] = {}

    while head < len(queue):
        if config.max_pages >= 0 and len(index) >= config.max_pages:
            break

        current_url = queue[head]
        head += 1
        statistics.inc_discovered()

        print(f"INFO: Fetching Bytes from {current_url}")
        try:
            body = fetch_bytes(
                client=client,
                url=current_url,
                retry_delay=config.retry_delay,
                retries=config.retries,
            )
        except Exception as exc:
            print(f"ERROR: failed to fetch {current_url} with error {exc}")
            statistics.inc_failed()
            continue

        statistics.inc_fetched()
        time.sleep(config.request_delay)

        try:
            path = save_html(allowed_host, config.save_dir, current_url, body)
        except Exception as exc:
            print(f"ERROR: failed to save html {current_url} with error {exc}")
            statistics.inc_failed()
            continue

        index[current_url] = path
        statistics.inc_saved()

        try:
            extracted_urls = extract_urls(seen_urls, body, current_url, allowed_host)
        except Exception as exc:
            print(f"ERROR: failed to extract urls at {current_url} with error {exc}")
            statistics.inc_failed()
            continue

        queue.extend(extracted_urls)

        if head % config.save_state_every == 0:
            save_state(
                state_path,
                CrawlState(
                    queue=queue,
                    head=head,
                    seen=seen_urls,
                    index=index,
                    statistics=statistics,
                ),
            )
    
    save_state(
                state_path,
                CrawlState(
                    queue=queue,
                    head=head,
                    seen=seen_urls,
                    index=index,
                    statistics=statistics,
                ),
            )
    return index

# saves page summary of all crawled pages
def save_jsonl(path: str | Path, index: Dict[str, str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        for url, file_path in index.items():
            row = {"url": url, "path": file_path}
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


