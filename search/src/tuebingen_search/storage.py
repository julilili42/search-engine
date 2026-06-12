import msgpack
import time
import logging

from pathlib import Path
from .models import SearchIndex, Document, Posting

logger = logging.getLogger(__name__)

def save_index(index_path: Path, search_index: SearchIndex) -> None:
    with Path(index_path).open("wb") as index_file:
        msgpack.pack(_to_msgpack(search_index), index_file, use_bin_type=True)

def _to_msgpack(search_index: SearchIndex) -> dict[str, object]:
    return {
        "documents": [
            [str(document.path), document.length, document.text_snippet]
            for document in search_index.documents
        ],
        "inverted_index": {
            term: [[posting.doc_index, posting.score] for posting in postings]
            for term, postings in search_index.inverted_index.items()
        },
    }

def load_index(index_path: str) -> SearchIndex:
    start = time.perf_counter()
    with Path(index_path).open("rb") as index_file:
        raw = msgpack.unpack(index_file, raw=False)

    index = SearchIndex(
    documents=[
            Document(path=Path(path), length=length, text_snippet=snippet)
            for path, length, snippet in raw["documents"]
            ],
    inverted_index={
            term: [Posting(doc_index, score) for doc_index, score in postings]
            for term, postings in raw["inverted_index"].items()
       },
   )
   
    logger.info(
        "Loaded %s with %d documents in %s",
        index_path,
        len(index.documents),
        elapsed(start),
    )
    return index


def elapsed(start: float) -> str:
    return f"{time.perf_counter() - start:.6f}s"

