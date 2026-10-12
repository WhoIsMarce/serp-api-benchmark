# Publishing checklist

Nothing leaves this repository as an article until every box is ticked. The goal
is a piece that an engineer can re-run in an afternoon and still trust.

## Before measuring

- [ ] Re-read each vendor's **current** API docs: endpoint, auth, parameters, response keys. Note the date.
- [ ] Run `pytest`. If a parser test fails, the adapter (or the fixture) is stale: fix it first.
- [ ] Put the vendor's current price into `config/providers.yaml` with `source_url` and `checked_on`.
- [ ] Decide the vantage point and write it down (`--vantage-point`).
- [ ] Decide what you will **not** compare (e.g. engines the other vendor does not offer).
- [ ] Write down, *before* looking at data, which result would surprise you.

## While measuring

- [ ] Same query file, same `country`/`language`, same timeout for every vendor.
- [ ] At least 3 repeats on at least 2 different days.
- [ ] Keep the entire `results/<run_id>/` directory, including `raw/`.
- [ ] Do not delete failed requests. Do not re-run "to get a cleaner result".

## Before writing

- [ ] Open a dozen raw responses by hand. Do the numbers match what you see?
- [ ] Look at the outcomes table: a latency number without its failure rate is a half-truth.
- [ ] Look at the confidence intervals. If two vendors' intervals overlap, you may not say one is faster.
- [ ] Check for caching effects (second identical query much faster than the first?).

## In the article

- [ ] The method is published next to the result (queries file, seed, commit hash, command).
- [ ] The vantage point, dates, and sample sizes are stated.
- [ ] Every number can be traced to a file in `results/`.
- [ ] Unflattering results are reported as prominently as flattering ones.
- [ ] A conflict-of-interest note is present if the author is paid by one of the vendors.
- [ ] Limitations are listed (copy from `docs/LIMITATIONS.md` and add the ones specific to this run).
- [ ] A "last re-measured" date appears at the top, and a plan to re-measure exists.
- [ ] AI-assisted text was read end to end by a human; every claim was checked against data.
