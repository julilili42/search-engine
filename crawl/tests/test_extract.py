from tuebingen_crawler.models import Language
from tuebingen_crawler.extract import parse_page


def test_parse_page_extracts_metadata_text_and_links():
    page = parse_page(
        b"""
        <html lang="en">
          <head>
            <title> Tuebingen page </title>
            <meta name="description" content=" A city page ">
          </head>
          <body>
            <h1> Welcome to Tuebingen </h1>
            <script>ignored()</script>
            <p>Visible text</p>
            <a href="/more"> More info </a>
          </body>
        </html>
        """
    )

    assert page.language is Language.EN
    assert page.title == "Tuebingen page"
    assert page.description == "A city page"
    assert page.h1 == "Welcome to Tuebingen"
    assert page.links == [("/more", "More info")]
    assert "Visible text" in page.text
    assert "ignored" not in page.text


def test_parse_page_falls_back_to_open_graph_description():
    page = parse_page(
        b"""
        <html>
          <head>
            <meta property="og:description" content=" OpenGraph summary ">
          </head>
          <body></body>
        </html>
        """
    )

    assert page.description == "OpenGraph summary"
    assert page.language is Language.UNKNOWN


def test_parse_page_normalizes_declared_german_language():
    page = parse_page(b"<html lang='de-DE'><body>Hallo</body></html>")

    assert page.language is Language.DE
