from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "db" / "pages.sqlite"
DEFAULT_INDEX_PATH = PROJECT_ROOT / "data" / "index" / "index.bin"
DEFAULT_QUERIES_PATH = PROJECT_ROOT / "benchmark" / "retrieval" / "queries.tsv"
DEFAULT_QRELS_PATH = PROJECT_ROOT / "benchmark" / "retrieval" / "qrels.tsv"
DEFAULT_RUNS_DIR = PROJECT_ROOT / "benchmark" / "retrieval" / "runs"
