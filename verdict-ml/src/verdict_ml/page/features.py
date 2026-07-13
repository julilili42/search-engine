from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PageVerdictInput:
    title: str
    url: str
    display_url: str = ""
    snippet: str = ""
    text: str = ""


def normalize_space(value: str | None) -> str:
    return " ".join((value or "").split())


def make_text(example: PageVerdictInput) -> str:
    parts = [
        f"title: {normalize_space(example.title)}",
        f"url: {normalize_space(example.url)}",
        f"display_url: {normalize_space(example.display_url)}",
        f"snippet: {normalize_space(example.snippet)}",
        f"text: {normalize_space(example.text)[:3000]}",
    ]
    return "\n".join(parts)
