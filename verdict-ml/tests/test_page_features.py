from verdict_ml.page.features import PageVerdictInput, make_text, normalize_space


def test_normalize_space_collapses_whitespace():
    assert normalize_space("  Tuebingen\n  attractions\t today ") == "Tuebingen attractions today"
    assert normalize_space(None) == ""


def test_make_text_uses_stable_field_labels():
    text = make_text(
        PageVerdictInput(
            title=" Tuebingen   Tourism ",
            url=" https://example.test/tuebingen ",
            display_url=" example.test ",
            snippet=" Official\ncity page ",
            text=" Welcome to  Tuebingen ",
        )
    )

    assert text.splitlines() == [
        "title: Tuebingen Tourism",
        "url: https://example.test/tuebingen",
        "display_url: example.test",
        "snippet: Official city page",
        "text: Welcome to Tuebingen",
    ]
