# serpbench: a reproducible benchmark rig for SERP APIs

> **Measure, don't guess.** `serpbench` is a small, auditable Python tool that benchmarks
> SERP (search engine results page) APIs on **latency, reliability, data completeness,
> result overlap and cost**, stores every raw response, and can recompute every number in a
> report without touching an API again. It is built to back "Best X API" comparisons that an
> engineer can re-run, challenge, and still trust a year later.

---

## Status and honesty statement (please read first)

* **This repository contains a measuring rig, not results.** No vendor numbers are shipped
  here, on purpose. A benchmark number without its raw data, method and date is just an opinion
  with decimals.
* The test suite and the `mock-server` use **synthetic** data to prove that the rig measures what
  it claims to measure. Synthetic runs are labelled `-synthetic`, carry a banner in their report,
  are git-ignored, and are excluded from trend charts by default.
* Vendor adapters (endpoints, parameter names, response keys) follow the public documentation
  **as I understand it**. APIs change. Re-read the docs and re-run the tests before publishing
  anything (`docs/PUBLISHING_CHECKLIST.md`).
* Prices are never hard-coded. You enter them, with a source URL and a date.

---

## Table of contents

1. [Why this exists](#1-why-this-exists)
2. [What it measures](#2-what-it-measures)
3. [Design principles](#3-design-principles)
4. [Architecture](#4-architecture)
5. [Project layout](#5-project-layout)
6. [Quickstart (5 minutes, no API keys)](#6-quickstart-5-minutes-no-api-keys)
7. [Running a real benchmark](#7-running-a-real-benchmark)
8. [Configuration reference](#8-configuration-reference)
9. [Understanding the output](#9-understanding-the-output)
10. [The statistics, explained](#10-the-statistics-explained)
11. [Fairness controls and threats to validity](#11-fairness-controls-and-threats-to-validity)
12. [Reproduce a single number from scratch](#12-reproduce-a-single-number-from-scratch)
13. [Re-measuring over time](#13-re-measuring-over-time)
14. [Cost of a run](#14-cost-of-a-run)
15. [Adding a provider](#15-adding-a-provider)
16. [Extending beyond Google web search](#16-extending-beyond-google-web-search)
17. [Testing the rig](#17-testing-the-rig)
18. [Writing an honest article from the data](#18-writing-an-honest-article-from-the-data)
19. [Ethics, terms of service and conflicts of interest](#19-ethics-terms-of-service-and-conflicts-of-interest)
20. [FAQ](#20-faq)
21. [Roadmap](#21-roadmap)
22. [Glossary](#22-glossary)
23. [License](#23-license)

---

## 1. Why this exists

Most "best API" comparisons on the internet share the same weaknesses:

1. **The numbers are not reproducible.** Nobody says which queries, from where, with what
   timeout, how many repeats, on what day.
2. **Speed is reported without reliability.** A provider that answers in 300 ms but fails 8% of
   the time is not "fast"; it is fast *when it works*.
3. **A single run is presented as truth.** Latency on a Tuesday afternoon from one laptop is a
   data point, not a ranking.
4. **Prose has outrun data.** Text is generated (or copied) first and numbers are fitted after.
5. **Articles rot.** Vendors change plans, performance and response formats; the article stays.

`serpbench` is the answer to those five problems in code form:

| Problem | What the rig does about it |
| --- | --- |
| Not reproducible | Every run stores seed, commit, config, query-file hash, versions, vantage point |
| Speed without reliability | Outcomes are classified; success rate has a Wilson CI; latency is on successes only and failures are reported next to it |
| One run = truth | Repeats within a run, bootstrap CIs, and `serpbench trend` for runs over time |
| Prose before data | The report is generated from raw data; the article is written afterwards, from the report |
| Rot | A scheduled workflow re-measures; each result carries a date and a vantage point |

The intended audience is a technical reader who will check your work. The intended author is
someone who uses AI to move faster but verifies every claim by running code.

---

## 2. What it measures

For each provider, on the same set of queries:

| Metric | Definition | Why it matters |
| --- | --- | --- |
| **Latency** | Wall-clock ms from request start to full body received; p50 (with 95% bootstrap CI), p95, p99, on *successful* requests | Users and pipelines wait on tail latency, not the median |
| **Success rate** | Share of requests with outcome `ok`, with a 95% Wilson interval | Reliability is the other half of speed |
| **Outcome mix** | Counts of `timeout`, `network_error`, `http_error`, `invalid_json`, `api_error`, `empty`, `ok` | *How* a provider fails is as informative as how often |
| **Completeness** | Average share of organic results with non-empty title, link and snippet | Catches "valid response, missing data" |
| **Result count** | Mean number of organic results per successful response | Different defaults make comparisons unfair if hidden |
| **Overlap** | Mean Jaccard index of normalised top-10 URLs between provider pairs | Sanity check that vendors return comparable pages; flags divergence for human review |
| **Cost** | Effective USD per 1,000 *successful* requests, from the pricing *you* enter | Speed has a price |
| **By category** | p50 and success per query category (informational, navigational, commercial, technical, time-sensitive, long-tail) | Averages hide where a vendor struggles |

What it deliberately does **not** measure: whether the first result is "the best one". Relevance
is subjective and needs human judges; this tool measures what can be measured honestly and
points you at the places where a human should look.

---

## 3. Design principles

1. **One measuring code path.** Every provider goes through the same `call_once()`. Adapters only
   build the request and parse the answer, so no vendor gets friendlier treatment.
2. **Raw data first, summaries second.** Every response body is stored gzipped. The report is a
   pure function of stored data.
3. **Determinism where it is possible.** Query order, provider order and bootstrap resampling are
   seeded. The network is not deterministic and the docs do not pretend it is.
4. **Failures are data.** Nothing is retried silently, nothing is dropped. A flaky provider should
   look flaky.
5. **Small enough to audit.** The core is a few hundred lines with three runtime dependencies
   (`httpx`, `pyyaml`, `matplotlib`). Statistics are implemented from textbook definitions with unit
   tests on known values.
6. **Safe by default.** API keys come from the environment, are never written to results, and a
   real run asks for confirmation because it spends credits.
7. **Honest about its limits.** See `docs/LIMITATIONS.md`; every report ends with a
   "read this before quoting any number" section.

---

## 4. Architecture

```text
                 config/providers.yaml            config/queries.csv
                          |                               |
                          v                               v
                +-----------------+            +-------------------+
                |  providers.py   |            |   runner.py       |
 CLI            |  adapters:      |  requests  |   schedule (seed) |
 serpbench ---> |  build()        | <--------- |   call_once()     |
 (cli.py)       |  extract_*()    |            |   timing, outcome |
     |          +-----------------+            +---------+---------+
     |                                                    |
     |                                                    v
     |                                   results/<run_id>/
     |                                     meta.json
     |                                     requests.jsonl   (one line per request)
     |                                     raw/<provider>/<rep>_<query>.json.gz
     |                                                    |
     v                                                    v
 report.py  <---------------------------------------------+
   summarize()  -> summary.json
   render_*()   -> report.md, latency.png
   build_trend()-> results/trend.csv, trend.png
```

The local `mock_server.py` imitates three response shapes so the whole pipeline can be tested
offline.

### Request lifecycle

1. The CLI loads the config, resolves API keys from the environment, and refuses to start if one
   is missing.
2. The runner builds a seeded schedule: for each repeat, a shuffled query list, and for each query a
   shuffled provider order.
3. Warm-up requests (default 1 per provider, discarded from statistics) open the connections.
4. For each scheduled item, `call_once()` builds the request, starts a monotonic timer, awaits the
   response, stops the timer, *then* parses and classifies the outcome.
5. The record is appended to `requests.jsonl` and the body saved gzipped.
6. When finished, `meta.json` is written and the report is generated automatically.

---

## 5. Project layout

```text
serp-api-benchmark/
├── README.md                    <- you are here
├── LICENSE                      MIT
├── pyproject.toml               package + tooling config
├── Makefile                     shortcuts: test, lint, mock-run, run, report, trend
├── Dockerfile                   run the CLI without installing Python deps
├── .env.example                 names of the API-key variables
├── config/
│   ├── providers.yaml           real providers (pricing left empty on purpose)
│   ├── providers.mock.yaml      synthetic providers for rig testing
│   └── queries.csv              40 queries in 6 categories
├── src/serpbench/
│   ├── cli.py                   run | check | report | trend | mock-server
│   ├── providers.py             one adapter per vendor + registry
│   ├── runner.py                scheduling, timing, outcome classification, raw storage
│   ├── metrics.py               percentile, Wilson, bootstrap, URL normalisation, Jaccard
│   ├── report.py                summary.json, report.md, charts, trend
│   └── mock_server.py           synthetic local server (rig tests only)
├── tests/
│   ├── test_metrics.py          statistics against known values
│   ├── test_providers.py        parsing + request building against fixtures
│   ├── test_end_to_end.py       full pipeline against the mock server
│   └── fixtures/                hand-written minimal response shapes
├── docs/
│   ├── METHODOLOGY.md           the contract between code and article
│   ├── LIMITATIONS.md           what the numbers cannot tell you
│   └── PUBLISHING_CHECKLIST.md  gate before anything is published
├── results/                     one directory per run (raw data included)
├── APPLICATION.md               application notes for the SearchApi role
└── .github/workflows/
    ├── ci.yml                   lint, tests, mock smoke run
    └── scheduled-benchmark.yml  weekly re-measurement
```

---

## 6. Quickstart (5 minutes, no API keys)

This validates the rig on your machine using the synthetic server.

```bash
git clone <this repository> serp-api-benchmark
cd serp-api-benchmark

python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

pytest -q                            # 12 tests should pass
```

Open two terminals.

```bash
# terminal 1: start the synthetic server (latency scaled down so the demo is quick)
serpbench mock-server --port 8765 --speed 0.05

# terminal 2: run a small benchmark against it
serpbench run --config config/providers.mock.yaml \
              --repeats 3 --limit 12 \
              --vantage-point local-synthetic -y
```

You will get a directory like `results/20261006T195921Z-synthetic/` containing `report.md`,
`latency.png`, `summary.json`, `meta.json`, `requests.jsonl` and `raw/`.

**These numbers describe the mock server, nothing else.** The point of this step is to confirm
that timing, classification, statistics and reporting work end to end.

---

## 7. Running a real benchmark

### 7.1 Get keys and register them

```bash
cp .env.example .env
# edit .env: SEARCHAPI_API_KEY=..., SERPAPI_API_KEY=..., SERPER_API_KEY=...
serpbench check                      # prints OK / MISSING per provider, never the keys
```

`.env` is git-ignored. In CI use repository secrets.

### 7.2 Fill in pricing (optional but recommended)

Open `config/providers.yaml` and, for each provider, set:

```yaml
pricing:
  usd_per_1k_requests: <number from the vendor's pricing page>
  plan: "<plan name you actually use>"
  source_url: "<pricing page URL>"
  checked_on: "<YYYY-MM-DD>"
  bills_failures: false     # true if the vendor charges for failed requests
```

If you leave `usd_per_1k_requests` empty the report prints `n/a` for cost. That is better than a
guess.

### 7.3 Dry thinking before spending credits

Compute the number of billable requests (see [section 14](#14-cost-of-a-run)). A first run with
`--limit 5 --repeats 1` costs about 20 requests across three providers and confirms keys,
parsing and quotas.

```bash
serpbench run --limit 5 --repeats 1 --vantage-point home-buenos-aires
```

The CLI prints the number of billable requests and asks for confirmation (`-y` skips it).

### 7.4 The real run

```bash
serpbench run --repeats 5 --vantage-point home-buenos-aires
```

Choose the vantage-point label honestly and consistently ("aws-us-east-1", "github-actions-ubuntu",
"home-buenos-aires"). It is stored in `meta.json` and used to keep trends comparable.

### 7.5 Look at the raw data before looking at the summary

```bash
RUN=results/<run_id>
head -n 3 $RUN/requests.jsonl | python -m json.tool
zcat $RUN/raw/<provider>/0_q01.json.gz | python -m json.tool | head -60
```

If the numbers in the report do not match what you see in the raw files, the report is wrong,
not the data. Open an issue.

### 7.6 Command reference

| Command | Purpose |
| --- | --- |
| `serpbench check [--config FILE] [--providers a,b]` | Verify keys are present |
| `serpbench run [options]` | Execute a run and write the report |
| `serpbench report --run <dir or id>` | Recompute the report from stored data (no API calls) |
| `serpbench trend [--vantage X] [--include-synthetic]` | Build `results/trend.csv` and `trend.png` |
| `serpbench mock-server [--port N] [--speed F] [--seed N]` | Start the synthetic server |

`run` options:

| Option | Default | Meaning |
| --- | --- | --- |
| `--config` | `config/providers.yaml` | Providers and settings |
| `--queries` | `config/queries.csv` | Query set |
| `--providers a,b` | all enabled | Subset of providers |
| `--repeats` | 3 | Passes over the whole query set |
| `--warmup` | 1 | Discarded requests per provider |
| `--seed` | 1234 | Seed for query and provider ordering |
| `--concurrency` | 1 | Query rounds in flight; keep at 1 for latency work |
| `--limit` | all | First N queries only (smoke tests) |
| `--vantage-point` | `unspecified` | Free-text label of where you run from |
| `--out` | `results` | Output directory |
| `-y, --yes` | off | Skip the "this costs money" prompt |

---

## 8. Configuration reference

### `config/providers.yaml`

```yaml
settings:
  country: us            # sent as `gl`
  language: en           # sent as `hl`
  timeout_seconds: 30
providers:
  searchapi:             # name shown in reports; adapter = `type` or, if absent, the name
    enabled: true
    api_key_env: SEARCHAPI_API_KEY
    pricing: {...}
```

Per-provider keys:

| Key | Meaning |
| --- | --- |
| `type` | Adapter to use (`searchapi`, `serpapi`, `serper`). Defaults to the provider name |
| `enabled` | `false` to skip |
| `base_url` | Override the endpoint host (used by the mock config) |
| `api_key_env` | Environment variable holding the key |
| `api_key_literal` | Inline key; **only for the mock config**, never commit a real one |
| `extra_params` | Extra query/body parameters passed through untouched |
| `pricing` | See [7.2](#72-fill-in-pricing-optional-but-recommended) |

### `config/queries.csv`

Columns: `id,category,query`. The shipped set has 40 queries in six categories:

| Category | Count | Purpose |
| --- | ---: | --- |
| informational | 8 | Stable "how/why/what" questions |
| navigational | 6 | Brand or site lookups with an obvious top result |
| commercial | 8 | "best X" queries: ads, listicles, shopping-heavy SERPs |
| technical | 8 | Developer queries (the audience of an API company) |
| time_sensitive | 5 | Results change hour to hour: low overlap expected |
| long_tail | 5 | Rare, specific queries |

Change it freely, but treat the file as part of the method: its SHA-256 prefix is recorded in
`meta.json`, so a changed query set is visible in every report.

### Environment

| Variable | Used for |
| --- | --- |
| `SEARCHAPI_API_KEY`, `SERPAPI_API_KEY`, `SERPER_API_KEY` | Provider credentials |

A tiny built-in loader reads `.env` without overriding variables that are already set.

---

## 9. Understanding the output

Every run produces one directory:

```text
results/20261006T120000Z/
├── meta.json          everything needed to understand how the run was made
├── requests.jsonl     one JSON object per request (including warm-ups, flagged)
├── raw/<provider>/    gzipped response bodies, named <rep>_<query_id>.json.gz
├── summary.json       all aggregated statistics, machine-readable
├── report.md          human-readable report (tables + chart)
└── latency.png        p50/p95 and success-rate chart
```

### `meta.json` (selected fields)

| Field | Why it is recorded |
| --- | --- |
| `run_id`, `started_at`, `finished_at` | Identity and dates; the date belongs in every article |
| `vantage_point` | Latency is meaningless without it |
| `seed`, `repeats`, `concurrency`, `timeout_seconds` | The schedule and limits |
| `country`, `language` | Search locale |
| `git_commit` | Exact code version (when run inside a git checkout) |
| `queries_sha256` | Fingerprint of the query file |
| `python`, `httpx_version`, `serpbench_version` | Environment |
| `providers` | Base URLs and the pricing snapshot used |
| `synthetic` | `true` for mock runs |

### `report.md` sections

1. **Run metadata**: the table above.
2. **Headline numbers**: success with CI, p50 with CI, p95, p99, completeness, result count, cost.
3. **Outcomes**: counts per outcome class per provider.
4. **By query category**: p50 and success per category.
5. **Result overlap**: pairwise mean Jaccard.
6. **Read this before quoting any number**: caveats generated with the report.
7. **Reproduce**: the command that regenerates the report.

### Reading a result, with a worked example of *reasoning* (not data)

Suppose provider A has p50 = 900 ms (CI 850-950) and success 99.0%, and provider B has
p50 = 700 ms (CI 640-760) and success 93.5%. A careful sentence is: "B was faster at the median in
this run, but failed noticeably more often; whether B's failures are transient rate limits or
something else is visible in the outcomes table." A careless sentence is "B is faster."
The report is structured to make the careful sentence the easy one to write.

---

## 10. The statistics, explained

All implementations live in `src/serpbench/metrics.py` and are covered by tests with known values.

### Percentiles

Linear interpolation between closest ranks: for sorted values `s` and quantile `q`,
`k = (n-1) * q/100`, result `s[floor(k)] + (s[ceil(k)] - s[floor(k)]) * (k - floor(k))`. This is
the same definition as NumPy's default.

### Bootstrap confidence interval for the median

Latency distributions are right-skewed, with long tails from retries and cold paths. The usual
formula for the standard error of a mean does not apply to a median of such data. The
bootstrap draws `n` values *with replacement* from the observed latencies, computes the median,
repeats 2,000 times, and takes the 2.5th and 97.5th percentiles of those medians. The RNG is
seeded, so the interval is reproducible.

### Wilson score interval for success rate

For `k` successes in `n` trials:

```text
p      = k / n
centre = (p + z^2/2n) / (1 + z^2/n)
half   = z * sqrt( p(1-p)/n + z^2/4n^2 ) / (1 + z^2/n)
CI     = [centre - half, centre + half],   z = 1.96
```

Unlike the "p plus or minus 1.96 sqrt(p(1-p)/n)" interval, Wilson does not collapse to zero width
when every request succeeds (p = 1) and behaves well at small `n`. With 40 successes out of 40
requests the lower bound is still around 91%, which is the honest statement: 40 clean requests do
not prove 99.9% reliability.

### Jaccard overlap

`J(A, B) = |A intersect B| / |A union B|` on sets of normalised URLs. `1.0` means identical top-10
sets (order ignored), `0.0` means disjoint. Order-sensitive measures (rank correlation) are on the
roadmap.

### What "significant" means here

The tool does not run hypothesis tests, because a "p-value" on 120 autocorrelated network
measurements is easy to over-read. The rule of thumb in the report is simpler: **if two intervals
overlap substantially, do not claim a difference.** If you want a formal test (for example a
paired permutation test on per-query latency differences), the stored data supports it; see the
roadmap.

---

## 11. Fairness controls and threats to validity

### Controls built in

| Threat | Control |
| --- | --- |
| A provider always goes first (cold DNS, cold caches, connection reuse) | Provider order shuffled per (repeat, query), seeded |
| Query order correlates with time of day | Query order shuffled per repeat, seeded |
| First-request overhead (TLS handshakes) | Warm-up requests excluded; one persistent client per provider |
| Our own concurrency distorting latency | Sequential by default |
| Parsing time contaminating latency | Timer stops before parsing |
| Failures hidden by averaging | Outcome classes, Wilson CI, latency on successes reported next to the failure rate |
| Silent retries | None. One request is one observation |
| API key leakage | Keys are not stored in records or raw bodies; a test asserts it |
| Query set drift | SHA-256 of the file in `meta.json` |
| Cherry-picking runs | `trend` aggregates all runs; checklist forbids re-running "for a cleaner result" |

### Threats that remain (you must address them in the write-up)

1. **Vantage point.** Measure from where your readers are, or from a neutral datacentre, and say which.
2. **Caching.** If repeats are faster than first requests, say so and report `rep == 0` separately.
3. **Provider-side throttling.** A burst of requests may trip rate limits that normal usage never would.
   Watch the `http_error` / `api_error` counts.
4. **Small samples.** Respect the confidence intervals.
5. **Time of day and weekday effects.** One run per week at the same time is consistent but may
   miss peaks. Add runs at different hours before claiming stability.
6. **Feature parity.** Providers differ in defaults (number of results, device, location resolution).
   The shipped adapters send the same `q`, `gl`, `hl`; anything else is the vendor's default and
   should be listed in the article.
7. **Adapter correctness.** If an adapter targets a renamed field, success rates fall to zero
   with `empty` outcomes. That is loud by design.
8. **Conflict of interest.** See [section 19](#19-ethics-terms-of-service-and-conflicts-of-interest).

---

## 12. Reproduce a single number from scratch

This is the exercise the whole project is built around: pick a number from a published report and
reproduce it. Example: "provider X, p50 latency 812 ms".

**Reproduce it from the stored data (no network):**

```bash
git checkout <commit recorded in meta.json>
pip install -e .
serpbench report --run results/<run_id>
grep -A8 "Headline numbers" results/<run_id>/report.md
```

The p50 is the 50th percentile of `latency_ms` over records with `outcome == "ok"`, no `warmup`
flag and `provider == X`. You can verify it independently without this tool:

```bash
python - <<'PY'
import json, statistics
rows = [json.loads(l) for l in open("results/<run_id>/requests.jsonl")]
lat = [r["latency_ms"] for r in rows
       if r["provider"] == "X" and r["outcome"] == "ok" and not r["warmup"]]
print(len(lat), statistics.median(lat))
PY
```

**Reproduce it by measuring again (new data, same method):**

```bash
git checkout <commit>
cp .env.example .env              # add your own keys
serpbench run --seed <seed from meta.json> --repeats <repeats> \
              --vantage-point <your label> -y
```

Same seed gives the same query and provider *order*; latencies will differ because networks and
vendors are not frozen. A faithful replication lands within the confidence interval or explains
why it did not (different vantage point, vendor change, caching).

**The two-sentence version** (for the application and for readers):

> Check out the commit recorded in `meta.json`, run `serpbench report --run results/<run_id>` to
> recompute every figure from the stored raw responses, or `serpbench run --seed <seed>` with your
> own keys to re-measure with the same schedule. The p50 is the median `latency_ms` over
> successful, non-warm-up requests of one provider, with a seeded 2,000-resample bootstrap interval.

---

## 13. Re-measuring over time

Evergreen content is only evergreen if it stays true. Two mechanisms:

### Manual

```bash
serpbench run --repeats 3 --vantage-point home-buenos-aires -y
serpbench trend --vantage home-buenos-aires
```

`trend` reads every `results/*/summary.json`, skips synthetic runs, optionally filters by vantage
point, and writes `results/trend.csv` and `results/trend.png` (p50 and success over runs).

### Scheduled (GitHub Actions)

`.github/workflows/scheduled-benchmark.yml` runs weekly (Mondays 06:17 UTC), executes a run with
the vantage label `github-actions-ubuntu`, updates the trend and commits the results.

Things to know before enabling it:

* It spends credits every week: see [section 14](#14-cost-of-a-run).
* Its vantage point is the GitHub runner. Do not compare those numbers with laptop runs.
* Provide the keys as repository secrets.
* A trend with only two or three points is an anecdote, not a trend. Say how many runs you have.

### What to update in a published article

The article should show a "last re-measured" date, link the latest `report.md`, and say what
changed since the previous measurement, including when nothing did. Corrections are published, not
silently edited.

---

## 14. Cost of a run

Billable requests per run:

```text
queries x repeats x providers  +  warmup x providers
```

With the shipped defaults (40 queries, 3 repeats, 3 providers, 1 warm-up) that is
`40 x 3 x 3 + 3 = 363` requests. Multiply by each vendor's price per request on *your* plan to
get the spend; most plans do not charge the same for failed requests, which is why
`bills_failures` is configurable.

Ways to reduce spend while developing: `--limit 5`, `--repeats 1`, `--providers searchapi`.
Ways to increase statistical power: more repeats, more queries, runs on different days.

---

## 15. Adding a provider

1. Read the vendor's current documentation: endpoint, authentication, locale parameters, response shape.
2. Add a class in `src/serpbench/providers.py`:

```python
class ExampleApi(Provider):
    type_name = "exampleapi"
    default_base_url = "https://api.example.com"
    path = "/v1/search"

    def build(self, query, country, language):
        return {
            "method": "GET",
            "url": self.url,
            "params": {"q": query, "country": country, "lang": language, **self.extra},
            "headers": {"Authorization": f"Bearer {self.api_key}"},
        }

    def extract_results(self, payload):
        return _normalize(payload.get("results"))   # list of dicts with title/link/snippet
```

1. Register it by adding it to the tuple that builds `PROVIDER_TYPES`.
2. Add a fixture in `tests/fixtures/` (preferably a real response copied from `raw/`) and a test in
   `tests/test_providers.py`.
3. Add it to `config/providers.yaml` with an `api_key_env`.
4. Run `serpbench check`, then a tiny real run (`--limit 3 --repeats 1`) and read the raw files.

If a vendor returns the organic results under a different structure (nested objects, different key
names for link or snippet), do the mapping inside `extract_results` so that the rest of the
pipeline stays vendor-agnostic.

---

## 16. Extending beyond Google web search

SERP API companies offer dozens of engines (Bing, Baidu, YouTube, Amazon, Google Shopping, Google
Jobs...). The rig is organised so that this is a configuration and adapter problem, not a rewrite:

* **Another engine from the same vendor**: pass it via `extra_params` (for example a different
  `engine` value on vendors that use one) or define a second provider entry with the same adapter
  and a different `extra_params`. Use a different query file whose queries make sense for that
  engine (product names for shopping, job titles for jobs).
* **Different result shapes** (videos, products, jobs): extend `NormalizedResult` and
  `completeness()` with the relevant fields. Keep the old fields working so earlier runs can still be
  re-reported.
* **Per-engine reports**: run each engine as its own run with its own `--queries`, then compare
  within an engine only.

Not implemented yet: see the roadmap. This README does not claim support that the code does not have.

---

## 17. Testing the rig

```bash
pytest -q          # 12 tests
ruff check src tests
```

| File | What it proves |
| --- | --- |
| `tests/test_metrics.py` | Percentile, Wilson (known value ~[0.888, 0.979] for 95/100), seeded bootstrap, URL normalisation, Jaccard, completeness |
| `tests/test_providers.py` | Request construction and response parsing per adapter; error payloads; unknown provider rejected |
| `tests/test_end_to_end.py` | Whole pipeline against the mock server: record counts, warm-ups excluded, keys never persisted, raw files written, report and chart produced |

A test failing after a vendor change is the *desired* behaviour: it tells you to re-read the docs.

CI (`.github/workflows/ci.yml`) runs lint, the tests on Python 3.10 and 3.12, and a mock smoke run.

---

## 18. Writing an honest article from the data

The repository is the research. The article is a view of it. Suggested structure for a
"Best X API" piece:

1. **The question and who it is for.** One paragraph. Which use case (SEO tools, AI agents, price
   monitoring) is the benchmark meant to serve?
2. **What we measured and what we did not.** Link `docs/METHODOLOGY.md`.
3. **The setup.** Vantage point, dates, queries file, repeats, plans and prices (with source and
   date), commit hash.
4. **Results.** Headline table first, then outcomes, then by category. Embed `latency.png`.
5. **The uncomfortable parts.** Every result that flatters nobody: failures, slow tails, a cheaper
   competitor, a vendor that wins a category. Put them where a skimming reader will see them.
6. **What surprised us** (relative to what you wrote down *before* measuring).
7. **Limitations.** Copy from `docs/LIMITATIONS.md` and add the run-specific ones.
8. **How to reproduce.** The two-sentence version from [section 12](#12-reproduce-a-single-number-from-scratch)
   plus the exact commands.
9. **Changelog.** Date of each re-measurement and what changed.

Using AI to draft prose is fine **after** the numbers exist; every sentence containing a number
or a claim about a vendor must be checked against `report.md` or the raw data by a human. Run the
checklist in `docs/PUBLISHING_CHECKLIST.md`.

---

## 19. Ethics, terms of service and conflicts of interest

* **Use your own keys and respect each vendor's terms and rate limits.** The default sequential
  traffic is polite; do not raise concurrency without a reason.
* **Do not publish vendor responses wholesale.** Raw bodies contain third-party web content
  (titles, snippets). Keep them for verification; publish aggregates, and quote sparingly.
* **Disclose conflicts.** If you are paid by, or compete with, one of the vendors being
  measured, say so at the top of the article. A benchmark published by a vendor about its own
  product can still be honest, but only if the method is open and unflattering results appear
  with the same prominence as flattering ones.
* **Give vendors a chance to respond** to surprising negative results (a misconfigured account
  or a recent incident may explain them) without letting them veto publication.
* **Do not scrape search engines directly with this tool.** It talks to commercial APIs only.

---

## 20. FAQ

**Why not just use a load-testing tool such as k6 or wrk?**
Those tools are excellent for throughput and concurrency. This project asks a different
question: how do vendors compare on the *same sequential workload*, including the content of the
answers (completeness, overlap), with the raw responses preserved for audit.

**Why is the default concurrency 1?**
Because it isolates the vendor's latency from our own queueing. Concurrency experiments are a
separate study; the flag exists so you can run one and report it as such.

**Why only successful requests in the latency statistics?**
A failed request's duration is often a timeout, i.e. a configured number, not a measurement. Both
facts are reported, side by side.

**Why does `empty` count as a failure?**
For a pipeline that needs results, an empty page is a failed call. It is reported separately so
you can argue otherwise with data.

**Does it handle retries?**
No, on purpose. Retries change what is being measured. If you want to study client-side retry
policies, add them as an explicit experiment.

**Can I run it in the cloud for a neutral vantage point?**
Yes. Use the Docker image or the scheduled GitHub Actions workflow and label the vantage point
accordingly.

**How many repeats are enough?**
Enough that your confidence intervals are narrower than the differences you want to claim. Start
with 3, look at the intervals, add repeats and extra days where they are too wide.

**Are the mock-server numbers useful for anything?**
Only for testing the rig. They are arbitrary and tagged `-synthetic`.

**What if two providers return different numbers of results by default?**
Report it (the headline table includes the average result count). If you want strict parity, set
the vendor's result-count parameter through `extra_params` after checking its documentation, and
state that in the article.

**How do I benchmark an agent or no-code integration (n8n, MCP, etc.)?**
That is on the roadmap, not in the code. The intended approach is the same: define a
workload, measure end-to-end time and success, store raw outputs, publish the rig.

---

## 21. Roadmap

Honest labels: **done** means it is in this repository and tested; **planned** means it is not.

| Item | Status |
| --- | --- |
| Latency, success, outcome classes, completeness, overlap, cost per 1k | done |
| Seeded schedule, raw storage, reproducible reports from stored data | done |
| Trend aggregation over runs; scheduled workflow | done |
| Mock server and end-to-end tests | done |
| Cache probe (`rep == 0` vs later repeats) as a report section | planned |
| Rank-correlation overlap (order-aware), per-query disagreement browser | planned |
| Paired permutation test on per-query latency differences | planned |
| Concurrency/throughput experiment mode | planned |
| Adapters for other engines (Bing, YouTube, Shopping, Jobs) | planned |
| End-to-end benchmark of workflow tools (n8n nodes, MCP servers) calling a SERP API | planned |
| Documentation friction log (rough edges found while integrating each vendor) | planned |

---

## 22. Glossary

| Term | Meaning |
| --- | --- |
| **SERP** | Search engine results page |
| **SERP API** | A service that returns search results as structured data |
| **Organic results** | Non-advertising results |
| **p50 / p95 / p99** | 50th/95th/99th percentile: the value below which 50/95/99% of observations fall |
| **Bootstrap** | Estimating uncertainty by resampling the observed data with replacement |
| **Wilson interval** | A confidence interval for a proportion that behaves well at small n and extreme p |
| **Jaccard index** | Size of the intersection divided by size of the union of two sets |
| **Vantage point** | The place and network from which measurements are taken |
| **Warm-up** | Requests issued and discarded to establish connections before measuring |
| **Synthetic run** | A run against the local mock server; validates the rig only |
| **Raw data** | The unmodified response bodies stored under `raw/` |

---

## 23. License

MIT. See [LICENSE](LICENSE). Vendor names are trademarks of their owners; this project is not
affiliated with or endorsed by any of them.
