from __future__ import annotations

from pathlib import Path

from selectolax.lexbor import LexborHTMLParser, LexborNode


SELECTED_TAGS = {
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "li",
    "dt",
    "dd",
    "td",
    "th",
    "caption",
    "figcaption",
    "blockquote",
    "pre",
}

SELECTED_SELECTOR = ", ".join(sorted(SELECTED_TAGS))

REMOVED_TAGS = [
    "script",
    "style",
    "noscript",
    "template",
]

BOILERPLATE_SELECTORS = [
    "nav",
    "aside",
    "form",
    "dialog",
    "button",
    "[hidden]",
    '[aria-hidden="true"]',
    '[role="navigation"]',
    '[role="complementary"]',

    "body > header",
    "body > footer",
    ".site-header",
    ".site-footer",
    "#site-header",
    "#site-footer",
    "#footer",

    ".sidebar",
    "#sidebar",
    ".breadcrumb",
    ".breadcrumbs",
    "#breadcrumbs",
    ".pagination",
    ".pager",

    ".advertisement",
    ".advert",
    ".ads",
    ".social-share",
    ".share-buttons",
    ".related-posts",
    ".recommended",

    ".cookie-banner",
    ".cookie-consent",
    ".consent-banner",
    ".login-form",

    ".comments",
    "#comments",

    ".mw-editsection",
    ".navbox",
    ".vertical-navbox",
    ".printfooter",
    "#toc",
    ".toc",
]

# Strong containers are checked first
# if one scores, we skip scoring every generic div on the page. 
# Avoids quadratic cost of computing subtree text for hundreds of nested divs
STRONG_CONTENT_SELECTOR = ", ".join(
    [
        "main",
        '[role="main"]',
        "#content",
        "#main",
        "#main-content",
        "#mw-content-text",
        ".mw-parser-output",
        ".main-content",
        ".article-content",
        ".post-content",
        ".entry-content",
    ]
)

GENERIC_CONTENT_SELECTOR = "article, section, div"

POSITIVE_HINTS = {
    "article",
    "content",
    "main",
    "post",
    "entry",
    "story",
    "text",
    "body",
    "mw-parser-output",
}

NEGATIVE_HINTS = {
    "nav",
    "menu",
    "sidebar",
    "footer",
    "comment",
    "related",
    "recommend",
    "promo",
    "advert",
    "cookie",
    "share",
    "social",
    "login",
    "search",
    "toolbar",
    "breadcrumb",
}


def is_html_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".html"


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _node_text(node: LexborNode) -> str:
    return _normalize_text(
        node.text(
            deep=True,
            separator=" ",
            strip=True,
        )
    )


def _node_hints(node: LexborNode) -> str:
    attributes = node.attributes

    values = (
        attributes.get("id"),
        attributes.get("class"),
        attributes.get("role"),
    )

    return " ".join(value for value in values if value).lower()


def _content_score(node: LexborNode) -> float:
    text = _node_text(node)
    text_length = len(text)

    if text_length < 80:
        return float("-inf")

    links = node.css("a")
    link_text_length = sum(len(_node_text(link)) for link in links)
    link_density = min(link_text_length / text_length, 1.0)

    paragraphs = node.css("p")
    paragraph_text_length = sum(len(_node_text(p)) for p in paragraphs)

    headings = node.css("h1, h2, h3")

    score = text_length * (1.0 - 0.85 * link_density)
    score += min(paragraph_text_length, 8_000) * 0.5
    score += min(len(paragraphs), 30) * 35
    score += min(len(headings), 10) * 60

    if node.tag == "main":
        score += 1_200
    elif node.tag == "article":
        score += 600

    if node.attributes.get("role") == "main":
        score += 1_000

    hints = _node_hints(node)

    if any(hint in hints for hint in POSITIVE_HINTS):
        score += 500

    if any(hint in hints for hint in NEGATIVE_HINTS):
        score -= 1_000

    return score


def _best_candidate(
    nodes: list[LexborNode],
) -> tuple[LexborNode | None, float]:
    best_node: LexborNode | None = None
    best_score = float("-inf")
    seen: set[int] = set()

    for node in nodes:
        if node.mem_id in seen:
            continue

        seen.add(node.mem_id)
        score = _content_score(node)

        if score > best_score:
            best_node = node
            best_score = score

    return best_node, best_score


def _find_main_content(body: LexborNode) -> LexborNode:
    strong_node, strong_score = _best_candidate(
        body.css(STRONG_CONTENT_SELECTOR)
    )

    if strong_node is not None and strong_score > 0:
        return strong_node

    generic_node, generic_score = _best_candidate(
        body.css(GENERIC_CONTENT_SELECTOR)
    )

    if generic_node is not None and generic_score > 0:
        return generic_node

    return body


def _is_inside(node: LexborNode, ancestor: LexborNode) -> bool:
    current: LexborNode | None = node

    while current is not None:
        if current.mem_id == ancestor.mem_id:
            return True

        current = current.parent

    return False

# Ignores duplicate text
# Example: <blockquote><p>Text</p></blockquote> => Only blockquote is extracted
def _has_selected_ancestor(
    node: LexborNode,
    root: LexborNode,
) -> bool:
    parent = node.parent

    while parent is not None:
        if parent.mem_id == root.mem_id:
            return False

        if parent.tag in SELECTED_TAGS:
            return True

        parent = parent.parent

    return False


def _extract_content_text(
    body: LexborNode,
    content_root: LexborNode,
) -> str:
    for br in content_root.css("br"):
        br.replace_with(" ")

    chunks: list[str] = []

    page_heading = body.css_first("h1")

    if (
        page_heading is not None
        and not _is_inside(page_heading, content_root)
    ):
        heading_text = _normalize_text(
            page_heading.text(deep=True, separator="", strip=False)
        )

        if heading_text:
            chunks.append(heading_text)

    for node in content_root.css(SELECTED_SELECTOR):
        if _has_selected_ancestor(node, content_root):
            continue

        text = _normalize_text(
            node.text(
                deep=True,
                separator="",
                strip=False,
            )
        )

        if not text:
            continue

        if not chunks or chunks[-1] != text:
            chunks.append(text)

    if chunks:
        return " ".join(chunks)

    return _node_text(content_root)


def extract_text(markup: str | bytes) -> str:
    tree = LexborHTMLParser(markup)

    tree.strip_tags(REMOVED_TAGS, recursive=True)

    for selector in BOILERPLATE_SELECTORS:
        for node in tree.css(selector):
            node.decompose()

    body = tree.body

    if body is None:
        return ""

    content_root = _find_main_content(body)

    return _extract_content_text(body, content_root)


def extract_text_from_html(file_path: Path) -> str:
    return extract_text(file_path.read_bytes())