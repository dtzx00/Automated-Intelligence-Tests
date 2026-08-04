# CAT model lineup — state as of 2026-08-03

Registry: `models.csv` (the single source of truth; the former `models_v2.csv` was promoted to
this name on 2026-08-03 and the DAT-era registry deleted). Every claim below is from a real call, not a provider catalogue.
A model id appearing in a provider's `/models` list does NOT mean the account can call it — six
models in this lineup were "live" by catalogue and returned 404/403/429 on first contact.

## Where the lineup stands

`models.csv` is the complete record of every model considered, not just the collected ones.

| status | meaning | count |
|---|---|---|
| `live` | collected | **71** |
| `blocked` | reachable model, our account cannot call it yet | 4 |
| `dead` | no API on any key we hold | 13 |
| `dropped` | reachable, excluded on purpose | 4 |
| | rows in the file | 92 |

Live by lane: `openai` 27, `qwen` 11, `anthropic` 11, `openai_responses` 6, `moonshot` 5, `xai` 4, `hunyuan` 3, `deepseek` 2, `doubao` 2.
Live by region: Western 48, Eastern 23.
Live by release year: 2023 4, 2024 9, 2025 26, 2026 32.

Only `live` rows are collected, so a `blocked` model is skipped rather than attempted and failed.

## Shakedown, 2026-08-03 — 72 models, 1 assessment each, 700 calls

`shakedown_items_ok` and `shakedown_ms` in `models.csv` hold the per-model result.

- **58 clean** (10/10 items parsed).
- **4 partial by model behaviour, not defect** — `o1` refused one item ("I can't comply"),
  `Moonshot-v1-8k`/`-128k` answered in prose ("There is no single word in English that..."),
  `Grok-4.20-reason` answered then justified (a parser bug, since fixed).
- **6 blocked or dead**: `Qwen-72B-Chat`, `Qwen1.5-72B-Chat`, `Qwen2-72B-Instruct` (404,
  permanently unavailable), `Qwen-Turbo-2024-11` (403 access denied), `Qwen-Max-1201` (429 model
  quota), `DeepSeek-V3.2` (400 — wrong service id for the Tencent gateway, our bug).
- **2 hung** past 25 minutes: `Kimi-K2.6`, `MiniMax-M2.7`. `Kimi-K2.6` did the same thing in the
  DAT round (commit e419c23 there). This is what `--assessment-timeout` exists for.
- **6 pro-tier models never tested** (`o1-pro`, `o3-pro`, `GPT-5-pro`, `GPT-5.2-pro`,
  `GPT-5.4-pro`, `GPT-5.5-pro`) — held back on cost, and duplicates of standard tiers we have.

## GLM dropped — reconsidered and confirmed

The DAT round dropped the GLM family for speed (`machine_data/legacy/pre_lock_nonfinal/README.md`
in `dtzx00/creativity_networks`: "too slow, >1 min/call"; commits 3b7e615, 46adcfa, 1156bd7).
That decision is *more* binding here: CAT sends ten calls per assessment.

| DAT preview, one call | median | max | x10 = per CAT assessment |
|---|---|---|---|
| GLM-5 | 48.1 s | 89.2 s | 8.0 min |
| GLM-4.7 | 33.3 s | 74.3 s | 5.5 min |
| GLM-5.1 | 29.6 s | 104.6 s | 4.9 min |
| GLM-5.2 | 27.7 s | 55.1 s | 4.6 min |

Confirmed again on 2026-08-03: GLM-5.2 timed out at 300 s on the Tencent gateway and was still
running past 15 minutes on Volcano. GLM also has no DAT counterpart, so it could only ever feed
the archive — at the highest time cost of anything on the list.

## Volcano Engine (Ark) — new lane, `DOUBAO_API_KEY`

Raw probe results: `probes/volcano_probe_2026-08-03.json`.

Activation is per model in 开通管理 and is what gates access; `ModelNotOpen` cleared the moment
Dawei subscribed. Six models answer:

| model | one call | ~per assessment |
|---|---|---|
| doubao-seed-2-0-mini-260428 | 10 s | ~25 s |
| doubao-seed-2-0-pro-260215 | 13 s | ~35 s |
| doubao-seed-2-0-lite-260428 | 26 s | ~65 s |
| doubao-seed-2-1-turbo-260628 | 160 s | ~5 min |
| doubao-seed-2-1-pro-260628 | 391 s | ~13 min |
| doubao-seed-evolving | 514 s | ~17 min |

