from __future__ import annotations

import logging
import time
import httpx
from http import HTTPStatus
from .models import FetchResult
from .models import CrawlState, CrawlSite

logger = logging.getLogger(__name__)


def fetch_page(
      client: httpx.Client,
      url: str,
      site: CrawlSite,
      state: CrawlState,
  ) -> FetchResult | None:
      try:
          result = fetch_bytes(
              client=client,
              url=url,
              retry_delay=site.retry_delay,
              retries=site.retries,
          )
      except Exception:
          logger.error("%-7s | %-3s | %-5.1s | %s", "FAILED", "-", "-", url)
          state.statistics.failed += 1
          return None

      state.statistics.fetched += 1
      time.sleep(site.request_delay)
      return result

def fetch_bytes(
    client: httpx.Client,
    url: str,
    retry_delay: float,
    retries: int,
) -> FetchResult:
    for attempt in range(retries):
        if attempt > 0:
            logger.info("Retry attempt %d...", attempt)

        try:
            response = client.get(url)
            status_code = response.status_code
            content_type = response.headers.get("Content-Type", "")
            media_type = content_type.partition(";")[0].strip().lower()

            if status_code == HTTPStatus.TOO_MANY_REQUESTS:
                # last retry no delay
                if attempt == retries - 1: 
                    return FetchResult(None, status_code, media_type)

                # extract retry after field from header to get exact delay time
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = (
                        float(retry_after)
                        if retry_after is not None
                        else (attempt + 1) * retry_delay
                    )
                except ValueError:
                    # extraction was not successfull, use delay probing...
                    delay = (attempt + 1) * retry_delay

                delay = min(delay, 30.0)
                logger.warning("Rate limited. Waiting %ss", delay)

                time.sleep(delay)
                continue
            
            if status_code < 200 or status_code >= 300:
                logger.warning("Bad status %d for %s", status_code, url)
                return FetchResult(None, status_code, media_type)

            if media_type not in {"text/html", "application/xhtml+xml"}:
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
