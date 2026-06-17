from pathlib import Path
import csv
from .search import search_index, load_index
from .models import SearchResult

# in vscode select identation to tab, else tabs are translated to spaces
def import_batch(import_path: Path) -> dict[int, str]:
    batch = {}
    with open(import_path, encoding="utf-8", newline="") as batch_data:
        reader = csv.reader(batch_data, delimiter="\t")

        for row_number, row in enumerate(reader, start=1):
            if not row:
                continue

            if len(row) != 2:
                raise ValueError(f"Invalid format in line {row_number}: {row}")

            query_id, query = row 

            try:
                query_id = int(query_id.strip())
            except ValueError as exc:
                raise ValueError(f"Invalid query ID in line {row_number}: {query_id}") from exc

            batch[query_id] = query.strip()

    return batch

def search_batch(index_path: Path, batch: dict[int, str], top_n: int) -> dict[int, list[SearchResult]]: 
    search_results = {}
    index = load_index(index_path)
    for query_id, query in batch.items():
        search_results[query_id] = search_index(index, query, top_n)
    return search_results

def export_batch(export_path: Path, search_results: dict[int, list[SearchResult]]) -> None:
    with export_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, delimiter="\t")
        for query_id, query_results in search_results.items():
            # since url has type str | None
            ranked = [r for r in query_results if r.url]
            for result_id, result in enumerate(ranked, start=1):
                writer.writerow([
                    query_id,
                    result_id,
                    result.url,
                    f"{result.score:.4f}",
                ])

def run_batch(index_path: Path, import_path: Path, export_path: Path, top_n: int) -> None:
    batch = import_batch(import_path)
    search_results = search_batch(index_path, batch, top_n)
    export_batch(export_path, search_results)