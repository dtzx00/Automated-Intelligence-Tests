> REFERENCE ONLY — the collector does NOT call these endpoints. Items are drawn locally from the
> committed pair list (see README, "Design"), and scoring is a separate pass that does not use the
> platform scorer. This file documents the live Rugu API and the scorer defects found in it, which
> matter for interpreting any CAT score the platform already stored for human participants.

# Rugu CAT endpoints

## What this repo uses

`GET https://api-v2.rugu.io/api/cat/?language=en` → `{"code":200,"data":[["coffee","shark"], …]}`

Returns a random sample of 10 cue pairs from the item pool. No authentication required.
Languages: `en`, `zh-Hans`, `zh-Hant`. The full pool file (`words_<lang>.txt`) lives in the
API's dataset directory and is not public; ask the platform team for a copy if the pool itself
is needed for analysis.

The endpoint 502s intermittently (2 of 6 calls in testing), so `fetch_items()` retries with
backoff.

## What this repo deliberately does not use

`POST /api/cat/sync_evaluate` — the platform scorer. Reasons:

1. Not reproducible. It estimates the z-score baseline by drawing 100 random words per item on
   every request with no seed. Four identical submissions returned 4.34, 4.50, 4.74 and 5.08.
2. Not the audited measure. It scores `0.5 * z_proximity + 0.5 * z_uniqueness`, where the
   uniqueness term carries no independent validity, and aggregates with a plain mean rather
   than a trimmed mean.
3. Operationally fragile. ~5s for 10 items, intermittent 502s, and a response word outside the
   embedding vocabulary returns HTTP 500 rather than a missing item.

Two API generations exist and they run the same scorer: the old `api.rugu.io` (snapshot in
`dtzx00/rugu-api-old`) and the current `api-v2.rugu.io` (`dtzx00/rugu-api`).
