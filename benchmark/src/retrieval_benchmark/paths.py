from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "benchmark" / "data"
OUTPUT_DIR = PROJECT_ROOT / "benchmark" / "output"
DEFAULT_INDEX_PATH = PROJECT_ROOT / "data" / "index" / "index.bin"
DEFAULT_QUERIES_PATH = DATA_DIR / "queries.tsv"
DEFAULT_QRELS_PATH = DATA_DIR / "qrels.tsv"
