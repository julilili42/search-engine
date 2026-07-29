from pathlib import Path
import csv
import io
from .embeddings import load_embeddings
from .paths import DEFAULT_EMBEDDINGS_PATH
from .search import search_index, load_index
from .models import SearchIndex, SearchResult


def parse_batch(data: str) -> dict[int, str]:
    batch = {}
    for row_number, row in enumerate(csv.reader(io.StringIO(data), delimiter="\t"), start=1):
        if not row:
            continue
        if len(row) != 2:
            raise ValueError(f"Invalid format in line {row_number}: {row}")
        query_id, query = row
        try:
            query_id = int(query_id.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid query ID in line {row_number}: {query_id}") from exc
        if not query.strip():
            raise ValueError(f"Empty query in line {row_number}")
        if query_id in batch:
            raise ValueError(f"Duplicate query ID in line {row_number}: {query_id}")
        batch[query_id] = query.strip()
    if not batch:
        raise ValueError("Batch contains no queries")
    return batch


def import_batch(import_path: Path) -> dict[int, str]:
    return parse_batch(import_path.read_text(encoding="utf-8"))


def search_loaded_batch(
    index: SearchIndex, doc_embeddings, batch: dict[int, str], top_n: int
) -> dict[int, list[SearchResult]]:
    return {
        query_id: search_index(index, query, top_n, doc_embeddings=doc_embeddings)
        for query_id, query in batch.items()
    }


def search_batch(index_path: Path, batch: dict[int, str], top_n: int) -> dict[int, list[SearchResult]]:
    index = load_index(index_path)
    doc_embeddings = load_embeddings(DEFAULT_EMBEDDINGS_PATH, index.documents)
    return search_loaded_batch(index, doc_embeddings, batch, top_n)


def format_batch(search_results: dict[int, list[SearchResult]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter="\t")
    for query_id, query_results in search_results.items():
        ranked = [r for r in query_results if r.url]
        for result_id, result in enumerate(ranked, start=1):
            writer.writerow([query_id, result_id, result.url, f"{result.score:.4f}"])
    return output.getvalue()


def export_batch(export_path: Path, search_results: dict[int, list[SearchResult]]) -> None:
    export_path.write_text(format_batch(search_results), encoding="utf-8")

def run_batch(index_path: Path, import_path: Path, export_path: Path, top_n: int) -> None:
    batch = import_batch(import_path)
    search_results = search_batch(index_path, batch, top_n)
    export_batch(export_path, search_results)
