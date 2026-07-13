from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .extract import read_qrels, read_queries, search_api_results
from .metrics import Metrics, compute_metrics, format_comparison, format_metrics
from .paths import DEFAULT_DB_PATH, DEFAULT_INDEX_PATH, DEFAULT_QRELS_PATH, DEFAULT_QUERIES_PATH, DEFAULT_RUNS_DIR
from .runs import latest_runs, load_run, save_run


def run(index_path: Path, queries_path: Path, qrels_path: Path, top_n: int) -> Metrics:
    queries = read_queries(queries_path)
    qrels = read_qrels(qrels_path)
    results, latencies = search_api_results(index_path, queries, top_n)
    return compute_metrics(queries, qrels, results, latencies)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="benchmark", description="Benchmark the search API")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", description="Run the benchmark")
    add_run_args(run_parser)

    compare_parser = subparsers.add_parser("compare", description="Compare saved benchmark runs")
    compare_parser.add_argument("runs", nargs="*", type=Path, help="Two saved run JSON files")
    compare_parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)

    add_run_args(parser)
    return parser


def add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-i", "--index", type=Path, default=DEFAULT_INDEX_PATH)
    parser.add_argument("-q", "--queries", type=Path, default=DEFAULT_QUERIES_PATH)
    parser.add_argument("-r", "--qrels", type=Path, default=DEFAULT_QRELS_PATH)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--name", default="benchmark")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("-t", "--top-n", type=int, default=100)


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "compare":
        compare(args)
        return

    metrics = run(args.index, args.queries, args.qrels, args.top_n)
    print(format_metrics(metrics))

    if should_save(args):
        name = args.name
        if sys.stdin.isatty() and not args.save:
            entered = input("Run name [benchmark]: ").strip()
            name = entered or name
        path = save_run(
            runs_dir=args.runs_dir,
            db_path=args.db,
            index_path=args.index,
            queries_path=args.queries,
            qrels_path=args.qrels,
            top_n=args.top_n,
            metrics=metrics,
            name=name,
        )
        print(f"\nsaved {path}")


def should_save(args: argparse.Namespace) -> bool:
    if args.no_save:
        return False
    if args.save:
        return True
    if not sys.stdin.isatty():
        return False
    return input("\nSave benchmark run? [y/N] ").strip().lower() in {"y", "yes"}


def compare(args: argparse.Namespace) -> None:
    paths = args.runs
    if not paths:
        paths = latest_runs(args.runs_dir, 2)
    if len(paths) != 2:
        raise SystemExit("compare needs exactly two run files, or at least two saved runs")

    left, right = [load_run(path) for path in paths]
    print(f"{paths[0]}\n{paths[1]}\n")
    print(format_comparison(left, right))
