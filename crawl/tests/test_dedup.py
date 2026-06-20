from tuebingen_crawler.dedup import NEAR_DUP_HAMMING, is_near_duplicate, simhash


def test_simhash_is_deterministic_integer():
    text = "Tübingen is an old university town on the Neckar river."

    assert simhash(text) == simhash(text)
    assert isinstance(simhash(text), int)


def test_simhash_empty_text_returns_zero():
    assert simhash("") == 0
    assert simhash("   \n\t") == 0


def test_is_near_duplicate_matches_identical_fingerprint():
    fingerprint = 0b101010

    assert is_near_duplicate(fingerprint, {fingerprint})


def test_is_near_duplicate_matches_threshold_distance():
    fingerprint = 0b0
    near = (1 << NEAR_DUP_HAMMING) - 1

    assert is_near_duplicate(fingerprint, {near})


def test_is_near_duplicate_rejects_above_threshold_distance():
    fingerprint = 0b0
    far = (1 << (NEAR_DUP_HAMMING + 1)) - 1

    assert not is_near_duplicate(fingerprint, {far})


def test_similar_text_variants_are_near_duplicates():
    first = simhash(
        "Tübingen is an old university town in southern Germany. "
        "The city lies on the Neckar river and has historic streets."
    )
    second = simhash(
        "  TÜBINGEN is an old university town in southern Germany. "
        "The city lies on the Neckar river and has historic streets.  "
    )

    assert is_near_duplicate(second, {first})


def test_unrelated_text_is_not_near_duplicate():
    first = simhash(
        "Tübingen is an old university town in southern Germany with historic streets."
    )
    second = simhash(
        "Python packaging tools install dependencies into isolated virtual environments."
    )

    assert not is_near_duplicate(second, {first})
