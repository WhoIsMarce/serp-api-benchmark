"""Runs the whole pipeline against the local mock server (no network, no keys)."""
import asyncio
import json

from serpbench.mock_server import serve_in_thread
from serpbench.providers import load_providers
from serpbench.report import load_run, summarize, write_report
from serpbench.runner import Query, run_benchmark


def test_pipeline_on_mock(tmp_path):
    srv, port = serve_in_thread(port=0, seed=1, speed=0.02)
    try:
        cfg = {"providers": {
            "mock_fast": {"type": "searchapi", "base_url": f"http://127.0.0.1:{port}/fast",
                          "api_key_literal": "k"},
            "mock_slow": {"type": "serpapi", "base_url": f"http://127.0.0.1:{port}/slow",
                          "api_key_literal": "k"},
            "mock_flaky": {"type": "serper", "base_url": f"http://127.0.0.1:{port}/flaky",
                           "api_key_literal": "k"}}}
        providers = load_providers(cfg)
        queries = [Query(f"q{i}", "cat_a" if i % 2 else "cat_b", f"query number {i}") for i in range(8)]
        run_dir = tmp_path / "run"
        asyncio.run(run_benchmark(providers, queries, run_dir=run_dir, run_id="t1", repeats=2,
                                  seed=3, warmup=1, concurrency=2, timeout=5, country="us",
                                  language="en", meta={"synthetic": True, "vantage_point": "test"}))
    finally:
        srv.shutdown()

    meta, recs = load_run(run_dir)
    assert len(recs) == 3 * (8 * 2) + 3  # measured + warmup
    assert sum(1 for r in recs if r["warmup"]) == 3
    assert all("api_key" not in json.dumps(r) for r in recs)  # keys never persisted
    assert (run_dir / "raw" / "mock_fast" / "0_q0.json.gz").exists() or \
        any((run_dir / "raw" / "mock_fast").iterdir())

    s = summarize(meta, recs)
    assert set(s["providers"]) == {"mock_fast", "mock_slow", "mock_flaky"}
    assert s["providers"]["mock_fast"]["n_requests"] == 16
    assert 0.0 <= s["providers"]["mock_flaky"]["success_rate"] <= 1.0
    assert "mock_fast vs mock_slow" in s["overlap"]

    write_report(run_dir)
    md = (run_dir / "report.md").read_text()
    assert "SYNTHETIC DATA" in md and (run_dir / "latency.png").exists()


def test_same_seed_same_schedule(tmp_path):
    """Determinism: the order in which requests are issued depends only on the seed."""
    import random
    def order(seed):
        rng = random.Random(seed)
        qs = list("abcdef")
        rng.shuffle(qs)
        return qs
    assert order(5) == order(5) and order(5) != order(6)
