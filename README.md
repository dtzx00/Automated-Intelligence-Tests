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

Two files per provider lane in `machine_data/raw/`, joined on `record_id`:

| file | grain | columns |
|---|---|---|
| `topup_<lane>.csv` | one row per assessment | 77 = 27 assessment/model/API + 5 per item x 10 |
| `items_topup_<lane>.csv` | one row per call (10 per assessment) | 32 |

Per item in the wide file: `cue_i_left`, `cue_i_right`, `word_i`, `item_i_request_utc`,
`item_i_response_utc`. The long file carries what would bloat a spreadsheet: verbatim response
text, reasoning trace, per-call tokens, response and request ids, fingerprint, finish reason,
retry count, error, and the per-call prompt hash.

Model metadata (region, intelligence class, release date) is NOT duplicated into rows;
`machine_data/models.csv` is the single registry and joins on `model_name`.

## Parsing fails closed

A call yields a word only if a line of the response reduces to one valid single word after
stripping markdown, list markers and an `answer:`-style label. Otherwise the word is blank and
`parse_status=failed`. A failed item does not discard the other nine: the assessment is kept and
marked `partial`. `raw_response_text` in the long file is never modified, so every failure stays
inspectable.

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