Planned: take the first two plus `seed-2-1-turbo` (one per intelligence class). All six are 2026
releases, so ByteDance fixes vendor concentration but adds no era depth.

**Everything from 2024-2025 on Ark is permanently unavailable — CLOSED 2026-08-03.** Dawei checked
开通管理 on desktop and subscribed everything assignable; the list is identical to mobile and
contains 2026 models only. Re-probed after that: `kimi-k2-250711`, `deepseek-v3-241226`,
`deepseek-r1-250120`, `doubao-1-5-pro-32k-250115`, `doubao-pro-32k-240615`, `qwen2-5-72b-20240919`,
`mistral-7b-instruct-v0.2`, `doubao-seed-1-6-250615`, `doubao-seed-1-8-251228` all still return
`InvalidEndpointOrModel.NotFound`. They appear in Ark's `/models` catalogue but are closed to new
subscriptions. **Do not chase these again.**

Taken from Ark: `Doubao-Seed-2.0-mini`, `Doubao-Seed-2.0-pro`, `Doubao-Seed-2.1-turbo` — one per
intelligence class. Skipped `seed-2-0-lite` (redundant with mini), `seed-2-1-pro` and
`seed-evolving` (13-17 min per assessment for a 4th and 5th 2026 Chinese model), and `glm-5-2`.

## DashScope rescued what Volcano could not (2026-08-03)

Probing alternate routes after the Ark dead end:

| model | route | note |
|---|---|---|
| `DeepSeek-Chat` | `deepseek-v3` on DashScope | was written off as dead; **has DAT data**, so this restores a pairing |
| `DeepSeek-V3.2` | `deepseek-v3.2` on DashScope | Tencent gateway rejects DeepSeek's own service ids |
| `DeepSeek-R1` | `deepseek-r1` on DashScope | recovered earlier, same story |
| `DeepSeek-V3.1` | `deepseek-v3.1` on DashScope | new, fills the gap between V3 and V3.2 |

Lesson: when a vendor retires a model from its own API, check the Chinese cloud gateways
individually. Tencent, Alibaba and Volcano host overlapping but different subsets, under different
ids, and being absent from one says nothing about the others.

## Do not re-add these

Each of these was checked with a real call. Reasons are in the registry's `notes` column.

**blocked (4)** — the model works, our account cannot call it yet
- `MiniMax-M2.7` — HTTP 402 on the Tencent TokenHub gateway: free-trial quota exhausted, postpaid billing not enabled. NOT a slow model — it answered in 49s on 2026-08-03. Has DAT 77.8586. Clears when billing is enabled.
- `MiniMax-M3` — HTTP 402 on the Tencent TokenHub gateway: free-trial quota exhausted, postpaid billing not enabled. Has DAT 78.4807. Clears when billing is enabled.
- `Qwen-Max-1201` — HTTP 429 model quota on this DashScope account; needs a quota raise from Dawei. Not attempted until then.
- `Qwen-Turbo-2024-11` — HTTP 403 access denied on this DashScope account; needs an access request from Dawei. Not attempted until then.

**dead (13)**
- `Qwen-72B-Chat` — add-old — 
- `Qwen1.5-72B-Chat` — add-old — 
- `Qwen2-72B-Instruct` — add-old — 72b not served; 57b is
- `Claude-3-Opus` — retired by Anthropic; claude-3-opus-20240229 not served, and Anthropic now lists only 11 models
- `Claude-3-Haiku` — retired by Anthropic
- `Claude-3.5-Sonnet` — retired by Anthropic
- `Claude-Sonnet-4` — retired by Anthropic; claude-sonnet-4-20250514 not served
- `Kimi-K2` — retired by Moonshot (k2.5+ only); kimi-k2-250711 on Volcano Ark is listed but closed to subscription
- `Grok-Code-Fast` — retired by xAI
- `Llama-2-70b` — no host on any key we hold; would need OpenRouter
- `Llama4-Maverick` — no host on any key we hold; would need OpenRouter
- `Llama4-Scout` — no host on any key we hold; would need OpenRouter
- `Ernie-4.0-8k` — no host on any key we hold

