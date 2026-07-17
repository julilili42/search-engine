from __future__ import annotations

import logging
import time
import httpx
from http import HTTPStatus
from .models import CrawlSite, FetchResult

logger = logging.getLogger(__name__)

_HTML_MEDIA_TYPES = {"text/html", "application/xhtml+xml"}

def fetch_page(
    client: httpx.Client,
    url: str,
    site: CrawlSite,
) -> FetchResult | None:
    try:
        result = fetch_bytes(
            client=client,
            url=url,
            request_timeout=site.request_timeout,
            retry_delay=site.retry_delay,
            retries=site.retries,
        )
    except Exception:
        logger.error("%-7s | %-3s | %-5.1s | %s", "FAILED", "-", "-", url)
        return None

    return result

def fetch_bytes(
    client: httpx.Client,
    url: str,
    retry_delay: float,
    retries: int,
    request_timeout: float = 30.0,
) -> FetchResult:
    for attempt in range(retries):
        if attempt > 0:
            logger.info("Retry attempt %d...", attempt)

        try:
            response = client.get(url, follow_redirects=True, timeout=request_timeout)
            status_code = response.status_code
            content_type = response.headers.get("Content-Type", "")
            media_type = content_type.partition(";")[0].strip().lower()

            if _is_retryable_status(response):
                # last retry no delay
                if attempt == retries - 1:
                    return FetchResult(None, status_code, media_type)

                delay = _retry_delay_for(response, attempt, retry_delay)
                logger.warning(
                    "Retryable status %d for %s. Waiting %ss",
                    status_code,
                    url,
                    delay,
                )

                time.sleep(delay)
                continue

            if not response.is_success:
                logger.warning("Bad status %d for %s", status_code, url)
                return FetchResult(None, status_code, media_type)

            if media_type not in _HTML_MEDIA_TYPES:
                return FetchResult(None, status_code, media_type)

            return FetchResult(response.content, status_code, media_type)

        except httpx.RequestError as exc:
            logger.warning("Failed to fetch %s with error %s", url, exc)

            if attempt == retries - 1:
                raise RuntimeError(
                    f"Failed to fetch {url} after {retries} attempts"
                ) from exc

            delay = min((attempt + 1) * retry_delay, 30.0)
            time.sleep(delay)
            continue

def _is_retryable_status(response: httpx.Response) -> bool:
    return (
        response.status_code == HTTPStatus.TOO_MANY_REQUESTS
        or response.is_server_error
    )

def _retry_delay_for(response: httpx.Response, attempt: int, retry_delay: float) -> float:
    retry_after = response.headers.get("Retry-After")
    try:
        delay = (
            float(retry_after)
            if retry_after is not None
            else (attempt + 1) * retry_delay
        )
    except ValueError:
        delay = (attempt + 1) * retry_delay

    return min(delay, 30.0)
