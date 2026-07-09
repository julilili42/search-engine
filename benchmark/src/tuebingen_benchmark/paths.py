from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "pages.sqlite"
DEFAULT_INDEX_PATH = PROJECT_ROOT / "index.bin"
DEFAULT_QUERIES_PATH = PROJECT_ROOT / "benchmark" / "queries.tsv"
DEFAULT_QRELS_PATH = PROJECT_ROOT / "benchmark" / "qrels.tsv"
DEFAULT_RUNS_DIR = PROJECT_ROOT / "benchmark" / "runs"
