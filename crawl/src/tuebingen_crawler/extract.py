from __future__ import annotations

from dataclasses import dataclass, field

from selectolax.lexbor import LexborHTMLParser


@dataclass(frozen=True)
class ExtractConfig:
    removed_tags: tuple[str, ...] = ("script", "style", "noscript", "template")
    description_selectors: tuple[str, ...] = (
        'meta[name="description"]',
        'meta[property="og:description"]',
    )


EXTRACT_CONFIG = ExtractConfig()


@dataclass
class ParsedPage:
    title: str
    lang: str | None
    description: str
    h1: str
    text: str
    links: list[tuple[str, str]] = field(default_factory=list)  


def _normalize_text(text: str | None) -> str:
    return " ".join((text or "").split())


def _extract_lang(tree: LexborHTMLParser) -> str | None:
    html_node = tree.css_first("html")
    return html_node.attributes.get("lang") if html_node is not None else None


def _extract_title(tree: LexborHTMLParser) -> str:
    title_node = tree.css_first("title")
    return _normalize_text(title_node.text(strip=True)) if title_node else ""


def _extract_description(tree: LexborHTMLParser) -> str:
    description = ""
    for selector in EXTRACT_CONFIG.description_selectors:
        node = tree.css_first(selector)
        if node is not None:
            description = _normalize_text(node.attributes.get("content", ""))
            if description:
                break
    return description


def _extract_h1(tree: LexborHTMLParser) -> str:
    h1_node = tree.css_first("h1")
    return _normalize_text(h1_node.text(deep=True, strip=True)) if h1_node else ""


def _extract_links(tree: LexborHTMLParser) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for a in tree.css("a"):
        href = a.attributes.get("href")
        if href:
            links.append((href, _normalize_text(a.text(deep=True, strip=True))))
    return links


def _extract_text(tree: LexborHTMLParser) -> str:
    tree.strip_tags(list(EXTRACT_CONFIG.removed_tags), recursive=True)
    body_node = tree.body
    return (
        _normalize_text(body_node.text(deep=True, separator=" ", strip=True))
        if body_node is not None
        else ""
    )


def parse_page(body: bytes) -> ParsedPage:
    tree = LexborHTMLParser(body)
    # mutates parse tree
    links = _extract_links(tree)

    return ParsedPage(
        title=_extract_title(tree),
        lang=_extract_lang(tree),
        description=_extract_description(tree),
        h1=_extract_h1(tree),
        text=_extract_text(tree),
        links=links,
    )