**dropped (4)**
- `Kimi-K3` — FAILS THE 5-MINUTE RULE. Measured 2026-08-04 off Beijing peak: 5 of 10 words hit the 300s cap, mean 161s for the ones that landed. NOTE this one costs a paired observation — it has DAT 77.5552. Re-add only if the provider gets faster.
- `GLM-5` — dropped: GLM family excluded from DAT for speed (>1min/call); 10 calls per CAT assessment makes it 5-8 min/assessment, and it has no DAT counterpart
- `GLM-5.2` — dropped: GLM family excluded from DAT for speed (>1min/call); 10 calls per CAT assessment makes it 5-8 min/assessment, and it has no DAT counterpart
- `Doubao-Seed-2.1-turbo` — FAILS THE 5-MINUTE RULE. Measured 2026-08-04 off Beijing peak: 7 of 10 words hit the 300s cap, mean 226s for a word that did land, 664s and 40,192 reasoning tokens on a single probe. No DAT counterpart, so dropping costs no paired observation.

Also listed in Volcano Ark's catalogue but closed to subscription, so unreachable however the
lineup changes: `kimi-k2-250711`, `deepseek-v3-241226`, `deepseek-r1-250120`,
`doubao-1-5-pro-32k-250115`, `doubao-pro-32k-240615`, `doubao-seed-1-6-*`, `doubao-seed-1-8-*`,
`qwen2-5-72b-20240919`, `mistral-7b-instruct-v0.2`, `glm-4-5-air`, `glm-4-7`.

## Open items

1. Dawei: check Volcano 开通管理 on desktop for 2024-2025 models (would recover Kimi-K2,
   DeepSeek-Chat and the original DeepSeek-R1, all currently written off).
2. Dawei: Alibaba Model Studio — access for `qwen-turbo-2024-11-01`, quota for `qwen-max-1201`.
3. Me: re-route `DeepSeek-V3.2` to DashScope; add the three Doubao models; verify release dates
   for all additions (provider `created` timestamps are not release dates).
4. ~~Decide n.~~ **LOCKED at n=100 by Dawei, 2026-08-03.** See below.
5. Decide the 6 pro-tier models (`o1-pro`, `o3-pro`, `GPT-5-pro`, `GPT-5.2-pro`, `GPT-5.4-pro`,
   `GPT-5.5-pro`) — never probed, held back on cost, and duplicates of standard tiers we already
   have. Default is to drop them.

## n = 100 assessments per model (LOCKED 2026-08-03)

`--n` now defaults to 100, so the decision cannot be lost to a forgotten flag.

100 assessments x 10 items = **1,000 responses per model**, already twice the DAT arm's 500 per
model. The unit of analysis is the assessment (one participant-equivalent, a 10%-trimmed mean over
its 10 items), so n=100 puts the standard error of a model mean near 0.3 points — far inside any
effect we would report. n=500 would buy SE 0.14 for five times the time and money.

Practical effect: the run goes from roughly 14 hours to roughly 3, and the slowest models stop
being prohibitive. `Doubao-Seed-2.1-turbo` at ~5 min per assessment is 8 hours serial at n=100 and
under an hour with assessments running 10-deep.

**DO NOT START COLLECTION** until Dawei says so (his instruction, 2026-08-03). Release dates for
the 30 additions are still unverified, and provider `created` timestamps are not release dates.


## Verification run, 2026-08-03 (n=2 per model, 1,890 calls)

Every live model was given 2 assessments to shake out the production settings.

- **69 of 75 collected cleanly.** Overall 1,266 of 1,890 words parsed; excluding the six pro-tier
  models and the eight slow ones, parse rate is effectively 100%.
- **The six OpenAI `*-pro` models are Responses-API only** — `404 This is not a chat model` /
  `only supported in v1/responses`. They wrote rows with zero words, which is why the run log said
  `+2 (done)`: a written row is not a collected answer, and the 3-strikes rule only fires on three
  CONSECUTIVE empties. FIXED 2026-08-04 — see below; they are live again on their own lane.
- **Eight models time out at a 600s deadline with item-concurrency 5**: Kimi-K3, Kimi-K2.5,
  Kimi-K2.6, Qwen3.5-Plus, MiniMax-M2.7, MiniMax-M3, DeepSeek-V4-Flash, Doubao-Seed-2.1-turbo.
  They need the slow pass: `--item-concurrency 10 --assessment-timeout 1800`.
- **Timing:** median assessment 4s; 224 hours of serial time for n=100 across all models, almost
  all of it in the slow eight. With lanes, models and assessments in parallel the fast 61 finish in
  well under an hour.
- **Two bugs found and fixed by running it** (see the commit): the CSV field-size limit crash and
  the `mixed:None/provider default` temperature label.
- **Do not run two collectors against the same output directory.** Six models have more than 2
  assessments because a detached run and a foreground run overlapped. Resumability counts rows; it
  does not lock the file.


