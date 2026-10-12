"""Turns raw request records into a summary, a Markdown report and charts."""
from __future__ import annotations

import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

from .metrics import NAN, bootstrap_ci, clean, jaccard, normalize_url, percentile, wilson_interval


def load_run(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    with open(run_dir / "requests.jsonl", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    return meta, records


def _lat_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {k: None for k in ("p50", "p50_ci_low", "p50_ci_high", "p95", "p99",
                                  "mean", "stdev", "min", "max")}
    lo, hi = bootstrap_ci(values)
    return {
        "p50": clean(percentile(values, 50), 1), "p50_ci_low": clean(lo, 1),
        "p50_ci_high": clean(hi, 1), "p95": clean(percentile(values, 95), 1),
        "p99": clean(percentile(values, 99), 1), "mean": clean(statistics.fmean(values), 1),
        "stdev": clean(statistics.stdev(values), 1) if len(values) > 1 else None,
        "min": clean(min(values), 1), "max": clean(max(values), 1),
    }


def summarize(meta: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    recs = [r for r in records if not r.get("warmup")]
    by_provider: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        by_provider[r["provider"]].append(r)

    providers: dict[str, Any] = {}
    for name, rs in by_provider.items():
        ok = [r for r in rs if r["outcome"] == "ok"]
        n, k = len(rs), len(ok)
        lo, hi = wilson_interval(k, n)
        success_rate = k / n if n else NAN
        comps = [r["completeness"] for r in ok if r.get("completeness")]
        comp = {f: clean(statistics.fmean(c[f] for c in comps)) if comps else None
                for f in ("title", "link", "snippet", "overall")}

        pricing = (meta.get("providers", {}).get(name, {}) or {}).get("pricing") or {}
        price = pricing.get("usd_per_1k_requests")
        cost = None
        if price is not None and success_rate and not math.isnan(success_rate):
            cost = price / success_rate if pricing.get("bills_failures") else price

        cats: dict[str, Any] = {}
        for cat in sorted({r["category"] for r in rs}):
            crs = [r for r in rs if r["category"] == cat]
            cok = [r for r in crs if r["outcome"] == "ok"]
            cats[cat] = {"n": len(crs), "success_rate": clean(len(cok) / len(crs)),
                         "p50": clean(percentile([r["latency_ms"] for r in cok], 50), 1)}

        providers[name] = {
            "n_requests": n, "n_ok": k,
            "success_rate": clean(success_rate), "success_ci_low": clean(lo),
            "success_ci_high": clean(hi),
            "outcomes": dict(Counter(r["outcome"] for r in rs)),
            "latency_ms_ok_only": _lat_stats([r["latency_ms"] for r in ok]),
            "mean_organic_results": clean(statistics.fmean(r["n_organic"] for r in ok), 2) if ok else None,
            "completeness": comp,
            "effective_usd_per_1k_ok": clean(cost, 4) if cost is not None else None,
            "by_category": cats,
        }

    units: dict[tuple, dict[str, set]] = defaultdict(dict)
    for r in recs:
        if r["outcome"] == "ok":
            units[(r["rep"], r["query_id"])][r["provider"]] = {
                normalize_url(u) for u in r["top_links"]}
    overlap: dict[str, Any] = {}
    for a, b in combinations(sorted(by_provider), 2):
        vals = [jaccard(u[a], u[b]) for u in units.values() if a in u and b in u]
        vals = [v for v in vals if not math.isnan(v)]
        overlap[f"{a} vs {b}"] = {"mean_jaccard_top10": clean(statistics.fmean(vals)) if vals else None,
                                  "n_pairs": len(vals)}
    return {"meta": meta, "providers": providers, "overlap": overlap}


def _fmt(x: Any, suffix: str = "") -> str:
    return "n/a" if x is None else f"{x}{suffix}"


def _pct(x: Any) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def render_markdown(summary: dict[str, Any]) -> str:
    meta, provs = summary["meta"], summary["providers"]
    L: list[str] = []
    L.append(f"# Benchmark report: `{meta['run_id']}`\n")
    if meta.get("synthetic"):
        L.append("> **SYNTHETIC DATA.** This run used the local mock server. It validates the "
                 "measuring rig and says nothing about any real vendor.\n")
    L.append("## Run metadata\n")
    L.append("| Field | Value |\n|---|---|")
    for key in ("started_at", "finished_at", "vantage_point", "git_commit", "seed", "repeats",
                "n_queries", "warmup_requests_per_provider", "concurrency", "timeout_seconds",
                "country", "language", "python", "httpx_version", "queries_sha256"):
        L.append(f"| {key} | `{meta.get(key)}` |")
    L.append("")
    L.append("## Headline numbers (successful requests only for latency)\n")
    L.append("| Provider | Requests | Success (95% CI) | p50 ms (95% CI) | p95 ms | p99 ms | "
             "Completeness | Avg organic | Eff. USD / 1k OK |")
    L.append("|---|---:|---|---|---:|---:|---:|---:|---:|")
    for name, p in sorted(provs.items()):
        lat = p["latency_ms_ok_only"]
        L.append(
            f"| {name} | {p['n_requests']} | {_pct(p['success_rate'])} "
            f"({_pct(p['success_ci_low'])}-{_pct(p['success_ci_high'])}) | "
            f"{_fmt(lat['p50'])} ({_fmt(lat['p50_ci_low'])}-{_fmt(lat['p50_ci_high'])}) | "
            f"{_fmt(lat['p95'])} | {_fmt(lat['p99'])} | "
            f"{_pct(p['completeness']['overall'])} | {_fmt(p['mean_organic_results'])} | "
            f"{_fmt(p['effective_usd_per_1k_ok'])} |")
    L.append("")
    L.append("![latency and success](latency.png)\n")
    L.append("## Outcomes\n")
    kinds = sorted({k for p in provs.values() for k in p["outcomes"]})
    L.append("| Provider | " + " | ".join(kinds) + " |\n|---|" + "---:|" * len(kinds))
    for name, p in sorted(provs.items()):
        L.append(f"| {name} | " + " | ".join(str(p["outcomes"].get(k, 0)) for k in kinds) + " |")
    L.append("")
    L.append("## By query category (p50 ms / success)\n")
    cats = sorted({c for p in provs.values() for c in p["by_category"]})
    L.append("| Provider | " + " | ".join(cats) + " |\n|---|" + "---|" * len(cats))
    for name, p in sorted(provs.items()):
        cells = []
        for c in cats:
            d = p["by_category"].get(c)
            cells.append("n/a" if not d else f"{_fmt(d['p50'])} / {_pct(d['success_rate'])}")
        L.append(f"| {name} | " + " | ".join(cells) + " |")
    L.append("")
    L.append("## Result overlap (mean Jaccard of normalised top-10 URLs)\n")
    L.append("| Pair | Mean Jaccard | Paired samples |\n|---|---:|---:|")
    for pair, o in summary["overlap"].items():
        L.append(f"| {pair} | {_fmt(o['mean_jaccard_top10'])} | {o['n_pairs']} |")
    L.append("")
    L.append("Overlap is *not* a quality score: two engines can legitimately disagree. It tells "
             "you whether vendors return comparable pages, and it flags outliers worth "
             "inspecting by hand.\n")
    L.append("## Read this before quoting any number\n")
    L.append("* One run, one vantage point "
             f"(`{meta.get('vantage_point')}`). Latency depends on where you measure from.")
    L.append("* Latency is computed on successful requests only; failures are reported "
             "separately above. A fast vendor that fails often is not fast.")
    L.append("* Sample sizes are in the table. Wide confidence intervals mean the ranking "
             "between two vendors may not be real.")
    L.append("* Time-sensitive queries change minute to minute; their overlap is expected to be low.")
    L.append("* Re-run on different days before drawing conclusions; see `serpbench trend`.\n")
    L.append("## Reproduce\n")
    L.append("```bash\nserpbench report --run " + f"results/{meta['run_id']}\n```\n"
             "Every figure above is recomputed from `requests.jsonl` and `raw/`; no API is called.")
    return "\n".join(L) + "\n"


def render_chart(summary: dict[str, Any], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    provs = summary["providers"]
    names = sorted(provs)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))

    p50 = [provs[n]["latency_ms_ok_only"]["p50"] or 0 for n in names]
    lo = [(provs[n]["latency_ms_ok_only"]["p50"] or 0) - (provs[n]["latency_ms_ok_only"]["p50_ci_low"] or 0) for n in names]
    hi = [(provs[n]["latency_ms_ok_only"]["p50_ci_high"] or 0) - (provs[n]["latency_ms_ok_only"]["p50"] or 0) for n in names]
    p95 = [provs[n]["latency_ms_ok_only"]["p95"] or 0 for n in names]
    ax1.bar(names, p50, yerr=[lo, hi], capsize=4, label="p50 (95% bootstrap CI)")
    ax1.scatter(names, p95, color="black", marker="_", s=400, label="p95", zorder=3)
    ax1.set_ylabel("latency (ms), successful requests")
    ax1.set_title("Latency")
    ax1.legend()

    sr = [(provs[n]["success_rate"] or 0) * 100 for n in names]
    err_lo = [sr[i] - (provs[n]["success_ci_low"] or 0) * 100 for i, n in enumerate(names)]
    err_hi = [(provs[n]["success_ci_high"] or 0) * 100 - sr[i] for i, n in enumerate(names)]
    ax2.bar(names, sr, yerr=[err_lo, err_hi], capsize=4, color="tab:green")
    ax2.set_ylim(0, 105)
    ax2.set_ylabel("success rate (%)")
    ax2.set_title("Reliability (Wilson 95% CI)")

    tag = "SYNTHETIC - rig validation only" if summary["meta"].get("synthetic") else \
        f"vantage point: {summary['meta'].get('vantage_point')}"
    fig.suptitle(f"{summary['meta']['run_id']}  |  {tag}", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def write_report(run_dir: Path) -> dict[str, Any]:
    meta, records = load_run(run_dir)
    summary = summarize(meta, records)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    render_chart(summary, run_dir / "latency.png")
    (run_dir / "report.md").write_text(render_markdown(summary), encoding="utf-8")
    return summary


def build_trend(results_dir: Path, vantage: str | None = None,
                include_synthetic: bool = False) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sp in sorted(results_dir.glob("*/summary.json")):
        s = json.loads(sp.read_text(encoding="utf-8"))
        meta = s["meta"]
        if meta.get("synthetic") and not include_synthetic:
            continue
        if vantage and meta.get("vantage_point") != vantage:
            continue
        for name, p in s["providers"].items():
            lat = p["latency_ms_ok_only"]
            rows.append({"run_id": meta["run_id"], "started_at": meta["started_at"],
                         "vantage_point": meta.get("vantage_point"), "provider": name,
                         "n_requests": p["n_requests"], "success_rate": p["success_rate"],
                         "p50_ms": lat["p50"], "p50_ci_low": lat["p50_ci_low"],
                         "p50_ci_high": lat["p50_ci_high"], "p95_ms": lat["p95"]})
    return rows


def write_trend(results_dir: Path, vantage: str | None, include_synthetic: bool) -> Path | None:
    rows = build_trend(results_dir, vantage, include_synthetic)
    if not rows:
        return None
    csv_path = results_dir / "trend.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))
    for name in sorted({r["provider"] for r in rows}):
        rs = [r for r in rows if r["provider"] == name]
        x = [r["run_id"][:8] for r in rs]
        ax1.plot(x, [r["p50_ms"] for r in rs], marker="o", label=name)
        ax2.plot(x, [(r["success_rate"] or 0) * 100 for r in rs], marker="o", label=name)
    ax1.set_title("p50 latency over runs (ms)")
    ax2.set_title("success rate over runs (%)")
    for ax in (ax1, ax2):
        ax.tick_params(axis="x", rotation=45)
        ax.legend()
    note = f"vantage point: {vantage}" if vantage else "all vantage points (do not compare across them!)"
    fig.suptitle(note, fontsize=9)
    fig.tight_layout()
    fig.savefig(results_dir / "trend.png", dpi=140)
    plt.close(fig)
    return csv_path
