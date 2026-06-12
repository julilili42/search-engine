from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

SELECTED_TAGS = {
    "h1",
    "h2",
    "h3",
    "h4",
    "p",
    "li",
    "td",
    "th",
    "figcaption",
    "blockquote",
}


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_body = False
        self._selected_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag == "body":
            self._in_body = True
        if self._in_body and tag in SELECTED_TAGS:
            self._selected_depth += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._in_body and tag in SELECTED_TAGS and self._selected_depth > 0:
            self._selected_depth -= 1
            self._chunks.append(" ")
        if tag == "body":
            self._in_body = False

    def handle_data(self, data: str) -> None:
        if self._in_body and self._selected_depth > 0:
            clean_text = " ".join(data.split())
            if clean_text:
                self._chunks.append(clean_text)
                self._chunks.append(" ")

    @property
    def text(self) -> str:
        return "".join(self._chunks)


def is_html_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".html"


def extract_text_from_html(file_path: Path) -> str:
    parser = TextExtractor()
    parser.feed(file_path.read_text(encoding="utf-8"))
    return parser.text
