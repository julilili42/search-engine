# Storage benchmark

Builds one index from all crawled pages, stores the same data as
MessagePack and compact JSON, and compares file size and median deserialization
time over 20 runs.

```bash
uv run python benchmark/index_storage/benchmark.py
```

Results and both index files are written to `benchmark/index_storage/output/`.
Use `--limit 500` for a quick sample run.
