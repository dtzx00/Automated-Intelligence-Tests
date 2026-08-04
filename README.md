# convergent_networks

Machine CAT (Convergent Association Task) collection. Companion to
[dtzx00/creativity_networks](https://github.com/dtzx00/creativity_networks), which holds the
machine DAT arm. Same models, same provider adapters, same temperature and reasoning policy, so
convergent and divergent scores are comparable within model.

## The one registry

`machine_data/models.csv` is the **only** model registry. There is no v1/v2 split: the file that
was briefly called `models_v2.csv` IS this file now, and the older DAT-era registry was deleted
(recoverable from git history). Every consumer — the collector's `--models` default, the README,
`MODEL_LINEUP.md` — points here.

Columns that the collector actually reads:

| column | meaning |
|---|---|
| `model` | our label, written to `model_name`. Not sent to any API. |
| `api_model_id` | the exact string sent as `model`. Falls back to `model` if blank. |
| `provider` | the VENDOR that made the model. |
| `lane` | overrides the vendor→lane map when the serving API is not the vendor's own. |
| `status` | only `live` rows are collected. `dead` and `dropped` rows stay for provenance. |

`status` and `lane` exist only in this file. Running an older registry would silently lose every
lane override — `DeepSeek-R1`, `DeepSeek-Chat`, `DeepSeek-V3.2`, `DeepSeek-V4-Flash-TH`, `GLM-*`,
`MiniMax-M2.1` and all three Doubao models reach their API only through a `lane` value.

Current state of the lineup, and the evidence behind every inclusion and exclusion, is in
[machine_data/MODEL_LINEUP.md](machine_data/MODEL_LINEUP.md).

## Design

**One API call per word pair.** An assessment is: 10 cue pairs drawn locally from the committed
endpoint, then 10 independent model calls, one per pair, each in a fresh context. No pair can
prime another. This matches the human form, where pairs are presented one at a time.

The one divergence from the human procedure: a participant accumulates memory across items and
can revise earlier answers with the Previous button. Independent calls cannot.

**Items are drawn fresh per assessment, locally.** No network call: `machine_data/items/
cat_word_pairs_en.txt` is the pair list, and `draw_items()` is a verbatim port of the sampling
code in the Django backend that served the human participants (`question/views.py` in
`dtzx00/rugu-api-old`) — pick a pair at random, reject it if either word is already used, remove
it from the candidate list either way, coin-flip the display order.

The pairs are not arbitrary word combinations. They were precomputed by taking 200 common nouns
and keeping every pair whose word vectors sit at **cosine distance 0.85-0.95**, which is the
instrument's difficulty control. Pairs must therefore be sampled from this list, never generated.
The file holds 22,674 lines = 7,558 distinct pairs at exactly 3x each (the generator ran three
times in append mode); multiplicity is uniform, so sampling it as written equals sampling the
distinct set, and it is kept verbatim to match the server.

Two properties a naive `random.sample(pairs, 10)` would break, both verified against the live
endpoint (240 draws): all 20 words in an assessment are **distinct** (live 0/240 draws repeat a
word, `random.sample` repeats in about two thirds), and each pair is accepted uniformly from the
pairs still compatible with those already chosen. Parity evidence: 2,400/2,400 live pairs are in
the committed list, and word-frequency correlation between live and local draws is r=0.588
against a same-size local-vs-local noise floor of r=0.558 — indistinguishable.

**Instructions are the instrument, verbatim** from the CAT frontend
(`Module-Federation apps/cat/src/translations/en.json`). Two mechanical edits, both forced by
single-item delivery: "each of the 10 word pairs" -> "the following word pair", and the output
line asks for one word instead of ten. English only.

**No scoring here.** `cat_score` stays blank; scoring is a later pass with the audited
proximity-only scorer. The platform scorer is not used: it blends an uninformative uniqueness
term and redraws an unseeded random baseline per request, so it is not reproducible.

## Output

ONE file per provider lane: `machine_data/raw/topup_<lane>.csv`, one row per assessment,
**64 columns** = 14 assessment-level + 5 per item x 10 items.

Assessment level: `record_id`, `model_name`, `api_model_requested`, `api_model_returned`,
`provider`, `vendor`, `prompt_version`, `temperature`, `seed_base`, `max_tokens`,
`assessment_start_utc`, `assessment_duration_ms`, `raw_responses`, `reasoning`.

Per item i in 0..9: `cue_i_left`, `cue_i_right`, `word_i`, `item_i_request_utc`,
`item_i_response_utc`. Per-item latency is the difference of the two timestamps.

Notes on specific columns:

- **Three model-id columns, all load-bearing.** `model_name` is our label, `api_model_requested`
  is what we sent, `api_model_returned` is what actually answered. Aliases repoint silently —
  `DeepSeek-R1` no longer resolves at all — so only the returned id records which snapshot
  produced the words.
- **`vendor` vs `provider`.** `provider` is the API lane that served the call; `vendor` is who
  made the model. Identical on 51 of 55 routed models and different on the four that matter:
  `MiniMax-M2.5/M2.7/M3` and `Hunyuan-Hy3` go through Tencent's gateway, `DeepSeek-Chat/R1/V3.1/
  V3.2` and `MiniMax-M2.1` through Alibaba's, and the three Doubao models through Volcano Ark.
- **`prompt_version`** records which instruction wording the row saw. Bump `PROMPT_VERSION` in
  `data_collection.py` whenever `ITEM_PROMPT_TEMPLATE` changes; the rules are the instrument, so a
  wording change is a measure change.
- **`temperature`** is the value actually used, after any provider-forced fallback. A row reading
  `provider default` means the model rejected its lane's midpoint and the parameter was omitted.
- **`seed_base`** records the seed actually sent. Item i receives `seed_base*100 + i`, so this one
  value reproduces all ten. Only openai, deepseek and qwen accept a seed; the column is blank for
  the other lanes, so it states what was sent rather than what we intended to send.
- **`raw_responses` and `reasoning`** each hold ten values as a JSON list, in item order — the
  only packed columns. A column per item for either would add twenty columns of long text, and
  traces are large (DeepSeek-V4-Flash returned 24,805 characters for one pair). `reasoning` is a
  list of empty strings for non-reasoning models. Read with `json.loads(row["reasoning"])[i]`.

Deliberately absent: `endpoint_base` (1:1 with `provider`, mapped in code — see the lane table
below), `language` (English only, locked 2026-08-01 — there is no Chinese arm, so a column reading
`en` on every row says nothing), `cat_score` and per-item scores (raw files stay immutable;
scoring writes its own file keyed on `record_id`), per-call response ids and token counts.
Model metadata (region, intelligence class, release date) is NOT duplicated into rows;
`machine_data/models.csv` is the single registry and joins on `model_name`.
Model metadata is deliberately NOT copied into the rows: a row records what was sent and what came
back, and anything about the model is looked up from the registry.

## Parsing fails closed

A call yields a word only if a line of the response reduces to one valid single word after
stripping markdown, list markers and an `answer:`-style label. Otherwise `word_i` is blank. A
failed item never discards the other nine — the assessment is always kept. `raw_responses[i]`
holds the verbatim output, unmodified, or `[ERROR: ...]` if the call itself failed, so a blank
word can always be diagnosed from the row alone.

## Run

```bash
# one assessment, printed, nothing written
python machine_data/data_collection.py --model "GPT-4.1-mini" --api-model gpt-4.1-mini \
  --provider openai --n 1 --dry-run

# full run: n assessments per model, all lanes in parallel, resumable
# n defaults to 100 — locked 2026-08-03; see machine_data/MODEL_LINEUP.md
python machine_data/data_collection.py --parallel --assessment-concurrency 10 --item-concurrency 5
```

`--n` counts assessments; each is 10 calls. Runs are resumable per model: existing rows in the
lane file are counted and only the shortfall is collected, so re-running a finished job collects
nothing. Rows flush per assessment, so an interruption loses at most the assessments in flight.

Three levels of concurrency:

| flag | default | what it does |
|---|---|---|
| (per lane) | — | every provider lane runs as its own thread |
| `--concurrency` | 3 | models in flight within a lane |
| `--assessment-concurrency` | 1 | assessments in flight within one model |
| `--item-concurrency` | 1 | calls in flight within one assessment |
| `--min-gap` | 0.5 | seconds between call launches in a lane |

`--item-concurrency` is timing only, never data: the 10 items are independent by construction,
each a fresh single-message context, so the words a model returns do not depend on whether the
calls overlap. Measured on GPT-4.1-mini: 8,740 ms sequential vs 1,616 ms at 5. Default is 1 so a
model's request rate stays low and its per-item timestamps do not overlap; raise it for slow
reasoning models, where 10 sequential calls at 25 s each is over four minutes per assessment.

`--assessment-timeout` (default 1200 s) writes an assessment with whatever came back once the
deadline passes; unfinished items are recorded as errors. Without it a hung provider holds the run:
a 300 s socket timeout times 6 retries is 30 minutes for a single item, and `Kimi-K2.6` and
`MiniMax-M2.7` each sat over 25 minutes on one assessment during the 2026-08-03 shakedown.

`--progress-every` (default 60 s) prints a heartbeat, since a run measured in hours otherwise gives
no way to see where a model is up to short of grepping the CSV:

```
PROGRESS 1/2 models done | 5 assessments this run (50 calls) | 18.7/min | remaining 1 | ETA 0.0h
         | furthest behind: GPT-4.1-mini 2/3, Claude-Haiku-4.5 3/3
```

## Failure handling

Three tiers, so one bad model cannot take down a run:

1. **A call** retries up to 6 times on transient failures (429, 5xx, timeouts, connection resets)
   with linear backoff. A 400 mentioning temperature retries once at 1.0, since some models accept
   only their default.
2. **An item that still fails** leaves `word_i` blank and `[ERROR: ...]` in `raw_responses[i]`. The
   other nine items are valid data, so the assessment is kept.
3. **A model whose assessments return zero usable words three times running** is abandoned and
   listed under SKIPPED at the end of the run.

## Temperature

Each lane runs at its provider's midpoint: 1.0 where the accepted range is 0-2 (openai, xai,
deepseek, qwen, hunyuan), 0.5 where it is 0-1 (anthropic, moonshot, doubao). A model that rejects
its lane's midpoint is retried **with the temperature parameter omitted entirely**, so it applies
its own default, and the row records `provider default` rather than a number we did not send.

The earlier fallback re-sent a literal 1.0, which was a no-op for the five (0,2) lanes whose
midpoint is already 1.0 — it could not fix the case it existed for.

## Checking the repo agrees with itself

```bash
python machine_data/tests/check_consistency.py
```

Fifteen assertions tying the code, this README, `MODEL_LINEUP.md` and `models.csv` together: column
counts, the single-registry rule, no dead flags, every live model routable and uniquely identified.
Run it after touching any of them. It exists because a cold reader found the repo asserting three
different things at once.

## Known limitations

- **Chat-completions only.** `_openai_like` posts to `/chat/completions` and does not stream.
  Models served exclusively through OpenAI's Responses API — the `*-pro` reasoning tier — cannot be
  collected without a new adapter. None are in the live lineup.
- **Anthropic reasoning traces are not captured.** The adapter never sends a `thinking` block, so
  Claude's extended thinking is off and the `reasoning` column is empty for every Claude, while
  OpenAI/DeepSeek/Qwen/xAI traces come back through `reasoning_content`. This is deliberate:
  the locked policy is to use each model's shipped default and capture only what the API returns,
  and enabling extended thinking would change the experimental condition. It is an asymmetry in
  what we can *observe*, not in what we asked the models to do, and it belongs in the paper's
  limitations.
- **Item sampling is not seeded.** Reproducibility comes from storing the drawn pairs in every row,
  not from a seed, so a row is self-describing but a run is not byte-repeatable.

## Provider lanes

`models.csv` `provider` is the vendor, which is not always the API serving the model: Tencent and
MiniMax models were served through the Tencent MaaS gateway (`hunyuan` lane) in the DAT run.
`LANE_BY_VENDOR` maps vendor to lane; a `lane` column in `models.csv` overrides per model. Models
with no resolvable lane are printed as UNROUTED and not silently skipped — currently
`Llama-2-70b`, `Llama4-Maverick`, `Llama4-Scout` (meta) and `Ernie-4.0-8k` (baidu).

Keys are read from env at runtime, never hard-coded, never written to disk.
