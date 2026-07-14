import math

import pytest

from tuebingen_crawler import scheduler
from tuebingen_crawler.models import Config
from tuebingen_crawler.scheduler import _run_parallel
from tuebingen_crawler.storage import generate_shared_state_path, load_shared_state


class FakeSite:
    url = "https://fake.test/"


class FakeRun:
    """Scripted stand-in for CrawlRun: a queue of (priority, name) links."""

    def __init__(self, entries, crawl_log, fail=False):
        self.entries = list(entries)  # sorted ascending: lower = better
        self.crawl_log = crawl_log
        self.fail = fail
        self.site = FakeSite()

    @property
    def has_work(self):
        return bool(self.entries)

    @property
    def head_priority(self):
        return self.entries[0][0] if self.entries else math.inf

    def run_chunk(self, max_pages):
        if self.fail:
            self.entries.clear()
            raise RuntimeError("boom")
        for _ in range(min(max_pages, len(self.entries))):
            self.crawl_log.append(self.entries.pop(0)[1])


def test_global_scheduler_prefers_best_head_across_seeds(monkeypatch):
    # single worker + chunk of 1 makes the pick order fully deterministic
    monkeypatch.setattr(scheduler, "GLOBAL_FRONTIER_WORKERS", 1)
    monkeypatch.setattr(scheduler, "WORKER_CHUNK", 1)
    log = []
    # seed A holds mediocre links, seed B holds the globally best ones
    a = FakeRun([(-1.0, "a1"), (-0.5, "a2")], log)
    b = FakeRun([(-9.0, "b1"), (-8.0, "b2"), (-7.0, "b3")], log)

    _run_parallel([a, b])

    # seed B's far better links must all be crawled before seed A gets a turn
    assert log == ["b1", "b2", "b3", "a1", "a2"]


def test_global_scheduler_reports_failing_seed_after_finishing():
    log = []
    ok = FakeRun([(-2.0, "ok1"), (-1.0, "ok2")], log)
    bad = FakeRun([(-9.0, "bad1")], log, fail=True)

    with pytest.raises(RuntimeError, match="https://fake.test/"):
        _run_parallel([ok, bad])

    assert sorted(log) == ["ok1", "ok2"]


def test_global_scheduler_handles_empty_runs():
    _run_parallel([])
    log = []
    _run_parallel([FakeRun([], log)])
    assert log == []


def test_crawl_persists_shared_state(monkeypatch, tmp_path):
    class PageStore:
        @staticmethod
        def host_counts():
            return {}

    def prepare_runs(*args, seen_urls, seen_texts, **kwargs):
        seen_urls.add("https://host/")
        seen_texts.add(123)
        return []

    monkeypatch.setattr(scheduler, "_prepare_runs", prepare_runs)

    scheduler.crawl_hostname(
        Config(save_dir=tmp_path, state_dir=tmp_path),
        PageStore(),
        None,
        None,
        None,
    )

    assert load_shared_state(generate_shared_state_path(tmp_path)) == ({"https://host/"}, {123})
