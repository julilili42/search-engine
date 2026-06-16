# search/tests/test_html.py
from pathlib import Path

from tuebingen_search.html import extract_text, extract_text_from_html, is_html_file


def extract(html: str) -> str:
    return extract_text(html)


def test_extracts_text_from_selected_tags():
    html = "<html><body><h1>Title</h1><p>Some paragraph.</p></body></html>"
    assert extract(html).split() == ["Title", "Some", "paragraph."]


def test_ignores_text_outside_body():
    html = "<html><head><title>Ignored</title></head><body><p>Kept</p></body></html>"
    assert extract(html).split() == ["Kept"]


def test_ignores_text_in_unselected_tags():
    html = "<body><div>skipped</div><p>kept</p><script>var x = 1;</script></body>"
    assert extract(html).split() == ["kept"]


def test_extracts_nested_selected_tags():
    html = "<body><li><p>inner</p> outer</li></body>"
    assert extract(html).split() == ["inner", "outer"]


def test_normalizes_whitespace():
    html = "<body><p>  several\n   spaced \t words  </p></body>"
    assert extract(html).split() == ["several", "spaced", "words"]


def test_converts_character_references():
    html = "<body><p>T&uuml;bingen &amp; Umgebung</p></body>"
    assert extract(html).split() == ["Tübingen", "&", "Umgebung"]


def test_table_and_caption_tags_are_selected():
    html = "<body><table><tr><th>Head</th><td>Cell</td></tr></table><figcaption>Cap</figcaption></body>"
    assert extract(html).split() == ["Head", "Cell", "Cap"]


def test_is_html_file(tmp_path):
    html_file = tmp_path / "page.html"
    html_file.write_text("<html></html>")
    upper_file = tmp_path / "page.HTML"
    upper_file.write_text("<html></html>")
    text_file = tmp_path / "notes.txt"
    text_file.write_text("text")

    assert is_html_file(html_file)
    assert is_html_file(upper_file)
    assert not is_html_file(text_file)
    assert not is_html_file(tmp_path)  # directory
    assert not is_html_file(Path(tmp_path / "missing.html"))


def test_extract_text_from_html_reads_file(tmp_path):
    file_path = tmp_path / "page.html"
    file_path.write_text(
        "<html><body><h1>Tübingen</h1><p>Eine Stadt am Neckar.</p></body></html>",
        encoding="utf-8",
    )
    text = extract_text_from_html(file_path)
    assert text.split() == ["Tübingen", "Eine", "Stadt", "am", "Neckar."]
