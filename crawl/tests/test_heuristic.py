import tuebingen_crawler.heuristic as heuristic
from tuebingen_crawler.heuristic import Language, detect_language, link_score, evaluate_page


def test_detect_language_uses_lang_attribute_without_loading_stopwords(monkeypatch):
    def fail_load_stopwords():
        raise AssertionError("stopwords should not be loaded for short text")

    monkeypatch.setattr(heuristic, "load_stopwords", fail_load_stopwords)

    assert detect_language("short text", "en") is Language.EN


def test_detect_language_uses_cached_nltk_stopwords(monkeypatch):
    monkeypatch.setattr(heuristic, "_STOPWORDS", ({"und", "der"}, {"the", "and"}))

    text = " ".join(
        [
            "the", "and", "the", "and", "the", "and",
            "university", "town", "river", "city", "history",
        ]
        * 3
    )

    assert detect_language(text) is Language.EN


def test_detect_language_trusts_non_english_lang_attribute(monkeypatch):
    def fail_load_stopwords():
        raise AssertionError("stopwords should not decide when lang is declared")

    monkeypatch.setattr(heuristic, "load_stopwords", fail_load_stopwords)

    english_looking = " ".join(["a", "i", "o", "it", "do", "as"] * 20)
    assert detect_language(english_looking, "cs") is Language.UNKNOWN


def test_link_score_normalizes_parent_www_host():
    score = link_score(
        anchor="About",
        url="https://uni-tuebingen.de/about",
        parent_relevance=heuristic.REL_THRESHOLD,
        parent_host="www.uni-tuebingen.de",
    )

    expected = (
        heuristic.LINK_FEATURE_WEIGHTS["url_has_tuebingen"]
        + heuristic.LINK_FEATURE_WEIGHTS["parent_relevant"]
        + heuristic.LINK_FEATURE_WEIGHTS["internal_link"]
    )
    assert score == expected


def test_link_score_does_not_prefer_known_hosts_without_tuebingen_terms():
    known_host_score = link_score(
        anchor="About",
        url="https://tuepedia.de/about",
        parent_relevance=0.0,
        parent_host="example.com",
    )
    unknown_host_score = link_score(
        anchor="About",
        url="https://example.com/about",
        parent_relevance=0.0,
        parent_host="other.example",
    )

    assert known_host_score == unknown_host_score == 0.0


def test_link_score_still_uses_tuebingen_terms_in_url():
    score = link_score(
        anchor="About",
        url="https://uni-tuebingen.de/about",
        parent_relevance=0.0,
        parent_host="example.com",
    )

    assert score == heuristic.LINK_FEATURE_WEIGHTS["url_has_tuebingen"]


# --- topic-drift regression tests -------------------------------------------

def test_relevance_substring_pub_in_republic_does_not_count():
    # "pub" must not match inside "Republic"/"Public"; without a core Tübingen
    # term the page is not relevant at all.
    body = "The Czech Republic is a country in central Europe with many pubs. " * 5
    assert heuristic.relevance_score(
        "https://en.wikipedia.org/wiki/Czech_Republic", "Czech Republic", body
    ) == 0.0


def test_relevance_generic_terms_alone_do_not_qualify():
    body = ("This list ranks restaurants and hotels. Restaurant, restaurant, "
            "hotel, cafe, bistro, brewery, pub. ") * 10
    assert heuristic.relevance_score(
        "https://en.wikipedia.org/wiki/List_of_restaurants",
        "List of Michelin-starred restaurants", body,
    ) == 0.0


def test_relevance_keeps_real_tuebingen_page():
    body = ("Tübingen is a university town on the river Neckar. The old town of "
            "Tübingen and the university of Tübingen attract many visitors. ") * 5
    score = heuristic.relevance_score(
        "https://en.wikipedia.org/wiki/T%C3%BCbingen", "Tübingen", body
    )
    assert score >= heuristic.REL_THRESHOLD


def test_relevance_named_entity_without_word_tuebingen_qualifies():
    # Bebenhausen is a Tübingen district; should qualify via the named-core list.
    body = ("Bebenhausen Abbey is a former Cistercian monastery near the town. "
            "The Bebenhausen monastery is a popular destination. ") * 5
    score = heuristic.relevance_score(
        "https://en.wikipedia.org/wiki/Bebenhausen_Abbey", "Bebenhausen Abbey", body
    )
    assert score >= heuristic.REL_THRESHOLD


def test_relevance_title_only_match_qualifies():
    # a page titled about Tübingen counts even with a neutral body (recall)
    body = "A museum showing art, coins and prehistoric artefacts to its visitors. " * 5
    score = heuristic.relevance_score(
        "https://example.com/museum", "Tübingen City Museum", body
    )
    assert score >= heuristic.REL_THRESHOLD


