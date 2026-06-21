from __future__ import annotations

import re
import nltk
from .semantic import topic_similarity
from .urls import normalize_host
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse
from nltk.corpus import stopwords

_STOPWORDS: tuple[set[str], set[str]] | None = None

# language detection reliable if >= 30 tokens
MIN_TOKENS_FOR_LANG = 30
# site is relevant (tuned to the compact 0–18 relevance scale)
REL_THRESHOLD = 3.0
# link is added to frontier
LINK_THRESHOLD = 4.0
# link is ignored
MAX_DEPTH = 5
# semantic model may pull a lexically-relevant page down, strong lexical should not be dropped
LEXICAL_FLOOR = 0.5


TOKEN_RE = re.compile(r"[a-zäöüß]+", re.IGNORECASE)

# SKIP
# sites wich end in these suffixes
RESOURCE_SUFFIXES = (
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".css", ".js",
    ".pdf", ".zip", ".mp4", ".mp3", ".ico", ".woff", ".woff2",
)
# overview sites 
SKIP_PATH_WORDS = {"category", "appendix", "talk"}

# TÜBINGEN
# multiple variants
TUEBINGEN_RE = re.compile(r"t[üu]e?bingen", re.IGNORECASE)
# relevant named entities without tübingen in it
NAMED_ENTITIES = (
    "bebenhausen", "neckarfront", "stocherkahn", "hölderlin",
    "chocolart", "eberhard karls",
    "lustnau", "derendingen", "unterjesingen", "hagelloch", "pfrondorf",
    "cyber valley", "neckarinsel", "steinlach", "wurmlinger kapelle", 
    "schwärzloch", "kupferbau", "wilhelmsstift"
)

# tuebingen terms in url and title score
_TERM_IN_URL_SCORE = 5.0
_TERM_IN_TITLE_SCORE = 3.0

LINK_FEATURE_WEIGHTS: dict[str, float] = {
    "anchor_has_tuebingen": 4.0,
    "url_has_tuebingen": 3.0,
    "parent_relevant": 2.0,
    "internal_link": 1.0,
}


class Language(StrEnum):
    EN = "en"
    DE = "de"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class PageVerdict:
    language: Language
    relevance: float

    @property
    def keep(self) -> bool:
        return self.is_english and self.is_relevant

    @property
    def is_english(self) -> bool:
        return self.language is Language.EN

    @property
    def is_relevant(self) -> bool:
        return self.relevance >= REL_THRESHOLD

def _check_nltk_stopwords() -> None:
    try:
        stopwords.words("english")
        stopwords.words("german")
    except LookupError:
        nltk.download("stopwords")

def _has_tuebingen(s: str) -> bool:
    s = s.lower()
    return bool(TUEBINGEN_RE.search(s)) or any(n in s for n in NAMED_ENTITIES)

def _tuebingen_hits(s: str) -> int:
    s = s.lower()
    return len(TUEBINGEN_RE.findall(s)) + sum(s.count(n) for n in NAMED_ENTITIES)

def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]

def _host(url: str) -> str:
    try:
        netloc = urlparse(url).hostname or ""
    except ValueError:
        return ""
    return normalize_host(netloc)

def _language_from_attribute(lang_attribute: str) -> Language:
    lang = lang_attribute.lower()
    if lang.startswith("en"):
        return Language.EN
    if lang.startswith("de"):
        return Language.DE
    return Language.UNKNOWN

def _is_skipable(url: str) -> bool:
    if url.lower().endswith(RESOURCE_SUFFIXES):
        return True
    path = urlparse(url).path.lower()
    return any(kw in path for kw in SKIP_PATH_WORDS)

def load_stopwords() -> tuple[set[str], set[str]]:
    global _STOPWORDS

    if _STOPWORDS is None:
        _check_nltk_stopwords()
        german_stopwords = set(stopwords.words("german"))
        english_stopwords = set(stopwords.words("english"))

        common = sorted(german_stopwords & english_stopwords)
        english_stopwords.difference_update(common)
        german_stopwords.difference_update(common)
        _STOPWORDS = german_stopwords, english_stopwords
        
    return _STOPWORDS

# POST FETCH
def detect_language(text: str, lang_attribute: str | None = None) -> Language:
    tokens = _tokenize(text)

    if len(tokens) < MIN_TOKENS_FOR_LANG:
        if lang_attribute:
            return _language_from_attribute(lang_attribute)
        return Language.UNKNOWN

    german_stopwords, english_stopwords = load_stopwords()
    en = sum(t in english_stopwords for t in tokens)
    de = sum(t in german_stopwords for t in tokens)

    if en >= 5 and en >= de:
        return Language.EN
    if de >= 5 and de >= en:
        return Language.DE

    # use <html lang="..."> as tiebreaker
    if lang_attribute:
        return _language_from_attribute(lang_attribute)
    return Language.UNKNOWN

def relevance_score(url: str, title: str, text: str) -> float:
    if not (_has_tuebingen(url) or _has_tuebingen(title) or _has_tuebingen(text)):
        return 0.0

    # score uses the full signal
    # (regex + named entities) in url, title and body
    score = 0.0
    if _has_tuebingen(url):
        score += _TERM_IN_URL_SCORE
    if _has_tuebingen(title):
        score += _TERM_IN_TITLE_SCORE

    score += min(_tuebingen_hits(text), 10)

    return score

def evaluate_page(
    url: str,
    title: str,
    text: str,
    lang_attribute: str | None = None,
) -> PageVerdict:
    lang = detect_language(text, lang_attribute)
    lexical = relevance_score(url, title, text)

    # lexical score is cheap
    # use model only if threshold is passed
    if lexical > 0.0:
        sim = topic_similarity(title, text)
        rel = lexical * (LEXICAL_FLOOR + (1.0 - LEXICAL_FLOOR) * sim)
    else:
        rel = 0.0

    return PageVerdict(
        language=lang,
        relevance=rel,
    )

# PRE FETCH
def link_score(
    anchor: str,
    url: str,
    parent_relevance: float,
    parent_host: str,
) -> float:
    if _is_skipable(url):
        return 0.0
    
    features = {
        "anchor_has_tuebingen": _has_tuebingen(anchor),
        "url_has_tuebingen": _has_tuebingen(url),
        "parent_relevant": parent_relevance >= REL_THRESHOLD,
        "internal_link": _host(url) == normalize_host(parent_host),
    }
    return sum(w for name, w in LINK_FEATURE_WEIGHTS.items() if features[name])

def should_enqueue(
    score: float,
    depth: int,
    threshold: float = LINK_THRESHOLD,
    max_depth: int = MAX_DEPTH,
) -> bool:
    return score >= threshold and depth <= max_depth