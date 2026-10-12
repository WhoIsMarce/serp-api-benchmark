# Methodology

This document is the contract between the code and any article built on it. If the code and  this file disagree, that is a bug; open an issue.

## 1. Question being answered

> For the same set of queries, issued the same way, from the same place, how do SERP API
> providers compare on **speed, realiability, completeness of the data returned, similarity
> of results, and price**?

The rig does not try to answer "which provider returns the *best* results." Result quality for a search query is subjective and engine-dependent; we measure things that can be measured without a judge, and we flag disagreement (overlap) for human inspection.

## 2. Unit of observation

One **request record** = one HTPP call one provider for one query in one repeat. Stored in `results/<run_id>/requests.jsonl`, with the full response body gzippe under `raw/`.

| Field | Meaning |
| --- | --- |
| `provider`, `provider_type` | name in the config, and which adapter parsed it |
| `query_id`, `category`, `query` | from `config/queries.csv` |
| `rep` | repeat index (0-based); `-1` for warm-up |
| `warmup` | warm-up requests are stored but excluded from every statistic |
| `started_at` | UTC wall-clock time the request was issued |
| `latency_ms` | monotonic clock, request start to full body received |
| `http_status` | HTTP status if a response was received |
| `outcome` | one of the classes below |
| `n_organic` | number of organic results parsed |
| `completeness` | share of results with non-empty title / link / snippet |
| `top_links` | first 10 organic URLs (used for overlap) |
| `response_bytes` | size of the response body |

### Outcome classes (mutually exclusive, evaluated in this order)

1. `timeout`: no complete response within `timeout_seconds`.
2. `network_error`: connection-level failure (DNS, TLS, reset...).
3. `http_error`: HTTP status >=400.
4. `invalid_json`: a 2xx response whose body is not a JSON object.
5. `api_error`: JSON object with a top-level `error` key.
6. `empty`: valid JSON, no organic results.
7. `ok`: at least one organic result parsed.

**Success** means `outcome == "ok"`. Note that `empty counts as a failure. For some queries a genuinely empty result is possible; our query set is chosen so that every query
has results on the major engines, and`empty` rates are reported separately in the outcomes table so
a reader can judge.

## 3. Metrics

### 3.1 Latency

`latency_ms` is measured with `time.perf_counter()` immediately around
`httpx.AsyncClient.request(...)`, which returns after the response body has been read.
JSON parsing happens afterwards and is excluded. DNS, TCP and TLS are included for the
first request on a connection and amortised afterwards because each provider has its own
persistent client (keep-alive). Warm-up requests absorb the first connection set-up.

Reported statistics (successful requests only):

* **p50** with a 95% **bootstrap** confidence interval (2,000 resamples, seeded).
* **p95**, **p99** with linear interpolation between closest ranks.
* mean and standard deviation (for completeness; heavy tails make them poor summaries).

Why successful-only? A timed-out request has no meaningful latency (it is censored at the
timeout). Reporting failures separately keeps both statements honest.
Why bootstrap? Latency distributions are right-skewed; the normal approximation of a
median's uncertainty is poor, the bootstrap makes no distributional assumption.

### 3.2 Reliability

`success_rate = n_ok / n_requests`, with a **Wilson score interval** (95%). Wilson is
accurate for small samples and for rates near 100%, where the textbook "p +/- 1.96 sqrt(p(1-p)/n)"
interval collapses to zero width and lies.

### 3.3 Completeness

For each successful response, the share of organic results with a non-empty `title`,
`link` and `snippet`; averaged across successful requests. This captures "the vendor
returned a result but dropped half of the fields". It does **not** judge whether the
content is *correct*.

### 3.4 Overlap

For every (repeat, query) where two providers both succeeded, the Jaccard index of the
sets of normalised top-10 URLs (`metrics.normalize_url`: host lower-cased, `www.` stripped,
scheme/fragment/trailing slash removed, tracking parameters removed). Averaged across pairs.

Overlap is a *similarity* measure, not a quality measure. Its use is (a) sanity-checking that
the vendors are talking about the same search, and (b) finding queries where they diverge so a human
can look at them.

### 3.5 Cost

Only computed if you filled in `pricing.usd_per_1k_requests`. The report prints
`effective USD / 1k OK`: the list price if the vendor does not bill failures, else
`price / success_rate`. We never ship prices in the repo.

## 4. Experimental design

* **Same inputs.** All providers receive the same query text, `country`, `language`.
* **Randomised order.** For each (repeat, query) the provider order is shuffled with a
  seeded RNG. This prevents "always first" effects (cold caches, connection reuse).
* **Randomised query order** per repeat, also seeded.
* **Sequential by default** (`--concurrency 1`) so that our own concurrency does not
  distort latency. Raise it for throughput experiments and say so in the write-up.
* **Warm-up.** One discarded request per provider before measuring.
* **Repeats.** Default 3. Repeats of the same query within a run expose provider-side
  caching; compare `rep=0` with `rep>0` before claiming a latency figure (see Limitations).
* **Time.** One run is a snapshot. Claims about stability require several runs on
  different days (`serpbench trend`).

## 5. Reproducibility guarantees

* `meta.json` records: seed, repeats, concurrency, timeout, locale, git commit, Python and
  httpx versions, the SHA-256 prefix of the query file, per-provider base URL and pricing, vantage point.
* Re-running `serpbench report --run <dir>` recomputes everything from stored data and
  makes **no** API call. Deterministic: bootstrap is seeded.
* A *new* measurement cannot be bit-identical: networks and vendors change. What is
  reproducible is the method, the code, the schedule (same seed -> same order) and every
  figure derived from a stored run.

## 6. What would invalidate a result

* Adapter drift (a vendor renames a field) -> parser tests and the `empty`/`api_error` rates will show it.
* Different vantage points mixed in one chart.
* Provider-side caching producing artificially low repeat latencies.
* Query set drift (the SHA-256 in `meta.json` makes this visible).
* Vendors giving special treatment to traffic they recognise as a benchmark (cannot be ruled out, only noted).
