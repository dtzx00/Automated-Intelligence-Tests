# convergent_networks

Machine CAT (Convergent Association Task) collection. Companion to
[dtzx00/creativity_networks](https://github.com/dtzx00/creativity_networks), which holds the
machine DAT arm. Same models, same provider adapters, same temperature and reasoning policy, so
convergent and divergent scores are comparable within model.

## Design

**One API call per word pair.** An assessment is: one fetch of 10 cue pairs from the Rugu CAT
endpoint, then 10 independent model calls, one per pair, each in a fresh context. No pair can
prime another. This matches the human form, where pairs are presented one at a time.

The one divergence from the human procedure: a participant accumulates memory across items and
can revise earlier answers with the Previous button. Independent calls cannot.

**Items are drawn fresh per assessment** from `GET /api/cat/?language=en`, which returns a
random sample of the pool — mirroring per-participant randomisation. Every row stores its own
pairs, so no row depends on knowing which draw it came from.

**Instructions are the instrument, verbatim** from the CAT frontend
(`Module-Federation apps/cat/src/translations/en.json`). Two mechanical edits, both forced by
single-item delivery: "each of the 10 word pairs" -> "the following word pair", and the output
line asks for one word instead of ten. English only.

**No scoring here.** `cat_score` stays blank; scoring is a later pass with the audited
proximity-only scorer. The platform scorer is not used: it blends an uninformative uniqueness
term and redraws an unseeded random baseline per request, so it is not reproducible.

## Output

ONE file per provider lane: `machine_data/raw/topup_<lane>.csv`, one row per assessment,
**65 columns** = 15 assessment/model/API + 5 per item x 10 items.

Assessment level: `record_id`, `model_name`, `api_model_requested`, `api_model_returned`,
`provider`, `vendor`, `endpoint_base`, `language`, `temperature`, `max_tokens`,
`assessment_start_utc`, `assessment_duration_ms`, `raw_responses`, `reasoning`, `cat_score`.

Per item i in 0..9: `cue_i_left`, `cue_i_right`, `word_i`, `item_i_request_utc`,
`item_i_response_utc`. Per-item latency is the difference of the two timestamps.

`raw_responses` and `reasoning` each hold ten values as a JSON list, in item order. They are the
only packed columns: a column per item for either would add twenty columns of long text, and
reasoning traces run to tens of thousands of characters (DeepSeek-V4-Flash returned 24,805 for a
single pair). `reasoning` is a list of empty strings for non-reasoning models. Read with
`json.loads(row["reasoning"])[i]`.

Model metadata (region, intelligence class, release date) is NOT duplicated into rows;
`machine_data/models.csv` is the single registry and joins on `model_name`.

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
python machine_data/data_collection.py --parallel --models machine_data/models.csv --n 500
```

`--n` counts assessments; each is 10 calls. Runs are resumable per model: existing rows in the
lane file are counted and only the shortfall is collected. Rows are flushed per assessment, so an
interrupted run loses nothing.

## Provider lanes

`models.csv` `provider` is the vendor, which is not always the API serving the model: Tencent and
MiniMax models were served through the Tencent MaaS gateway (`hunyuan` lane) in the DAT run.
`LANE_BY_VENDOR` maps vendor to lane; a `lane` column in `models.csv` overrides per model. Models
with no resolvable lane are printed as UNROUTED and not silently skipped — currently
`Llama-2-70b`, `Llama4-Maverick`, `Llama4-Scout` (meta) and `Ernie-4.0-8k` (baidu).

Keys are read from env at runtime, never hard-coded, never written to disk.
