# convergent_networks — machine CAT collection

LLM data collection for the **Convergent Association Task (CAT)**: the machine arm of the
convergent-creativity project. This repo collects responses only. It does **not** score them.

Companion repo: [`dtzx00/creativity_networks`](https://github.com/dtzx00/creativity_networks)
(the machine DAT / divergent arm). The collector here is adapted from that repo's
`machine_data/data_collection.py`, so both arms are collected under identical conditions —
same provider adapters, same temperature policy, same reasoning capture, same provenance
columns, same resumable parallel lanes.

## Design decisions

**Items are drawn fresh for every assessment.** Each assessment calls the live Rugu endpoint
`GET https://api-v2.rugu.io/api/cat/?language=en`, which returns a random sample of 10 cue
pairs from the item pool. Six consecutive calls returned 60 distinct pairs with no repeats, so
the pool is large. This mirrors the human procedure, where cue pairs were randomised per
participant. The drawn pairs are written into every row (`cue_i_left`, `cue_i_right`,
`items_json`), so each row is self-describing and no separate item key is needed.

**No scoring in this repo.** `cat_score` is written blank. Scoring is a separate later pass,
because the scoring method is still being settled. The platform's own scorer is deliberately
not used: it blends a uniqueness term that carries no independent validity, and it redraws an
unseeded 100-word random baseline on every request, so the same answers do not produce the
same score twice.

**Prompt.** `PROMPT_TEMPLATE` in the collector is currently a faithful paraphrase of the task
instructions, not the instrument. Before the production run it must be replaced with the
verbatim participant-facing wording from the study materials, the way the DAT collector uses
the verbatim OSF baseline prompt. The template hash and the per-assessment prompt hash are both
recorded on every row so any change is detectable after the fact.

**Reasoning and thinking effort.** Every row stores whatever reasoning trace the API returns
(`reasoning_text`), and no model is ever sent a reasoning-effort or thinking-budget override —
every model runs at its shipped default. Reasoning tokens are billed either way, so capturing
the trace is free.

## Usage

```bash
# one assessment, printed, nothing written
python machine_data/data_collection.py \
  --model "GPT-4.1-mini" --api-model gpt-4.1-mini --provider openai --n 1 --dry-run

# full run: one lane per provider, resumable, per-row flush
python machine_data/data_collection.py --parallel --models machine_data/models.csv --n 500
```

Provider keys are read from the environment at runtime (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`XAI_API_KEY`, `DEEPSEEK_API_KEY`, `QWEN_API_KEY`, `HUNYUAN_API_KEY`, `MOONSHOT_API_KEY`) and are
never written to disk. Output goes to `machine_data/raw/topup_<provider>.csv`, one row per
assessment, flushed per row so an interrupted run loses nothing and resumes where it stopped.

`machine_data/models.csv` is copied from `creativity_networks` so the model line-up matches the
DAT run exactly — that is what makes a per-model convergent-vs-divergent comparison possible.

## Row layout

One row = one assessment = one API call = 10 items.

| group | columns |
|---|---|
| identity | `model_name`, `api_model_requested`, `api_model_returned`, `provider`, `endpoint_base`, `batch`, `region`, `reasoning`, `model_year` |
| condition | `language`, `temperature_requested`, `temperature_effective`, `temp_range_used`, `seed` |
| items | `items_source`, `items_fetch_timestamp_utc`, `items_json`, `cue_0_left` … `cue_9_right` |
| response | `raw_response_text`, `reasoning_text`, `word_0` … `word_9`, `parse_status`, `n_words_parsed` |
| provenance | timestamps, `latency_ms`, `api_request_id`, `response_id`, `system_fingerprint`, `finish_reason`, token counts, `prompt_template_sha256`, `prompt_sha256`, `collector_version` |
| scoring | `cat_score` (left blank on purpose) |
