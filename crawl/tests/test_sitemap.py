import gzip

import httpx

from tuebingen_crawler.frontier import GlobalFrontier
from tuebingen_crawler.models import Config, CrawlContext, CrawlState
from tuebingen_crawler.sitemap import ingest_sitemaps
from tuebingen_crawler.verdict_models import VerdictModels


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
        request_delay=0.0,
        max_pages=None,
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        context = CrawlContext(
            config=Config(request_delay=0.0, request_timeout=1.0),
            client=client,
            state=state,
            page_store=None,
            link_store=None,
            robots=None,
            host_counts={},
            host_reject_counts={},
            verdict_models=VerdictModels(None, None),
        )
        queued = ingest_sitemaps(
            context,
            ["https://host.test/sitemap.xml"],
            "https://host.test/seed",
            frontier,
            0,
        )
        repeated = ingest_sitemaps(
            context,
            ["https://host.test/sitemap.xml"],
            "https://host.test/seed",
            frontier,
            0,
        )

    lease = frontier.claim()
    assert lease is not None and lease.entry.url == "https://host.test/one"
    assert queued == 1
    assert repeated == 0
    assert requests == ["https://host.test/sitemap.xml", "https://host.test/urls.xml.gz"]
