from __future__ import annotations

import re

import nltk
from nltk.corpus import stopwords

from .models import Language, PageVerdict, REL_THRESHOLD
from .semantic import topic_similarity
from .tuebingen_terms import has_tuebingen, tuebingen_hits

_STOPWORDS: tuple[set[str], set[str]] | None = None

# language detection reliable if >= 30 tokens
MIN_TOKENS_FOR_LANG = 30
# semantic model may pull a lexically-relevant page down, strong lexical should not be dropped
LEXICAL_FLOOR = 0.5
# minimum semantic similarity to admit a page that has no lexical signal at all
SEM_ADMIT = 0.7
# relevance span granted to semantically admitted pages
SEM_ADMIT_REL = 2.0

TOKEN_RE = re.compile(r"[a-zäöüß]+", re.IGNORECASE)

# tuebingen terms in url and title score
_TERM_IN_URL_SCORE = 5.0
_TERM_IN_TITLE_SCORE = 3.0

def _check_nltk_stopwords() -> None:
    try:
        stopwords.words("english")
        stopwords.words("german")
    except LookupError:
        nltk.download("stopwords")

def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]

def _language_from_attribute(lang_attribute: str) -> Language:
    lang = lang_attribute.lower()
    if lang.startswith("en"):
        return Language.EN
    if lang.startswith("de"):
        return Language.DE
    return Language.UNKNOWN

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

def detect_language(text: str, lang_attribute: str | None = None) -> Language:
    if lang_attribute:
        return _language_from_attribute(lang_attribute)

    tokens = _tokenize(text)
    if len(tokens) < MIN_TOKENS_FOR_LANG:
        return Language.UNKNOWN

    german_stopwords, english_stopwords = load_stopwords()
    en = sum(t in english_stopwords for t in tokens)
    de = sum(t in german_stopwords for t in tokens)

    if en >= 5 and en >= de:
        return Language.EN
    if de >= 5 and de >= en:
        return Language.DE

    return Language.UNKNOWN

def relevance_score(url: str, title: str, text: str) -> float:
    if not (has_tuebingen(url) or has_tuebingen(title) or has_tuebingen(text)):
        return 0.0

    score = 0.0
    if has_tuebingen(url):
        score += _TERM_IN_URL_SCORE
    if has_tuebingen(title):
        score += _TERM_IN_TITLE_SCORE

    score += min(tuebingen_hits(text), 10)

    return score

def classify_page(
    url: str,
    title: str,
    text: str,
    lang_attribute: str | None = None,
) -> PageVerdict:
    lang = detect_language(text, lang_attribute)
    lexical = relevance_score(url, title, text)

    if lexical > 0.0:
        # known-relevant page: the model only refines the lexical score
        sim = topic_similarity(title, text)
        rel = lexical * (LEXICAL_FLOOR + (1.0 - LEXICAL_FLOOR) * sim)
    elif lang is Language.EN:
        # no lexical signal, the model admits clearly on-topic English pages
        sim = topic_similarity(title, text)
        if sim >= SEM_ADMIT:
            rel = REL_THRESHOLD + SEM_ADMIT_REL * (sim - SEM_ADMIT) / (1.0 - SEM_ADMIT)
        else:
            rel = 0.0
    else:
        rel = 0.0

    return PageVerdict(language=lang, relevance=rel)