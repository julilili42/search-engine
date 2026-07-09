from dataclasses import dataclass
from pathlib import Path

TermFrequency = dict[str, int]
TermPosition = dict[str, list[int]]
DocumentScores = dict[int, float]
DocumentTermPositions = dict[int, TermPosition]


@dataclass(frozen=True)
class Posting:
    doc_index: int
    score: float
    positions: list[int]


@dataclass(frozen=True)
class Document:
    path: Path
    url: str | None
    length: int
    terms: tuple[str, ...]
    title: str | None = None


@dataclass(frozen=True)
class SearchIndex:
    documents: list[Document]
    inverted_index: dict[str, list[Posting]]


@dataclass(frozen=True)
class SearchResult:
    rank: int
    score: float
    path: Path
    url: str | None
    snippet: str
