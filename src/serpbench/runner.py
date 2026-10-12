"""Executes the benchmark and writes raw, auditable data to disk.

Design rules:
  * every provider goes through the same `call_once` code path;
  * latency is wall-clock time from just before the request until the full
    response body is read (parsing is NOT included);
  * provider order is shuffled per query (seeded) so no vendor always goes first;
  * every response body is saved gzipped: any number in a report can be
    recomputed from `results/<run_id>/` without calling an API again.
"""
from __future__ import annotations

import asyncio
import csv
import gzip
import json
import random
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from . import __version__
from .metrics import completeness
from .providers import Provider

WARMUP_QUERY = "what is a web server"
MAX_RAW_BYTES = 1_000_000


@dataclass(frozen=True)
class Query:
    id: str
    category: str
    text: str


def load_queries(path: str | Path, limit: int | None = None) -> list[Query]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = [Query(r["id"].strip(), r["category"].strip(), r["query"].strip())
                for r in csv.DictReader(f)]
    return rows[:limit] if limit else rows


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=5, check=False).stdout.strip()
        return out or None
    except Exception:
        return None


async def call_once(client: httpx.AsyncClient, provider: Provider, text: str,
                    country: str, language: str) -> dict[str, Any]:
    req = provider.build(text, country, language)
    started = utcnow()
    status: int | None = None
    body = ""
    outcome = "ok"
    error: str | None = None

    t0 = time.perf_counter()
    try:
        resp = await client.request(req["method"], req["url"], params=req.get("params"),
                                    json=req.get("json"), headers=req.get("headers"))
        status, body = resp.status_code, resp.text
    except httpx.TimeoutException:
        outcome = "timeout"
    except httpx.HTTPError as exc:
        outcome, error = "network_error", type(exc).__name__
    latency_ms = (time.perf_counter() - t0) * 1000.0

    results = []
    if outcome == "ok":
        if status is not None and status >= 400:
            outcome, error = "http_error", f"HTTP {status}"
        else:
            try:
                payload = json.loads(body)
            except ValueError:
                payload = None
            if not isinstance(payload, dict):
                outcome = "invalid_json"
            else:
                api_err = provider.extract_error(payload)
                if api_err:
                    outcome, error = "api_error", api_err
                else:
                    results = provider.extract_results(payload)
                    if not results:
                        outcome = "empty"

    return {
        "started_at": started.isoformat(),
        "latency_ms": round(latency_ms, 3),
        "http_status": status,
        "outcome": outcome,
        "error": error,
        "n_organic": len(results),
        "completeness": completeness(results) if results else None,
        "top_links": [r.link for r in results[:10]],
        "response_bytes": len(body.encode("utf-8")),
        "_body": body,
    }


async def run_benchmark(
    providers: list[Provider],
    queries: list[Query],
    *,
    run_dir: Path,
    run_id: str,
    repeats: int,
    seed: int,
    warmup: int,
    concurrency: int,
    timeout: float,
    country: str,
    language: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    schedule = []
    for rep in range(repeats):
        qs = list(queries)
        rng.shuffle(qs)
        for q in qs:
            order = list(providers)
            rng.shuffle(order)
            schedule.append((rep, q, order))

    meta = dict(meta)
    meta.update({
        "run_id": run_id, "serpbench_version": __version__, "httpx_version": httpx.__version__,
        "python": sys.version.split()[0], "git_commit": git_commit(), "seed": seed,
        "repeats": repeats, "warmup_requests_per_provider": warmup, "concurrency": concurrency,
        "timeout_seconds": timeout, "country": country, "language": language,
        "n_queries": len(queries), "started_at": utcnow().isoformat(),
        "providers": {p.name: {"type": p.type_name, "base_url": p.base_url, "pricing": p.pricing}
                      for p in providers},
    })

    clients = {p.name: httpx.AsyncClient(timeout=timeout,
                                         headers={"User-Agent": f"serpbench/{__version__}"})
               for p in providers}
    lock = asyncio.Lock()
    sem = asyncio.Semaphore(max(1, concurrency))
    out = open(run_dir / "requests.jsonl", "w", encoding="utf-8")
    state = {"done": 0}

    async def emit(p: Provider, q_id: str, category: str, q_text: str, rep: int,
                   is_warmup: bool, frag: dict[str, Any]) -> None:
        body = frag.pop("_body")
        raw_rel = None
        if not is_warmup:
            raw_rel = f"raw/{p.name}/{rep}_{q_id}.json.gz"
        record = {"run_id": run_id, "provider": p.name, "provider_type": p.type_name,
                  "query_id": q_id, "category": category, "query": q_text, "rep": rep,
                  "warmup": is_warmup, "raw_path": raw_rel, **frag}
        async with lock:
            if raw_rel:
                path = run_dir / raw_rel
                path.parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(path, "wt", encoding="utf-8") as g:
                    g.write(body[:MAX_RAW_BYTES])
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()

    async def unit(rep: int, q: Query, order: list[Provider]) -> None:
        async with sem:
            for p in order:
                frag = await call_once(clients[p.name], p, q.text, country, language)
                await emit(p, q.id, q.category, q.text, rep, False, frag)
        state["done"] += 1
        if state["done"] % 10 == 0 or state["done"] == len(schedule):
            print(f"  [{state['done']}/{len(schedule)}] query-rounds done", file=sys.stderr)

    try:
        for _ in range(warmup):
            for p in providers:
                frag = await call_once(clients[p.name], p, WARMUP_QUERY, country, language)
                await emit(p, "warmup", "warmup", WARMUP_QUERY, -1, True, frag)
        await asyncio.gather(*(unit(rep, q, order) for rep, q, order in schedule))
    finally:
        out.close()
        await asyncio.gather(*(c.aclose() for c in clients.values()))

    meta["finished_at"] = utcnow().isoformat()
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return meta