def test_relevance_single_incidental_mention_is_filtered():
    # one passing mention of Tübingen in an otherwise off-topic page is too weak
    body = ("This article is about German universities in general. "
            "Heidelberg, Munich and Tübingen are mentioned once. ") + (
            "Universities educate students across many disciplines. " * 30)
    score = heuristic.relevance_score(
        "https://example.com/german-universities", "German universities", body
    )
    assert score < heuristic.REL_THRESHOLD


def test_link_score_does_not_chase_republic_url():
    # /Czech_Republic with a generic anchor gains no tuebingen url/anchor bonus.
    score = link_score(
        anchor="Czech Republic",
        url="https://en.wikipedia.org/wiki/Czech_Republic",
        parent_relevance=0.0,
        parent_host="en.wikipedia.org",
    )
    # only the internal_link feature may apply, never the tuebingen features
    assert score <= heuristic.LINK_FEATURE_WEIGHTS["internal_link"]


# --- semantic modulation of the page relevance ------------------------------

_TUEBINGEN_URL = "https://en.wikipedia.org/wiki/T%C3%BCbingen"
_TUEBINGEN_BODY = (
    "Tübingen is a university town on the river Neckar. The old town of "
    "Tübingen and the university of Tübingen attract many visitors. "
) * 5


def test_evaluate_page_rejects_offtopic_english_page(monkeypatch):
    # an English page without a lexical signal is run through the model, but a
    # low similarity keeps it out of the index.
    monkeypatch.setattr(heuristic, "topic_similarity", lambda title, text: 0.3)

    verdict = evaluate_page(
        "https://example.com/czech", "Czech Republic", "A country in Europe. " * 10
    )
    assert verdict.relevance == 0.0


def test_evaluate_page_high_similarity_keeps_lexical_score(monkeypatch):
    monkeypatch.setattr(heuristic, "topic_similarity", lambda title, text: 1.0)

    lexical = heuristic.relevance_score(_TUEBINGEN_URL, "Tübingen", _TUEBINGEN_BODY)
    verdict = evaluate_page(_TUEBINGEN_URL, "Tübingen", _TUEBINGEN_BODY, "en")

    assert verdict.relevance == lexical


def test_evaluate_page_low_similarity_demotes_to_floor(monkeypatch):
    monkeypatch.setattr(heuristic, "topic_similarity", lambda title, text: 0.0)

    lexical = heuristic.relevance_score(_TUEBINGEN_URL, "Tübingen", _TUEBINGEN_BODY)
    verdict = evaluate_page(_TUEBINGEN_URL, "Tübingen", _TUEBINGEN_BODY, "en")

    assert verdict.relevance == lexical * heuristic.LEXICAL_FLOOR


def test_evaluate_page_model_can_demote_borderline_page_below_threshold(monkeypatch):
    # a url-only match (lexical == _TERM_IN_URL_SCORE) that the model finds
    # off-topic should drop below the relevance threshold.
    monkeypatch.setattr(heuristic, "topic_similarity", lambda title, text: 0.0)

    body = "An unrelated article about something else entirely. " * 10
    verdict = evaluate_page("https://www.tuebingen.de/hotel-booking", "Booking", body, "en")

    assert 0.0 < verdict.relevance < heuristic.REL_THRESHOLD


# --- semantic admission of pages without any lexical signal ------------------

# a page with no "Tübingen"/named-entity term anywhere -> lexical score is 0
_TOKENLESS_URL = "https://example.com/old-town"
_TOKENLESS_BODY = "The old town has a market square, half-timbered houses and a castle. " * 5


def test_evaluate_page_admits_tokenless_english_page_on_high_similarity(monkeypatch):
    monkeypatch.setattr(heuristic, "topic_similarity", lambda title, text: 0.9)

    verdict = evaluate_page(_TOKENLESS_URL, "Old Town", _TOKENLESS_BODY, "en")

    assert verdict.relevance >= heuristic.REL_THRESHOLD
    # stays below strong lexical hits
    assert verdict.relevance <= heuristic.REL_THRESHOLD + heuristic.SEM_ADMIT_REL


def test_evaluate_page_rejects_tokenless_english_page_on_low_similarity(monkeypatch):
    monkeypatch.setattr(heuristic, "topic_similarity", lambda title, text: 0.4)

    verdict = evaluate_page(_TOKENLESS_URL, "Old Town", _TOKENLESS_BODY, "en")

    assert verdict.relevance == 0.0


def test_evaluate_page_skips_model_for_tokenless_non_english_page(monkeypatch):
    def fail_similarity(title, text):
        raise AssertionError("model must not run on non-English pages without lexical signal")

    monkeypatch.setattr(heuristic, "topic_similarity", fail_similarity)

    # short body + lang attribute -> detected as German without loading stopwords
    verdict = evaluate_page(_TOKENLESS_URL, "Altstadt", "Kurzer Text.", "de")

    assert verdict.relevance == 0.0
