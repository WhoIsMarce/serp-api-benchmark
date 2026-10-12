# Limitations (read before quoting)

1. **Vantage point.** Latency from a Buenos Aires laptop and from a US datacentre differ by
   far more than most vendors differ from each other. Always state where you measured.
   Never mix vantage points in one comparison.
2. **Caching.** Several providers may cache identical queries. Repeats inside a run can
   therefore be faster than first requests. The report does not separate them by default;
   inspect `rep == 0` vs `rep > 0` before publishing latency claims.
3. **Query set size.** 40 queries x a few repeats is enough to see gross differences, not
   fine ones. Confidence intervals are in the report; respect them.
4. **Query set bias.** English, US locale, general web search. Results for local, mobile, other
   languages or other engines (Bing, YouTube, Amazon, Jobs, Shopping...) may differ. The
   adapters only cover Google web search for now.
5. **Time-sensitive queries** return different results from minute to minute: low overlap on
   those is expected.
6. **Adapters can drift.** Parameter names and response keys come from public docs and may
   have changed since this code was written. Parser tests use hand-written fixtures; refresh
   them from real `raw/` files.
7. **Feature parity.** Providers differ in what they return (knowledge graph, related
   questions, ads, AI overviews...). We compare organic results only.
8. **Billing semantics.** Whether failed requests are billed, and what a "credit" is, varies.
   Cost output is only as correct as the pricing you enter.
9. **Possible special-casing.** A vendor could in principle serve benchmark-looking traffic
   differently. We use a plain User-Agent (`serpbench/<version>`); change it if you want to test that.
10. **Success != correct.** A 200 with ten plausible-looking results can still be wrong.
    Overlap and manual spot checks are the only guards.
11. **Concurrency.** Everything above is for sequential traffic. Behaviour under load is a
    different experiment (roadmap).
