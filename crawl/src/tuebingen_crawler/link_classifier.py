from __future__ import annotations

from urllib.parse import urlparse

from .models import LinkVerdict, REL_THRESHOLD
from .tuebingen_terms import has_tuebingen
from .urls import normalize_host

# link is added to frontier
LINK_THRESHOLD = 4.0
# link is ignored
MAX_DEPTH = 5

# sites which end in these suffixes
RESOURCE_SUFFIXES = (
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".css", ".js",
    ".pdf", ".zip", ".mp4", ".mp3", ".ico", ".woff", ".woff2", ".webp"
)
# overview sites will be skipped
SKIP_PATH_WORDS = {"category", "appendix", "talk", "special:"}

# weights are experimentally choose 
LINK_FEATURE_WEIGHTS: dict[str, float] = {
    "anchor_has_tuebingen": 4.0,
    "url_has_tuebingen": 3.0,
    "parent_relevant": 2.0,
    "internal_link": 1.0,
}

def _host(url: str) -> str:
    try:
        netloc = urlparse(url).hostname or ""
    except ValueError:
        return ""
    return normalize_host(netloc)

def _is_skipable(url: str) -> bool:
    if url.lower().endswith(RESOURCE_SUFFIXES):
        return True
    path = urlparse(url).path.lower()
    return any(kw in path for kw in SKIP_PATH_WORDS)

def should_enqueue(
    score: float,
    depth: int,
    threshold: float = LINK_THRESHOLD,
    max_depth: int = MAX_DEPTH,
) -> bool:
    return score >= threshold and depth <= max_depth

def link_score(
    anchor: str,
    url: str,
    parent_relevance: float,
    parent_host: str,
) -> float:
    if _is_skipable(url):
        return 0.0

    features = {
        "anchor_has_tuebingen": has_tuebingen(anchor),
        "url_has_tuebingen": has_tuebingen(url),
        "parent_relevant": parent_relevance >= REL_THRESHOLD,
        "internal_link": _host(url) == normalize_host(parent_host),
    }
    return sum(w for name, w in LINK_FEATURE_WEIGHTS.items() if features[name])

def classify_link(
    anchor: str,
    url: str,
    parent_relevance: float,
    parent_host: str,
    depth: int,
) -> LinkVerdict:
    score = link_score(anchor, url, parent_relevance, parent_host)
    return LinkVerdict(url=url, score=score, enqueue=should_enqueue(score, depth))
