"""Command line interface: serpbench run | report | trend | check | mock-server."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .providers import load_providers
from .report import write_report, write_trend
from .runner import load_queries, run_benchmark


def load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _load_cfg(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def cmd_check(args) -> int:
    cfg = _load_cfg(args.config)
    missing = 0
    for p in load_providers(cfg, args.providers.split(",") if args.providers else None):
        ok = bool(p.api_key)
        print(f"{'OK     ' if ok else 'MISSING'}  {p.name:<12} key present: {ok}  -> {p.url}")
        missing += 0 if ok else 1
    return 1 if missing else 0


def cmd_run(args) -> int:
    cfg = _load_cfg(args.config)
    settings = cfg.get("settings", {})
    providers = load_providers(cfg, args.providers.split(",") if args.providers else None)
    absent = [p.name for p in providers if not p.api_key]
    if absent:
        print(f"Missing API key for: {', '.join(absent)}. Run `serpbench check`.", file=sys.stderr)
        return 2
    queries = load_queries(args.queries, args.limit)
    synthetic = bool(settings.get("synthetic"))
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ("-synthetic" if synthetic else "")
    run_dir = Path(args.out) / run_id
    n_req = len(queries) * args.repeats * len(providers) + args.warmup * len(providers)
    print(f"Run {run_id}: {len(queries)} queries x {args.repeats} repeats x "
          f"{len(providers)} providers (+warmup) = {n_req} billable requests", file=sys.stderr)
    if not synthetic and not args.yes:
        if input("These requests consume paid credits. Continue? [y/N] ").strip().lower() != "y":
            return 1
    meta = {
        "vantage_point": args.vantage_point, "synthetic": synthetic,
        "queries_file": args.queries,
        "queries_sha256": hashlib.sha256(Path(args.queries).read_bytes()).hexdigest()[:16],
        "config_file": args.config,
    }
    asyncio.run(run_benchmark(
        providers, queries, run_dir=run_dir, run_id=run_id, repeats=args.repeats, seed=args.seed,
        warmup=args.warmup, concurrency=args.concurrency,
        timeout=float(settings.get("timeout_seconds", 30)),
        country=settings.get("country", "us"), language=settings.get("language", "en"), meta=meta))
    write_report(run_dir)
    print(f"Done. Report: {run_dir / 'report.md'}", file=sys.stderr)
    return 0


def cmd_report(args) -> int:
    run_dir = Path(args.run)
    if not run_dir.exists():
        run_dir = Path(args.out) / args.run
    write_report(run_dir)
    print(f"Wrote {run_dir / 'report.md'}")
    return 0


def cmd_trend(args) -> int:
    path = write_trend(Path(args.results), args.vantage, args.include_synthetic)
    if path is None:
        print("No matching runs found (synthetic runs are excluded by default).")
        return 1
    print(f"Wrote {path} and {path.with_name('trend.png')}")
    return 0


def cmd_mock(args) -> int:
    from .mock_server import make_server
    srv = make_server(args.port, args.seed, args.speed)
    print(f"Mock SERP server on http://127.0.0.1:{args.port} (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv=None) -> int:
    load_dotenv()
    ap = argparse.ArgumentParser(prog="serpbench", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="execute a benchmark run")
    r.add_argument("--config", default="config/providers.yaml")
    r.add_argument("--queries", default="config/queries.csv")
    r.add_argument("--providers", help="comma-separated subset")
    r.add_argument("--repeats", type=int, default=3)
    r.add_argument("--warmup", type=int, default=1)
    r.add_argument("--seed", type=int, default=1234)
    r.add_argument("--concurrency", type=int, default=1)
    r.add_argument("--limit", type=int, help="use only the first N queries (smoke tests)")
    r.add_argument("--vantage-point", default="unspecified",
                   help="where you run from, e.g. 'aws-us-east-1' or 'home-buenos-aires'")
    r.add_argument("--out", default="results")
    r.add_argument("-y", "--yes", action="store_true", help="skip the billing confirmation")
    r.set_defaults(fn=cmd_run)

    c = sub.add_parser("check", help="verify API keys are present (never prints them)")
    c.add_argument("--config", default="config/providers.yaml")
    c.add_argument("--providers")
    c.set_defaults(fn=cmd_check)

    rp = sub.add_parser("report", help="recompute the report from stored raw data")
    rp.add_argument("--run", required=True, help="run directory or run id")
    rp.add_argument("--out", default="results")
    rp.set_defaults(fn=cmd_report)

    t = sub.add_parser("trend", help="aggregate all runs into a time series")
    t.add_argument("--results", default="results")
    t.add_argument("--vantage", help="only runs from this vantage point")
    t.add_argument("--include-synthetic", action="store_true")
    t.set_defaults(fn=cmd_trend)

    m = sub.add_parser("mock-server", help="start the local synthetic server")
    m.add_argument("--port", type=int, default=8765)
    m.add_argument("--seed", type=int, default=42)
    m.add_argument("--speed", type=float, default=1.0, help="latency scale factor (0.1 = 10x faster)")
    m.set_defaults(fn=cmd_mock)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
