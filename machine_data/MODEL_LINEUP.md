# CAT model lineup — state as of 2026-08-03

Registry: `models.csv` (the single source of truth; the former `models_v2.csv` was promoted to
this name on 2026-08-03 and the DAT-era registry deleted). Every claim below is from a real call, not a provider catalogue.
A model id appearing in a provider's `/models` list does NOT mean the account can call it — six
models in this lineup were "live" by catalogue and returned 404/403/429 on first contact.

## Where the lineup stands

`models.csv` is the complete record of every model considered, not just the collected ones.

| status | meaning | count |
|---|---|---|
| `live` | collected | **77** |
| `dead` | no API on any key we hold | 13 |
| `dropped` | reachable, excluded on purpose | 2 |
| | rows in the file | 92 |

Live by lane: `openai` 33, `qwen` 13, `anthropic` 11, `moonshot` 6, `hunyuan` 5, `xai` 4, `doubao` 3, `deepseek` 2.
Live by region: Western 48, Eastern 29.
Live by release year: 2023 5, 2024 10, 2025 26, 2026 36.

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

**dropped (2)**
- `GLM-5` — dropped: GLM family excluded from DAT for speed (>1min/call); 10 calls per CAT assessment makes it 5-8 min/assessment, and it has no DAT counterpart
- `GLM-5.2` — dropped: GLM family excluded from DAT for speed (>1min/call); 10 calls per CAT assessment makes it 5-8 min/assessment, and it has no DAT counterpart

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
