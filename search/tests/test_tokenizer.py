# search/tests/test_tokenizer.py
from tuebingen_search.tokenizer import tokenize


def test_tokenize_splits_on_whitespace_and_lowercases():
    assert tokenize("Hello World") == ["hello", "world"]


def test_tokenize_drops_single_character_tokens():
    assert tokenize("a bc d ef") == ["bc", "ef"]


def test_tokenize_skips_punctuation():
    assert tokenize("hello, world! (test)") == ["hello", "world", "test"]


def test_tokenize_keeps_numbers_as_tokens():
    assert tokenize("im Jahr 1477 gegründet") == ["im", "jahr", "1477", "gegründet"]


def test_tokenize_splits_number_followed_by_letters():
    # a token starting with a digit only consumes digits, the rest starts anew
    assert tokenize("1477er") == ["1477", "er"]
    assert tokenize("42abc") == ["42", "abc"]


def test_tokenize_keeps_digits_inside_alphabetic_token():
    assert tokenize("web2py") == ["web2py"]


def test_tokenize_handles_umlauts():
    assert tokenize("Tübingen Straße") == ["tübingen", "straße"]


def test_tokenize_empty_and_whitespace_only():
    assert tokenize("") == []
    assert tokenize("   \n\t  ") == []


def test_tokenize_punctuation_only():
    assert tokenize("!?., - ()") == []