## The six pro models, 2026-08-04: fixed, not dead

Calling `/v1/responses` with the same prompt, all six answer:

| model | api id | latency, 1 item | reasoning tokens | word |
|---|---|---|---|---|
| o1-pro | o1-pro-2025-03-19 | 42s | 320 / 1,600 (two draws) | organ, instrument |
| o3-pro | o3-pro-2025-06-10 | 59s | 960 | harpsichord |
| GPT-5-pro | gpt-5-pro-2025-10-06 | 161s | 1,984 | instrument |
| GPT-5.2-pro | gpt-5.2-pro-2025-12-11 | 6s | 81 | instrument |
| GPT-5.4-pro | gpt-5.4-pro-2026-03-05 | 12s | 516 | instrument |
| GPT-5.5-pro | gpt-5.5-pro-2026-04-23 | 28s | 79 | instrument |

Full assessment through the collector (GPT-5.2-pro, 10 items in parallel): 10/10 words in 62s,
temperature 1.0 accepted, reasoning summaries captured on 9 of 10 items.

They run on lane `openai_responses` — same key and account as `openai`, separate lane so they get
their own file and their own concurrency pool instead of clogging the 33-model chat lane. The
adapter asks for `reasoning.summary="auto"`, which is a CAPTURE knob and not an effort knob, and
retries once without it if an account is not verified for summaries.

**Cost is the reason to think twice, not the endpoint.** At n=100 (1,000 calls per model), using
the measured token counts and list pricing:

| model | $/1M in / out | est. n=100 |
|---|---|---|
| o1-pro | 150 / 600 | $200–1,000 (reasoning length varied 5x across two draws) |
| GPT-5-pro | 15 / 120 | ~$240 |
| GPT-5.4-pro | 30 / 180 | ~$100 |
| o3-pro | 20 / 80 | ~$80 |
| GPT-5.2-pro | 21 / 168 | $15–250 |
| GPT-5.5-pro | 30 / 180 | $20–150 |

Order $700–1,700 for the tier, over half of it o1-pro. The Batch API is half price on every one of
these if 24-hour turnaround is acceptable. Prices from
https://developers.openai.com/api/docs/pricing (2026-08-04).


## The five-minute rule (Dawei, 2026-08-04)

**One word must not cost more than five minutes. A model that cannot answer inside the cap is
dropped, not waited for.**

Enforced in code, not by convention:

- `--call-timeout` (default **300s**) is a budget for the whole word, retries included. A word that
  hits it is left blank and never retried — retrying spends another five minutes to learn what we
  already know.
- The cap is enforced on **wall clock**, not on the socket. A socket timeout is an inactivity
  timer, so a provider that trickles reasoning tokens never trips it: DeepSeek-V4-Flash returned a
  *completed* call at 458s under a 300s socket timeout. The call now runs in its own thread and the
  run stops waiting at the cap.
- A model is **dropped mid-run** when it averages more than 300s per word over its completed calls,
  or when at least half its calls hit the cap. It prints `DROP <model>: TOO SLOW — <reason>`.
- `--assessment-timeout` default drops 1200s -> 600s. With the per-word cap and ten items in
  flight, an assessment cannot legitimately need more.

### Measured against the rule, 2026-08-04, off Beijing peak

| model | words / 10 | hit the cap | mean per word | verdict |
|---|---|---|---|---|
| MiniMax-M2.1 | 10 | 0 | 43s | keep |
| DeepSeek-V4-Flash-TH | 10 | 0 | 44s | keep |
| Kimi-K2.5 | 9 | 1 | 74s | keep |
| DeepSeek-V4-Pro | 10 | 0 | 92s | keep |
| Qwen3.5-Plus | 8 | 2 | 149s | keep, flagged |
| DeepSeek-V4-Flash | 10 | 0 | 155s | keep |
| Kimi-K2.6 | 6 | 4 | 216s | keep, flagged |
| **Kimi-K3** | 5 | **5** | 161s | **dropped** |
| **Doubao-Seed-2.1-turbo** | 3 | **7** | 226s | **dropped** |

Dropping Kimi-K3 costs a paired observation — it has a DAT score (77.5552). Doubao-Seed-2.1-turbo
has no DAT counterpart, so it costs nothing.

DeepSeek-V4-Flash went 0-for-20 on 2026-08-03 and 10-for-10 at 155s a day later. That was
Beijing-peak load, not the model. Measure Eastern providers off peak before judging them.
