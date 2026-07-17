import gzip

import httpx

from tuebingen_crawler.frontier import GlobalFrontier
from tuebingen_crawler.models import CrawlState
from tuebingen_crawler.sitemap import ingest_sitemaps


def test_sitemap_index_enqueues_same_origin_urls_once():
    requests = []
    index = b"""<sitemapindex><sitemap><loc>https://host.test/urls.xml.gz</loc></sitemap></sitemapindex>"""
    urls = gzip.compress(
        b"""<urlset><url><loc>https://host.test/one</loc></url><url><loc>https://other.test/no</loc></url></urlset>"""
    )

    def handler(request):
        requests.append(str(request.url))
        body = index if request.url.path == "/sitemap.xml" else urls
        return httpx.Response(200, content=body, request=request)

    state = CrawlState()
    frontier = GlobalFrontier(
        state,
        request_delays={0: 0.0},
        max_pages_per_seed={0: None},
        max_discovered_per_seed={0: None},
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        queued = ingest_sitemaps(
            client,
            ["https://host.test/sitemap.xml"],
            "https://host.test/seed",
            state,
            frontier,
            0,
            0.0,
            1.0,
        )
        repeated = ingest_sitemaps(
            client,
            ["https://host.test/sitemap.xml"],
            "https://host.test/seed",
            state,
            frontier,
            0,
            0.0,
            1.0,
        )

    lease = frontier.claim()
    assert lease is not None and lease.entry.url == "https://host.test/one"
    assert queued == 1
    assert repeated == 0
    assert requests == ["https://host.test/sitemap.xml", "https://host.test/urls.xml.gz"]
