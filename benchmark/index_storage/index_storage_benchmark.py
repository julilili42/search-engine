from __future__ import annotations

import argparse
import json
import statistics
import time
from itertools import islice
from pathlib import Path

import msgpack

from tuebingen_search.indexer import index
from tuebingen_search.load_pages import PageLoad


ROOT = Path(__file__).resolve().parents[2]


class Pages:
    def __init__(self, database: Path, limit: int | None):
        self.pages = PageLoad(database)
        self.limit = limit

    def iter_html_pages(self):
        return islice(self.pages.iter_html_pages(), self.limit)


def median_ms(load, repeats: int) -> float:
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        load()
        times.append((time.perf_counter() - start) * 1_000)
    return statistics.median(times)


def run(database: Path, output: Path, limit: int | None, repeats: int) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    binary_path = output / "index.bin"
    json_path = output / "index.json"

    index(binary_path, Pages(database, limit))
    binary = binary_path.read_bytes()
    data = msgpack.unpackb(binary, raw=False)
    encoded_json = json.dumps(
        data, ensure_ascii=False, separators=(",", ":")
    ).encode()
    json_path.write_bytes(encoded_json)

    result = {
        "documents": len(data["documents"]),
        "repeats": repeats,
        "messagepack": {
            "bytes": len(binary),
            "median_load_ms": median_ms(
                lambda: msgpack.unpackb(binary, raw=False), repeats
            ),
        },
        "json": {
            "bytes": len(encoded_json),
            "median_load_ms": median_ms(lambda: json.loads(encoded_json), repeats),
        },
    }
    (output / "results.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare MessagePack and compact JSON for the same search index."
    )
    parser.add_argument(
        "--database", type=Path, default=ROOT / "data/db/pages.sqlite"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "benchmark/index_storage/output"
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--repeats", type=int, default=20)
    args = parser.parse_args()
    if (args.limit is not None and args.limit < 1) or args.repeats < 1:
        parser.error("--limit and --repeats must be positive")

    print(json.dumps(run(args.database, args.output, args.limit, args.repeats), indent=2))


if __name__ == "__main__":
    main()
