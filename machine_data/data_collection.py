"""
data_collection.py — collect machine CAT (Convergent Association Task) responses with full
open-science provenance.

Adapted from dtzx00/creativity_networks machine_data/data_collection.py (the DAT collector).
Provider adapters, temperature policy, reasoning capture, parallel lanes, resumability and
skip-and-flag behaviour are carried over unchanged so machine CAT and machine DAT are
collected under identical conditions.

DELIVERY: ONE API CALL PER WORD PAIR (locked 2026-08-03, Dawei)
  1 assessment = 10 cue pairs drawn locally + 10 independent model calls + 1 CSV row.
  Each call carries the instructions and exactly one pair, in a fresh context, so no pair can
  prime another. This matches the human form, where pairs are presented one at a time.
  Note the one real divergence: a human accumulates memory across the 10 items and may revise
  earlier answers with the Previous button; independent calls cannot.

OUTPUT: ONE file per provider lane, raw/topup_<lane>.csv — one row per assessment, 63 columns:
  13 assessment/model/API columns + 5 per item (cue left, cue right, word, request timestamp,
  response timestamp) x 10 items. Every field has its own column. raw_responses and reasoning
  each hold ten values as a JSON list, since a column per item for either would add twenty
  columns of long text.

ITEMS ARE DRAWN FRESH PER ASSESSMENT, locally, from the committed pair list, using a verbatim
port of the sampling code that served the human participants. No network call for items: the Rugu
endpoint was the run's single point of failure and it added nothing, since the pair list is fixed
and public to us. The drawn pairs are stored in the row, so every row is self-describing.

NO SCORING HERE, AND NO SCORE COLUMN. Raw collection files stay immutable; scoring is a separate
pass that writes its own file keyed on record_id, using the audited proximity-only scorer. The
platform's own scorer is not used (it blends an uninformative uniqueness term and redraws an
unseeded random baseline per request, so it is not reproducible).

Keys are read from env at runtime; never hard-coded, never written to disk.

Usage:
  python data_collection.py --model "GPT-4o" --api-model gpt-4o-2024-08-06 --provider openai --n 1 --dry-run
  python data_collection.py --parallel --models machine_data/models.csv --n 500
"""
import argparse, atexit, csv, hashlib, io, json, os, random, re, signal, socket, subprocess, sys, time, threading, queue
import concurrent.futures as cf
import urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
N_ITEMS = 10

# --- item source ---------------------------------------------------------------------------
# Cue pairs are drawn LOCALLY from the committed pair list, not fetched per assessment.
#
# items/cat_word_pairs_en.txt is question/dataset/words_en.txt copied from dtzx00/rugu-api-old —
# the Django backend that served the human participants. The pairs are NOT arbitrary combinations
# of words: they were precomputed by taking 200 common nouns and keeping every pair whose word
# vectors sit at cosine distance 0.85-0.95 (see that repo's cat_questions.py). That band is the
# instrument's difficulty control, so pairs must be sampled FROM this list, never generated.
#
# The file holds 22,674 lines = 7,558 distinct pairs, each appearing exactly 3 times because the
# generator was run three times in append mode. Multiplicity is uniform, so sampling the file as
# written is equivalent to sampling the distinct set; it is kept verbatim to match the server.
ITEMS_FILE = HERE / "items" / "cat_word_pairs_en.txt"

def load_pairs(path=None):
    with open(path or ITEMS_FILE, encoding="utf-8") as f:
        return [tuple(l.strip().split(",")) for l in f if l.strip()]

_PAIR_POOL = None
def pair_pool():
    global _PAIR_POOL
    if _PAIR_POOL is None:
        _PAIR_POOL = load_pairs()
    return _PAIR_POOL

def draw_items(rng=random):
    """Draw 10 cue pairs exactly the way the human participants' backend did.

    Verbatim port of the CAT branch of question/views.py in dtzx00/rugu-api-old: pick a pair at
    random, reject it if either word is already used, remove it from the candidate list either
    way, and coin-flip the display order. The two properties that matter and that a naive
    random.sample(pairs, 10) does NOT reproduce:
      1. all 20 words in an assessment are distinct — verified against 90 live API draws, 0 had a
         repeated word, while random.sample repeats in about two thirds of draws;
      2. each pair is accepted uniformly at random from the pairs still compatible with the ones
         already chosen, which is not the same as uniform over valid 10-pair sets.
    """
    pairs = list(pair_pool())
    q, used = [], set()
    while len(q) < N_ITEMS:
        if not pairs:                      # cannot happen with this pool; restart if it ever does
            pairs, q, used = list(pair_pool()), [], set()
            continue
        i = rng.randrange(len(pairs))
        a, b = pairs.pop(i)
        if a in used or b in used:
            continue
        used.add(a); used.add(b)
        q.append((a, b) if rng.choice([True, False]) else (b, a))
    return q

# --- prompt --------------------------------------------------------------------------------
# v3, written by Dawei 2026-08-03. Second-person restatement of the CAT instructions for
# single-item, single-call delivery. Differences from the participant-facing UI text, on purpose:
#   - no "Convergent Association Task" heading (models are not primed with the task name)
#   - the cue words are named inline instead of shown as a card below the instructions
#   - each rule is phrased as "Your word must ..." rather than an example label, and spells out
#     what the UI left to examples: no open or hyphenated compounds, no brands, no abbreviations
#   - the UI's fifth rule, "Do not rely on objects in your surroundings", is dropped as inert
#     for a model with no surroundings
# The instrument's substance is unchanged: similar to BOTH cues, one English word, no proper
# nouns, no specialist terms.
#
# The verb is load-bearing: "Enter", not "Generate". Measured 2026-08-03 on 10 fixed pairs,
# GPT-4.1-mini produced 5/10 invented cue blends ("inwestim", "comach", "plantfall") under
# "Generate a word" and 0/10 under "Enter a word". Adding a "must be a real word" rule did not
# repair it. Do not reintroduce "Generate".
# ENGLISH ONLY (locked 2026-08-01, Dawei): the zh-Hans arm is not collected.
ITEM_PROMPT_TEMPLATE = (
    "Enter a word that is as similar as possible, in all meanings and uses to the word pair: "
    "\"{left}\" and \"{right}\".\n\n"
    "- Your word must be similar to both words in the word pair.\n"
    "- Your word must be a single word in English (i.e., no open or hyphenated compounds).\n"
    "- Your word must not be a proper noun (i.e., no specific people, places or brands).\n"
    "- Your word must not be a specialized vocabulary or technical term (i.e., no abbreviations).\n\n"
    "Return only that single word. Do not return anything else."
)
# Bump this whenever ITEM_PROMPT_TEMPLATE changes. The rules ARE the instrument, so a wording
# change is a measure change and every row must say which wording it saw.
PROMPT_VERSION = "v3"

def build_item_prompt(left, right):
    return ITEM_PROMPT_TEMPLATE.format(left=left, right=right)

PROVIDER_TEMP_RANGE = {
    "doubao": (0, 1),      # Ark accepts (0,1]; midpoint 0.5
    "openai": (0, 2), "openai_responses": (0, 2), "xai": (0, 2), "deepseek": (0, 2), "qwen": (0, 2), "hunyuan": (0, 2),
    "anthropic": (0, 1), "moonshot": (0, 1),}
def provider_midpoint(provider):
    lo, hi = PROVIDER_TEMP_RANGE.get(provider, (0, 2))
    return (lo + hi) / 2

# --- schema --------------------------------------------------------------------------------
# ONE file. 13 assessment-level columns + 5 per item x 10 items = 63 columns.
# Every field gets its own column; nothing is packed two-to-a-cell.
# Two columns hold ten values each, as JSON lists, because a per-item column for either would
# add 20 columns of long text: raw_responses (verbatim model output per call, in item order,
# with "[ERROR: ...]" where a call failed) and reasoning (the trace per call, empty for
# non-reasoning models). Everything else is one value per column.
# Deliberately absent: endpoint_base (1:1 with provider, mapped in code), language (English only,
# locked 2026-08-01 — there is no Chinese arm, so a column recording "en" on every row says nothing),
# cat_score (raw files stay immutable; scoring writes its own file keyed on record_id).
# Model metadata (region, intelligence class, release date) is NOT duplicated here;
# machine_data/models.csv is the single registry and joins on model_name.
META_FIELDS = [
    "record_id", "model_name", "api_model_requested", "api_model_returned",
    "provider", "vendor", "prompt_version", "temperature", "max_tokens",
    "assessment_start_utc", "assessment_duration_ms",
    "raw_responses", "reasoning",
]
ITEM_FIELDS = []
for _i in range(N_ITEMS):
    ITEM_FIELDS += [f"cue_{_i}_left", f"cue_{_i}_right", f"word_{_i}",
                    f"item_{_i}_request_utc", f"item_{_i}_response_utc"]
FIELDS = META_FIELDS + ITEM_FIELDS

def _parse_ts(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00'))

def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

def _record_id(model_name, batch, started):
    h = hashlib.sha256(f"{model_name}|{batch}|{started}".encode()).hexdigest()[:12]
    return f"cat_{h}"

# ---- reasoning capture ---------------------------------------------------------------------
# POLICY (locked 2026-07-27, Dawei): capture ALL reasoning the API returns, and use each model's
# DEFAULT thinking effort. Never send a reasoning_effort / thinking-budget override.
def _extract_inline_think(text):
    if not text: return "", text
    m = re.search(r"<think(?:ing)?>(.*?)</think(?:ing)?>", text, re.DOTALL|re.IGNORECASE)
    if not m: return "", text
    reasoning = m.group(1).strip()
    clean = re.sub(r"<think(?:ing)?>.*?</think(?:ing)?>", "", text, flags=re.DOTALL|re.IGNORECASE).strip()
    return reasoning, clean

# ---- the per-call cap ------------------------------------------------------------------------
# Dawei's rule (2026-08-04): ONE word must not cost more than five minutes. A model that cannot
# answer inside the cap is not a slow model to wait for, it is a model to drop.
CALL_TIMEOUT_S = 300.0

class TooSlow(Exception):
    """The call hit CALL_TIMEOUT_S. Deliberately NOT transient: retrying spends another five
    minutes to learn what we already know. The word is left blank and the run moves on."""

def _post_full(url, headers, body, timeout=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout or CALL_TIMEOUT_S) as r:
            return json.loads(r.read()), dict(r.headers)
    except socket.timeout:
        raise TooSlow(f"exceeded the {CALL_TIMEOUT_S:.0f}s per-call cap")
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise TooSlow(f"exceeded the {CALL_TIMEOUT_S:.0f}s per-call cap")
        raise

MAX_TOKENS_ANTHROPIC = 4000

# ---- streaming -------------------------------------------------------------------------------
# Streaming is on by default (--no-stream disables it). Two reasons, neither of them speed:
#   1. It makes the per-word cap HONEST. A socket timeout is an inactivity timer, so a gateway that
#      trickles keep-alive bytes never trips it — DeepSeek-V4-Flash returned a COMPLETED call at
#      458s under a 300s socket timeout. Streaming puts a clock on the bytes.
#   2. It makes the cap CHEAP. Hanging up tells the provider to stop generating; abandoning a
#      blocking call leaves the meter running on tokens nobody will ever read.
# It does not change the request otherwise, so the condition is unchanged.
STREAM = True

def _post_stream(url, headers, body, deadline=None):
    """POST with stream=True and read the SSE lines, stopping dead at the wall-clock cap.

    Returns (events, headers). A malformed line is skipped rather than fatal; a provider that
    cannot stream yields no usable events and the caller falls back to a blocking request.
    """
    body = dict(body); body["stream"] = True
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    end = deadline if deadline is not None else time.time() + CALL_TIMEOUT_S
    try:
        resp = urllib.request.urlopen(req, timeout=min(CALL_TIMEOUT_S, max(end - time.time(), 0.001)))
    except socket.timeout:
        raise TooSlow(f"exceeded the {CALL_TIMEOUT_S:.0f}s per-word cap")
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise TooSlow(f"exceeded the {CALL_TIMEOUT_S:.0f}s per-word cap")
        raise
    events, hdrs = [], dict(resp.headers)
    try:
        for raw in resp:
            if time.time() >= end:
                raise TooSlow(f"exceeded the {CALL_TIMEOUT_S:.0f}s per-word cap")
            line = raw.decode("utf-8", "replace").strip()
            if not line or line.startswith(":") or line.startswith("event:"):
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if line == "[DONE]":
                break
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except socket.timeout:
        raise TooSlow(f"exceeded the {CALL_TIMEOUT_S:.0f}s per-word cap")
    finally:
        resp.close()                     # hanging up IS the cancel
    return events, hdrs

def _fold_chat_stream(events):
    """Fold OpenAI-compatible deltas back into the blocking response shape, so every adapter parses
    ONE shape and streaming cannot change what lands in the CSV."""
    text, reasoning, finish, model, rid, usage = [], [], "", "", "", {}
    for ev in events:
        model = ev.get("model") or model
        rid = ev.get("id") or rid
        usage = ev.get("usage") or usage
        for ch in ev.get("choices") or []:
            delta = ch.get("delta") or ch.get("message") or {}
            text.append(delta.get("content") or "")
            reasoning.append(delta.get("reasoning_content") or delta.get("reasoning") or "")
            finish = ch.get("finish_reason") or finish
    joined, thought = "".join(text), "".join(reasoning)
    return {"choices": [{"message": {"content": joined, "reasoning_content": thought},
                         "finish_reason": finish}],
            "model": model, "id": rid, "usage": usage,
            "_text_seen": bool(joined or thought)}

def _fold_anthropic_stream(events):
    """Same for Anthropic: text_delta and thinking_delta accumulate into its content blocks."""
    text, thinking, model, rid, stop, usage = [], [], "", "", "", {}
    for ev in events:
        t = ev.get("type")
        if t == "message_start":
            m = ev.get("message") or {}
            model = m.get("model") or model; rid = m.get("id") or rid
            usage = m.get("usage") or usage
        elif t == "content_block_delta":
            d = ev.get("delta") or {}
            if d.get("type") == "text_delta": text.append(d.get("text") or "")
            elif d.get("type") == "thinking_delta": thinking.append(d.get("thinking") or "")
        elif t == "message_delta":
            stop = (ev.get("delta") or {}).get("stop_reason") or stop
            usage = {**usage, **(ev.get("usage") or {})}
    blocks = ([{"type": "thinking", "thinking": "".join(thinking)}] if thinking else []) + \
             [{"type": "text", "text": "".join(text)}]
    return {"content": blocks, "model": model, "id": rid, "stop_reason": stop, "usage": usage,
            "_text_seen": bool("".join(text) or "".join(thinking))}

# ---- provider adapters ---------------------------------------------------------------------
def _openai_like(base, key, api_model, prompt, temperature, extra_headers=None):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra_headers: headers.update(extra_headers)
    body = {"model": api_model, "messages": [{"role":"user","content":prompt}]}
    if temperature is not None: body["temperature"] = temperature   # None = omit, use model default
    url = f"{base}/chat/completions"
    d, h = {}, {}
    if STREAM:
        events, h = _post_stream(url, headers, body)
        d = _fold_chat_stream(events)
    if not d.get("_text_seen"):
        # A provider that will not stream still gets collected; take the blocking answer.
        d, h = _post_full(url, headers, body)
    ch = (d.get("choices") or [{}])[0]
    usage = d.get("usage") or {}
    _msg = ch.get("message") or {}
    _content = (_msg.get("content") or "")
    _reasoning = (_msg.get("reasoning_content") or _msg.get("reasoning") or "").strip()
    _inline, _clean = _extract_inline_think(_content)
    if not _reasoning and _inline:
        _reasoning = _inline; _content = _clean
    return {
        "text": _content.strip(), "reasoning_text": _reasoning,
        "api_model_returned": d.get("model",""), "response_id": d.get("id",""),
        "system_fingerprint": d.get("system_fingerprint",""), "finish_reason": ch.get("finish_reason",""),
        "prompt_tokens": usage.get("prompt_tokens",""), "completion_tokens": usage.get("completion_tokens",""),
        "total_tokens": usage.get("total_tokens",""),
        "api_request_id": h.get("x-request-id") or h.get("x-amzn-requestid") or h.get("request-id",""),
        "endpoint_base": base, "max_tokens": "",
    }

def _anthropic(base, key, api_model, prompt, temperature):
    headers = {"x-api-key": key, "anthropic-version":"2023-06-01", "Content-Type":"application/json"}
    body = {"model": api_model, "max_tokens":MAX_TOKENS_ANTHROPIC,
            "messages":[{"role":"user","content":prompt}]}
    if temperature is not None: body["temperature"] = temperature   # None = omit, use model default
    url = f"{base}/messages"
    d, h = {}, {}
    if STREAM:
        events, h = _post_stream(url, headers, body)
        d = _fold_anthropic_stream(events)
    if not d.get("_text_seen"):
        d, h = _post_full(url, headers, body)
    usage = d.get("usage") or {}
    _blocks = d.get("content",[])
    _reasoning = "".join(b.get("thinking","") for b in _blocks if b.get("type")=="thinking").strip()
    return {
        "text": "".join(b.get("text","") for b in _blocks if b.get("type")=="text").strip(),
        "reasoning_text": _reasoning,
        "api_model_returned": d.get("model",""), "response_id": d.get("id",""),
        "system_fingerprint": "", "finish_reason": d.get("stop_reason",""),
        "prompt_tokens": usage.get("input_tokens",""), "completion_tokens": usage.get("output_tokens",""),
        "total_tokens": (usage.get("input_tokens",0) or 0)+(usage.get("output_tokens",0) or 0),
        "api_request_id": h.get("request-id",""), "endpoint_base": base,
        "max_tokens": MAX_TOKENS_ANTHROPIC,
    }

# (adapter, env key). No third element: the old "supports seed" flag is gone with seeding itself.
def _openai_responses(base, key, api_model, prompt, temperature):
    """OpenAI's /responses endpoint.

    The six *-pro models are served ONLY here — chat/completions answers
    404 "This is not a chat model" / "only supported in v1/responses". Same prompt, same single
    user turn; only the envelope differs, so the condition is unchanged.

    `reasoning.summary="auto"` is a CAPTURE knob, not an effort knob: it asks for a summary of
    thinking the model does anyway. Without it the reasoning item comes back with an empty summary.
    If an account is not verified for summaries the API 400s, so we retry once without it rather
    than lose the answer.
    """
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {"model": api_model, "input": prompt, "reasoning": {"summary": "auto"}}
    if temperature is not None: body["temperature"] = temperature   # None = omit, use model default
    url = f"{base}/responses"
    def _send(bd):
        if STREAM:
            events, hh = _post_stream(url, headers, bd)
            # The terminal event carries the whole response object, so what follows parses
            # identically for streamed and blocking calls.
            for ev in reversed(events):
                if ev.get("type") == "response.completed" and ev.get("response"):
                    return ev["response"], hh
        return _post_full(url, headers, bd)
    try:
        d, h = _send(body)
    except urllib.error.HTTPError as e:
        detail = ""
        try: detail = e.read().decode()
        except Exception: pass
        if e.code == 400 and "summary" in detail.lower():
            body.pop("reasoning")
            d, h = _send(body)
        else:
            raise urllib.error.HTTPError(e.url, e.code, e.reason, e.headers, io.BytesIO(detail.encode()))
    text, reasoning = "", []
    for item in d.get("output") or []:
        if item.get("type") == "message":
            text += "".join(c.get("text","") for c in (item.get("content") or []))
        elif item.get("type") == "reasoning":
            reasoning += [sm.get("text","") for sm in (item.get("summary") or [])]
    usage = d.get("usage") or {}
    status = d.get("status","")
    incomplete = ((d.get("incomplete_details") or {}).get("reason") or "")
    return {
        "text": text.strip(), "reasoning_text": "\n".join(t for t in reasoning if t).strip(),
        "api_model_returned": d.get("model",""), "response_id": d.get("id",""),
        "system_fingerprint": "", "finish_reason": f"{status}:{incomplete}" if incomplete else status,
        "prompt_tokens": usage.get("input_tokens",""), "completion_tokens": usage.get("output_tokens",""),
        "total_tokens": usage.get("total_tokens",""),
        "api_request_id": h.get("x-request-id") or h.get("request-id",""),
        "endpoint_base": base, "max_tokens": "",
    }

PROVIDERS = {
    "openai":    (lambda k,m,p,t: _openai_like("https://api.openai.com/v1", k, m, p, t), "OPENAI_API_KEY"),
    # Same key and same account as `openai`; a separate lane so the six slow pro models get their
    # own file and their own concurrency pool instead of clogging the 33-model chat lane.
    "openai_responses": (lambda k,m,p,t: _openai_responses("https://api.openai.com/v1", k, m, p, t), "OPENAI_API_KEY"),
    "anthropic": (lambda k,m,p,t: _anthropic("https://api.anthropic.com/v1", k, m, p, t), "ANTHROPIC_API_KEY"),
    "xai":       (lambda k,m,p,t: _openai_like("https://api.x.ai/v1", k, m, p, t), "XAI_API_KEY"),
    "deepseek":  (lambda k,m,p,t: _openai_like("https://api.deepseek.com/v1", k, m, p, t), "DEEPSEEK_API_KEY"),
    "qwen":      (lambda k,m,p,t: _openai_like("https://dashscope.aliyuncs.com/compatible-mode/v1", k, m, p, t), "QWEN_API_KEY"),
    "hunyuan":   (lambda k,m,p,t: _openai_like("https://tokenhub.tencentmaas.com/v1", k, m, p, t), "HUNYUAN_API_KEY"),
    "moonshot":  (lambda k,m,p,t: _openai_like("https://api.moonshot.ai/v1", k, m, p, t), "MOONSHOT_API_KEY"),
    # Volcano Engine Ark (ByteDance). OpenAI-compatible. Serves Doubao plus third-party weights
    # (DeepSeek, Kimi, Qwen, GLM, Mistral) at their ORIGINAL dated snapshots, several of which are
    # no longer available from the vendors' own APIs.
    "doubao":    (lambda k,m,p,t: _openai_like("https://ark.cn-beijing.volces.com/api/v3", k, m, p, t), "DOUBAO_API_KEY"),
}

# ---- vendor -> API lane ---------------------------------------------------------------------
# models.csv `provider` is the VENDOR that made the model, which is not always the API that
# serves it. Verified from the DAT run: Tencent and MiniMax models were served through the
# Tencent MaaS gateway (the `hunyuan` lane), as were a couple of DeepSeek/Qwen snapshots.
# A `lane` column in models.csv overrides this map per model.
LANE_BY_VENDOR = {
    "openai": "openai", "anthropic": "anthropic", "xai": "xai", "deepseek": "deepseek",
    "qwen": "qwen", "moonshot": "moonshot", "tencent": "hunyuan", "minimax": "hunyuan",
}

def resolve_lane(model_row):
    lane = (model_row.get("lane") or "").strip()
    if lane: return lane
    return LANE_BY_VENDOR.get((model_row.get("provider") or "").strip().lower(), "")

# ---- parsing --------------------------------------------------------------------------------
WORD_RE = re.compile(r"^[a-z][a-z'-]{0,29}$")

def _reduce(fragment):
    """Strip decoration from a fragment and return it if it is one valid word, else ''."""
    t = re.sub(r"[*_`\"']", "", fragment)
    t = re.sub(r"^\s*(?:\d+[.)]|[-•])\s*", "", t)
    t = t.strip().strip(".,;:!?").strip().lower()
    return t if WORD_RE.match(t) else ""

def parse_word(text):
    """Extract the answer from the LAST line only, or fail.

    Models are told to return only the word, but some think out loud first. The answer, when
    present, is always last. An earlier version scanned upward until some line reduced to a
    single word, which silently harvested candidates the model had CONSIDERED AND REJECTED:
    a Claude response ending "Actually, I think the answer is: **den**" was recorded as "tank"
    from a bullet higher up. A wrong word that looks plausible is worse than no word, so only
    the final line is read, and a response that trails off mid-sentence yields nothing.

    Accepted on the last line: a bare word, a bolded word, and a trailing "... answer is: word".
    """
    lines = [l for l in (text or "").splitlines() if l.strip()]
    if not lines:
        return "", "failed"
    last = lines[-1]
    w = _reduce(last)
    if w:
        return w, "ok"
    if ":" in last:                                  # "The answer is: **den**"
        w = _reduce(last.rsplit(":", 1)[1])
        if w:
            return w, "ok"
    bold = re.findall(r"\*\*([^*]+)\*\*", last)     # "... I would say **den** here"
    if bold:
        w = _reduce(bold[-1])
        if w:
            return w, "ok"
    # Answer-then-explain: some models put the word on line 1 and justify below
    # (Grok-4.20-reason does this). Safe to accept because a model that deliberates FIRST never
    # opens with a bare single word — it opens with prose. So this cannot pick up a rejected
    # candidate, which is the failure the last-line rule exists to prevent.
    if len(lines) > 1:
        w = _reduce(lines[0])
        if w:
            return w, "ok"
    return "", "failed"

def call_once(provider, key, api_model, prompt, target_temp):
    """One call. NO SEED IS EVER SENT (locked 2026-08-03, Dawei).

    Only openai, deepseek and qwen accept a seed at all, so seeding meant three lanes ran under a
    different sampling condition from the other five — an asymmetry across the 77-model lineup for
    no gain, since every assessment draws different word pairs and nothing is reproducible
    call-to-call at these temperatures anyway. Every model now runs on its provider's default
    sampling at the lane midpoint temperature."""
    fn = PROVIDERS[provider][0]
    label = "provider default" if target_temp is None else target_temp
    try:
        return fn(key, api_model, prompt, target_temp), label
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode()
        except Exception: pass
        if e.code == 400 and "temperature" in body.lower():
            # Resending a NUMBER here was a no-op for every (0,2) lane, whose midpoint is already
            # 1.0. Omit the parameter instead: the model applies its own default, and we record
            # "provider default" rather than a temperature we did not send.
            return fn(key, api_model, prompt, None), "provider default"
        raise RuntimeError(f"HTTP {e.code}: {body[:200]}")

TRANSIENT_BITS = ("429", "timed out", "timeout", "temporarily", "connection", "reset",
                  "incompleteread", "chunked",
                  " 500", " 502", " 503", " 504", " 520", " 521", " 522", " 524")
def _is_transient(msg):
    m = msg.lower()
    return any(b.strip() in m for b in TRANSIENT_BITS)

def call_item(provider, key, api_model, prompt, target_temp, max_retries=6):
    """One call for one cue pair, with bounded retry on transient failures.
    Returns (payload|None, temp_used, retries, error_str).

    The cap is enforced on WALL CLOCK, not on the socket. A socket timeout is an INACTIVITY timer:
    a provider that trickles reasoning tokens for eight minutes never goes idle for 300s, so it
    sails past the cap. Measured on 2026-08-04 — DeepSeek-V4-Flash returned a completed call at
    458s under a 300s socket timeout. So the call runs in its own thread and we stop waiting at the
    cap. The abandoned thread is not cancellable and its tokens are already billed; what the cap
    buys is that the RUN stops waiting, not that the provider stops generating."""
    retries = 0
    # The cap is a budget for the WHOLE WORD, retries included. Capping each attempt separately
    # left the hole this was meant to close: a 400-then-retry or a couple of 429s multiplied the
    # cap by the attempt count, and items were still alive at 600s under a 300s "cap".
    word_deadline = time.time() + CALL_TIMEOUT_S
    while True:
        left = word_deadline - time.time()
        if left <= 0:
            return None, target_temp, retries, f"exceeded the {CALL_TIMEOUT_S:.0f}s per-word cap"
        try:
            # Streaming already enforces the wall-clock cap inside the read loop, so the watchdog
            # thread is only needed for a blocking call. Spawning one per word ALSO broke on exit:
            # "cannot schedule new futures after interpreter shutdown" appeared 110 times in the
            # wave-2 run, recording model errors that were really our own shutdown. Fall back to a
            # direct call when a thread cannot be started.
            if STREAM:
                payload, temp_used = call_once(provider, key, api_model, prompt, target_temp)
            else:
                try:
                    ex = cf.ThreadPoolExecutor(1)
                except RuntimeError:
                    payload, temp_used = call_once(provider, key, api_model, prompt, target_temp)
                    return payload, temp_used, retries, ""
                try:
                    fut = ex.submit(call_once, provider, key, api_model, prompt, target_temp)
                    try:
                        payload, temp_used = fut.result(timeout=left)
                    except cf.TimeoutError:
                        raise TooSlow(f"exceeded the {CALL_TIMEOUT_S:.0f}s per-word cap")
                finally:
                    ex.shutdown(wait=False)
            return payload, temp_used, retries, ""
        except TooSlow as e:
            return None, target_temp, retries, str(e)
        except Exception as e:
            msg = str(e)
            if _is_transient(msg) and retries < max_retries and time.time() < word_deadline:
                retries += 1
                time.sleep(min(2.0 * retries, 15))
                continue
            return None, target_temp, retries, msg[:200]


# ---- one assessment = 10 calls --------------------------------------------------------------
def run_assessment(model_name, api_model, prov, meta, batch, key,
                   pairs=None, item_workers=1, deadline_s=1200):
    """Fetch 10 pairs (unless supplied), call the model once per pair, return one row.

    A failed call leaves its word blank and records "[ERROR: ...]" in raw_responses for that
    item. The other nine are still valid data, so the assessment is always kept.
    """
    if pairs is None:
        pairs = draw_items()
    target_temp = provider_midpoint(prov)
    started = _now(); t_start = time.time()
    record_id = _record_id(model_name, batch, started)

    expired = threading.Event()          # set when the assessment deadline passes
    temp_lock = threading.Lock()
    forced_default = [False]             # sticky: once one call drops the temperature, all do

    def one_item(i):
        if expired.is_set():             # deadline passed before this item was dispatched
            return i, _now(), _now(), None, "", "assessment deadline (not attempted)"
        left, right = pairs[i]
        prompt = build_item_prompt(left, right)
        req_ts = _now()
        with temp_lock:
            t = None if forced_default[0] else target_temp
        payload, temp_used, retries, err = call_item(prov, key, api_model, prompt, t)
        if temp_used == "provider default":
            # A provider that rejects its lane midpoint rejects it for every call, so make the
            # fallback sticky. This guarantees one temperature per assessment instead of leaving
            # the row's single temperature column to whichever item finished last.
            with temp_lock:
                forced_default[0] = True
        return i, req_ts, _now(), payload, temp_used, err

    # Items are independent by construction — each call is a fresh context — so running them
    # concurrently changes timing only, never the data. Default 1 keeps a model's request rate
    # low and its per-item timestamps non-overlapping; raise it for slow reasoning models.
    # A hung provider must not hold the run. Kimi-K2.6 and MiniMax-M2.7 each sat >25 min on one
    # assessment (300s socket timeout x 6 retries = 30 min per item, worst case). Past the
    # deadline the assessment is written with whatever came back; unfinished items are errors.
    started_at = time.time()
    # ONE execution path at every concurrency. A 1-worker pool runs the items in submission order,
    # exactly like the old serial loop, but routing both cases through futures means the deadline
    # is enforced DURING a call, not only between calls. Previously a single hung request could
    # ignore --assessment-timeout entirely in the serial path (300s socket x 6 retries = 30 min).
    ex = cf.ThreadPoolExecutor(min(max(item_workers, 1), N_ITEMS))
    futs = {ex.submit(one_item, i): i for i in range(len(pairs))}
    # HARVEST EVERY FINISHED ITEM BEFORE CANCELLING ANYTHING. The old loop waited on futures in
    # submission order and, on the first timeout, wrote placeholders only for the future it was
    # waiting on plus futures not yet done — so an item that had ALREADY ANSWERED but had not been
    # read yet was dropped with NO RECORD AT ALL. That is why 145 item slots in the 2026-08-03 run
    # had no entry in raw_responses, and why models that answered most of their items were scored
    # 0 words and diagnosed "too slow". cf.wait hands back the finished set, so nothing answered is
    # thrown away and raw_responses is always exactly N_ITEMS long.
    left = deadline_s - (time.time() - started_at)
    finished, unfinished = cf.wait(list(futs), timeout=max(left, 0))
    results = []
    for f in finished:
        try:
            results.append(f.result())
        except Exception as e:
            results.append((futs[f], _now(), _now(), None, "", f"collector crash: {e}"[:200]))
    if unfinished:
        expired.set()                    # stop items that have not started spending yet
        for f in unfinished:
            f.cancel()
        for f in unfinished:
            results.append((futs[f], _now(), _now(), None, "",
                            f"assessment deadline {deadline_s}s"))
    ex.shutdown(wait=False)
    seen = set()
    results = [r for r in sorted(results, key=lambda r: r[0])
               if not (r[0] in seen or seen.add(r[0]))]

    words, raws, reasonings, item_ts = [], [], [], []
    api_model_returned = ""; max_tokens = ""; temps_used = set()
    for i, req_ts, resp_ts, payload, temp_used, err in results:
        if payload is None:
            words.append(""); raws.append(f"[ERROR: {err}]"); reasonings.append("")
        else:
            word, _status = parse_word(payload["text"])
            words.append(word)
            raws.append(payload["text"])
            reasonings.append(payload.get("reasoning_text", ""))
            api_model_returned = api_model_returned or payload.get("api_model_returned", "")
            temps_used.add(temp_used)
            max_tokens = payload.get("max_tokens", "") or max_tokens
        item_ts.append((req_ts, resp_ts))

    # The sticky fallback should make this a single value always. "mixed" is an alarm, not an
    # expected state: it means a provider rejected the temperature intermittently.
    temp_effective = (temps_used.pop() if len(temps_used) == 1
                      else ("" if not temps_used else "mixed:" + "/".join(map(str, sorted(map(str, temps_used))))))
    row = {
        "record_id": record_id, "model_name": model_name, "api_model_requested": api_model,
        "api_model_returned": api_model_returned, "provider": prov,
        "vendor": meta.get("vendor", ""), "prompt_version": PROMPT_VERSION,
        "temperature": temp_effective, "max_tokens": max_tokens,
        "assessment_start_utc": started,
        "assessment_duration_ms": int((time.time() - t_start) * 1000),
        "raw_responses": json.dumps(raws, ensure_ascii=False),
        "reasoning": json.dumps(reasonings, ensure_ascii=False),
    }
    for i in range(N_ITEMS):
        row[f"cue_{i}_left"]  = pairs[i][0] if i < len(pairs) else ""
        row[f"cue_{i}_right"] = pairs[i][1] if i < len(pairs) else ""
        row[f"word_{i}"]      = words[i] if i < len(words) else ""
        row[f"item_{i}_request_utc"]  = item_ts[i][0] if i < len(item_ts) else ""
        row[f"item_{i}_response_utc"] = item_ts[i][1] if i < len(item_ts) else ""
    return row

# ---- io -------------------------------------------------------------------------------------
def _append(path, fields, rows):
    if not rows: return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists: w.writeheader()
        w.writerows(rows)

def write_assessment(out_csv, row):
    _append(out_csv, FIELDS, [row])

# Reasoning traces blow past Python's default 128 KiB CSV field cap — DeepSeek-V4-Flash wrote
# 827,556 characters of reasoning for ONE assessment. Without this, reading our own output back
# raises _csv.Error and every resume of a reasoning-heavy model dies before it can count its rows.
csv.field_size_limit(sys.maxsize)

def existing_count(out_csv, model_name):
    """Assessments already collected for this model that carry at least one parsed word.

    Wordless rows are NOT counted. They are kept for provenance (they record what the API said),
    but counting them would let a model that fails every parse look progressively 'more done' on
    each resume, and quietly stop retrying while producing nothing."""
    if not out_csv.exists(): return 0
    with open(out_csv, encoding="utf-8") as f:
        return sum(1 for r in csv.DictReader(f)
                   if r["model_name"] == model_name
                   and any(r.get(f"word_{i}") for i in range(N_ITEMS)))

_write_locks = {}
_wl_guard = threading.Lock()
def write_lock(path):
    with _wl_guard:
        if path not in _write_locks: _write_locks[path] = threading.Lock()
        return _write_locks[path]

def acquire_lock(out_dir, stale_after=300.0):
    """One collector per output directory, enforced instead of remembered.

    Two collectors briefly overlapped on 2026-08-03 and re-collected six models, because resuming
    counts rows and rows are not a lock. The real damage is subtler: duplicate assessments split a
    model's empty rows between two processes, so neither saw three in a row and the 3-strikes
    abandonment never fired. A masked failure signal is worse than a wasted call.

    Liveness is a HEARTBEAT, not a pid. Container pids are low and reused, /proc is not always
    readable, and os.kill(pid, 0) answered "alive" for a lock left behind by a killed collector —
    which then blocked every restart. The holder rewrites its timestamp every 60s; a lock that has
    not been touched in `stale_after` seconds is dead no matter what its pid claims.
    """
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    lock = out / ".collector.lock"

    def write(fd=None):
        payload = f"{os.getpid()} {time.time():.0f}\n".encode()
        if fd is not None:
            os.write(fd, payload)
        else:
            lock.write_bytes(payload)

    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            write(fd); os.close(fd)
            break
        except FileExistsError:
            try:
                parts = lock.read_text().split()
                pid, beat = int(parts[0]), float(parts[1]) if len(parts) > 1 else 0.0
            except (ValueError, IndexError, OSError):
                pid, beat = 0, 0.0
            age = time.time() - beat
            if beat and age < stale_after:
                sys.exit(f"another collector (pid {pid}) is writing to {out} — its heartbeat is "
                         f"{age:.0f}s old. Wait for it, or use a different --out-dir.")
            print(f"clearing a stale lock (pid {pid or 'unknown'}, "
                  f"{'no heartbeat' if not beat else f'{age:.0f}s since its last heartbeat'})",
                  flush=True)
            try: lock.unlink()
            except FileNotFoundError: pass

    atexit.register(lambda: lock.exists() and lock.unlink())
    def beat():
        while True:
            time.sleep(60)
            try: write()
            except OSError: return
    threading.Thread(target=beat, daemon=True).start()


def load_live(models_csv, only=None):
    """Group models by resolved API lane. Models with no known lane are reported, never dropped
    silently — a missing endpoint must be fixed, not skipped."""
    lanes, unrouted = {}, []
    for r in csv.DictReader(open(models_csv, encoding="utf-8")):
        if (r.get("status") or "live").strip().lower() != "live": continue
        lane = resolve_lane(r)
        if lane not in PROVIDERS:
            unrouted.append((r.get("model",""), r.get("provider","")))
            continue
        if only and lane not in only: continue
        lanes.setdefault(lane, []).append(r)
    if unrouted:
        print("=== UNROUTED MODELS (no API lane — NOT collected) ===", flush=True)
        for m, v in unrouted: print(f"  {m}  (vendor: {v})", flush=True)
    return lanes

class Progress:
    """Live progress for a run measured in hours. Without this the only way to see where a model
    is up to is grepping the CSV."""
    def __init__(self, target_per_model, total_models):
        self.target = target_per_model; self.total_models = total_models
        self.done = {}            # model -> assessments written this run
        self.have = {}            # model -> assessments already on disk at start
        self.finished = set()
        self.t0 = time.time()
        self.lock = threading.Lock()
    def start_model(self, name, have):
        with self.lock: self.have[name] = have; self.done.setdefault(name, 0)
    def tick(self, name):
        with self.lock: self.done[name] = self.done.get(name, 0) + 1
    def finish(self, name):
        with self.lock: self.finished.add(name)
    def snapshot(self):
        with self.lock:
            written = sum(self.done.values())
            at = {n: self.have.get(n, 0) + self.done.get(n, 0) for n in self.done}
            remaining = sum(max(0, self.target - v) for v in at.values())
            elapsed = time.time() - self.t0
            rate = written / (elapsed / 60) if elapsed > 0 else 0
            eta = f"{remaining / rate / 60:.1f}h" if (rate > 0 and remaining) else ("done" if not remaining else "?")
            slowest = sorted(at.items(), key=lambda kv: kv[1])[:3]
            return (f"PROGRESS {len(self.finished)}/{self.total_models} models done | "
                    f"{written} assessments this run ({written*N_ITEMS} calls) | "
                    f"{rate:.1f}/min | remaining {remaining} | "
                    f"ETA {eta}" + (" | furthest behind: " +
                    ", ".join(f"{n} {v}/{self.target}" for n, v in slowest) if slowest else ""))

def progress_printer(prog, every, stop):
    while not stop.wait(every):
        print(prog.snapshot(), flush=True)

class LaunchGate:
    def __init__(self, min_gap):
        self.min_gap = min_gap; self.lock = threading.Lock(); self.last = 0.0
    def wait(self):
        with self.lock:
            now = time.time(); delta = now - self.last
            if delta < self.min_gap: time.sleep(self.min_gap - delta)
            self.last = time.time()

def collect_one(model_row, n, out_csv, batch, gate, key, stop,
                item_workers=1, prog=None, assess_workers=1, deadline_s=1200):
    prov = resolve_lane(model_row); name = model_row["model"]
    api = model_row.get("api_model_id") or model_row["model"]
    meta = {"vendor": model_row.get("provider","")}
    have = existing_count(out_csv, name); made = have
    if prog: prog.start_model(name, have)
    lk = write_lock(str(out_csv))
    dead = 0

    # Per-call timing, kept so the model can be judged against the five-minute rule while it runs.
    pace = {"calls": 0, "capped": 0, "secs": 0.0, "timed": 0}
    pace_lock = threading.Lock()

    def one_assessment(seq):
        pairs = draw_items()
        gate.wait()
        row = run_assessment(name, api, prov, meta, batch, key,
                             pairs=pairs, item_workers=item_workers,
                             deadline_s=deadline_s)
        with lk: write_assessment(out_csv, row)
        capped = sum(1 for e in json.loads(row["raw_responses"]) if "per-word cap" in e)
        secs, timed = 0.0, 0
        for i in range(N_ITEMS):
            a, b = row.get(f"item_{i}_request_utc"), row.get(f"item_{i}_response_utc")
            if a and b and row.get(f"word_{i}"):
                secs += (_parse_ts(b) - _parse_ts(a)).total_seconds(); timed += 1
        with pace_lock:
            pace["calls"] += N_ITEMS; pace["capped"] += capped
            pace["secs"] += secs; pace["timed"] += timed
        return row

    def too_slow():
        """Dawei's rule, applied while the run is going: a model that spends more than five
        minutes on the average word is dropped, not waited for. Judged on completed calls once
        there are enough of them, and on cap hits when nothing completes at all.

        `pace_exempt` in models.csv overrides the drop for a model we want for reasons the clock
        does not capture — Kimi-K3 is too prominent to be missing from the lineup. The exemption
        stops the DROP only; the 300s per-word cap still applies, so an exempt model costs the run
        nothing extra and simply comes back with blanks where it was too slow."""
        with pace_lock:
            calls, capped, secs, timed = pace["calls"], pace["capped"], pace["secs"], pace["timed"]
        if calls < 10: return ""
        if (model_row.get("pace_exempt") or "").strip().lower() in ("yes","y","true","1"):
            with pace_lock:
                if pace.get("warned"): return ""
                pace["warned"] = True
            rate = 100 * capped / calls
            print(f"PACE {name} ({prov}): over the {CALL_TIMEOUT_S:.0f}s cap on {rate:.0f}% of "
                  f"calls — kept anyway (pace_exempt), expect blanks", flush=True)
            return ""
        if timed >= 5 and secs / timed > CALL_TIMEOUT_S:
            return f"averages {secs/timed:.0f}s per word, over the {CALL_TIMEOUT_S:.0f}s cap"
        if capped / calls >= 0.5:
            return f"{100*capped/calls:.0f}% of calls hit the {CALL_TIMEOUT_S:.0f}s cap"
        return ""

    # Assessments within a model can run concurrently. Serial assessments made the slowest model
    # the whole run's floor: MiniMax-M3 at 992s per assessment is 138 hours for n=500 on its own.
    if assess_workers > 1:
        with cf.ThreadPoolExecutor(assess_workers) as ex:
            pending = {}
            seq = made
            while (made < n or pending) and not stop.is_set():
                while len(pending) < assess_workers and seq < n:
                    pending[ex.submit(one_assessment, seq)] = seq; seq += 1
                if not pending: break
                done, _ = cf.wait(list(pending), return_when=cf.FIRST_COMPLETED)
                for fut in done:
                    pending.pop(fut)
                    row = fut.result()
                    made += 1
                    if prog: prog.tick(name)
                    if not any(row[f"word_{i}"] for i in range(N_ITEMS)):
                        dead += 1
                    else:
                        dead = 0
                if dead >= 3:
                    print(f"FAIL {name} ({prov}): 3 consecutive empty assessments", flush=True)
                    if prog: prog.finish(name)
                    return name, made-have, "error:3 empty assessments"
                slow = too_slow()
                if slow:
                    print(f"DROP {name} ({prov}): TOO SLOW — {slow}", flush=True)
                    if prog: prog.finish(name)
                    return name, made-have, f"too slow:{slow}"
    else:
        while made < n and not stop.is_set():
            row = one_assessment(made)
            made += 1
            if prog: prog.tick(name)
            if not any(row[f"word_{i}"] for i in range(N_ITEMS)):
                dead += 1
                if dead >= 3:
                    errs = json.loads(row["raw_responses"])
                    err = next((e for e in errs if e.startswith("[ERROR")), "all calls failed")
                    print(f"FAIL {name} ({prov}): {err[:90]}", flush=True)
                    if prog: prog.finish(name)
                    return name, made-have, f"error:{err[:60]}"
            else:
                dead = 0
            slow = too_slow()
            if slow:
                print(f"DROP {name} ({prov}): TOO SLOW — {slow}", flush=True)
                if prog: prog.finish(name)
                return name, made-have, f"too slow:{slow}"
    if prog: prog.finish(name)
    return name, made-have, "done"

def run_lane(prov, models, n, out_dir, batch, concurrency, min_gap, stop,
             lane_results=None, item_workers=1, prog=None, assess_workers=1, deadline_s=1200):
    key = os.environ.get(PROVIDERS[prov][1])
    if not key:
        print(f"LANE {prov}: MISSING KEY {PROVIDERS[prov][1]} — skipped", flush=True); return
    out_csv = Path(out_dir)/f"topup_{prov}.csv"
    gate = LaunchGate(min_gap)
    todo = [m for m in models if existing_count(out_csv, m["model"]) < n]
    print(f"LANE {prov}: {len(todo)}/{len(models)} models need work (concurrency={concurrency})", flush=True)
    q = queue.Queue()
    for m in todo: q.put(m)
    results = []
    def worker():
        while not stop.is_set():
            try: m = q.get_nowait()
            except queue.Empty: return
            try:
                name, got, st = collect_one(m, n, out_csv, batch, gate, key, stop,
                                            item_workers=item_workers, prog=prog,
                                            assess_workers=assess_workers, deadline_s=deadline_s)
                results.append((name, got, st))
                print(f"  [{prov}] {name}: +{got} ({st})", flush=True)
            except Exception as e:
                # A bug in the collector must not read as "collected cleanly". It did once: an
                # unpacking error killed every assessment and the run still printed
                # "No models skipped".
                results.append((m["model"], 0, f"error:collector crash: {type(e).__name__}: {e}"))
                print(f"  [{prov}] {m['model']}: CRASHED — {type(e).__name__}: {e}", flush=True)
                if prog: prog.finish(m["model"])
            finally:
                q.task_done()
    ts = [threading.Thread(target=worker, daemon=True) for _ in range(max(1,concurrency))]
    for t in ts: t.start()
    for t in ts: t.join()
    if lane_results is not None: lane_results.extend(results)
    print(f"LANE DONE: {prov}", flush=True)

def run_parallel(models_csv, n, out_dir, batch, concurrency, min_gap, only=None,
                 item_workers=1, progress_every=60, assess_workers=1, deadline_s=1200):
    lanes = load_live(models_csv, only)
    if not lanes: sys.exit("no live lanes matched")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    print(f"START {len(lanes)} lanes @ n={n} assessments ({n*N_ITEMS} calls/model), "
          f"concurrency={concurrency}, min-gap={min_gap}s, batch={batch}", flush=True)
    stop = threading.Event()
    prog = Progress(n, sum(len(ms) for ms in lanes.values()))
    hb_stop = threading.Event()
    hb = threading.Thread(target=progress_printer, args=(prog, progress_every, hb_stop), daemon=True)
    hb.start()
    results = []; threads = []
    for prov, models in lanes.items():
        t = threading.Thread(target=run_lane, args=(prov, models, n, out_dir, batch, concurrency,
                                                    min_gap, stop, results, item_workers,
                                                    prog, assess_workers, deadline_s), daemon=True)
        t.start(); threads.append(t)
    try:
        for t in threads: t.join()
    except KeyboardInterrupt:
        stop.set(); print("STOPPING (data already flushed per assessment)", flush=True)
    finally:
        hb_stop.set()
    print(prog.snapshot(), flush=True)
    skipped = [(name, st) for (name, got, st) in results if st.startswith("error")]
    print("ALL LANES COMPLETE", flush=True)
    if skipped:
        print("\n=== SKIPPED (errored — NOT collected, NOT swapped) ===", flush=True)
        for name, st in skipped: print(f"  {name}: {st}", flush=True)
    else:
        print("No models skipped — all attempted models collected cleanly.", flush=True)
    return results

def generate(model_name, api_model, provider, n, out_csv, meta,
             dry_run=False, batch="cat_collect_2026", item_workers=1, deadline_s=1200):
    key = os.environ.get(PROVIDERS[provider][1])
    if not key: sys.exit(f"Missing env key {PROVIDERS[provider][1]} for provider {provider}")
    made = 0
    while made < n:
        row = run_assessment(model_name, api_model, provider, meta, batch,
                             key, item_workers=item_workers, deadline_s=deadline_s)
        made += 1
        if dry_run:
            print(json.dumps({k: row[k] for k in (
                "record_id","model_name","api_model_returned","provider","prompt_version",
                "temperature","assessment_start_utc","assessment_duration_ms")}, ensure_ascii=False, indent=2))
            raws = json.loads(row["raw_responses"]); rsn = json.loads(row["reasoning"])
            for i in range(N_ITEMS):
                print(f"  item {i}: {row[f'cue_{i}_left']} / {row[f'cue_{i}_right']} -> "
                      f"{row[f'word_{i}'] or '(FAILED)'}   raw={raws[i][:40]!r}"
                      f"{'  reasoning=' + str(len(rsn[i])) + ' chars' if rsn[i] else ''}")
            return [row]
        write_assessment(out_csv, row)
    print(f"[{provider}/{api_model}] wrote {made} assessments ({made*N_ITEMS} calls) -> {out_csv}")

def main():
    ap = argparse.ArgumentParser(description="Collect machine CAT responses, one API call per word pair.")
    ap.add_argument("--model"); ap.add_argument("--api-model"); ap.add_argument("--provider", choices=list(PROVIDERS))
    ap.add_argument("--n", type=int, default=100,
                    help="assessments per model, each = 10 API calls (locked at 100 by Dawei 2026-08-03)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--vendor", default="", help="vendor label; defaults to the lane name")
    ap.add_argument("--batch", default="cat_collect_2026"); ap.add_argument("--out-dir", default=str(HERE/"raw"))
    ap.add_argument("--parallel", action="store_true")
    ap.add_argument("--concurrency", type=int, default=1,
                    help="models in flight PER LANE (default 1). Lanes always run in parallel; "
                         "within one provider we go one model, one assessment, one call at a time "
                         "so latency measures the model instead of our own queue (Dawei 2026-08-04).")
    ap.add_argument("--no-stream", action="store_true",
                    help="disable streaming (default on: it puts a real clock on the per-word cap "
                         "and hanging up at the cap stops the provider generating)")
    ap.add_argument("--min-gap", type=float, default=0.5)
    ap.add_argument("--item-concurrency", type=int, default=1,
                    help="calls in flight WITHIN one assessment; timing only, data identical")
    ap.add_argument("--progress-every", type=float, default=60, help="heartbeat seconds")
    ap.add_argument("--assessment-concurrency", type=int, default=1,
                    help="assessments in flight per model")
    ap.add_argument("--call-timeout", type=float, default=CALL_TIMEOUT_S,
                    help="hard cap on ONE WORD in seconds (default 300), retries included. A word "
                         "that hits it is left blank and never retried; a model that keeps hitting "
                         "it is dropped from the lineup.")
    ap.add_argument("--assessment-timeout", type=float, default=0,
                    help="seconds before an assessment is written with whatever came back")
    ap.add_argument("--only")
    ap.add_argument("--models", default=str(HERE/"models.csv"))
    a = ap.parse_args()
    globals()["CALL_TIMEOUT_S"] = a.call_timeout
    globals()["STREAM"] = not a.no_stream
    if not a.assessment_timeout:
        # Derived, not guessed: serial items at a 300s cap need 10 x 300s, and a fixed 600s default
        # would have blanked items 3-10 of every serial assessment.
        a.assessment_timeout = N_ITEMS * a.call_timeout / max(1, a.item_concurrency) + 60
        print(f"assessment deadline derived from the per-word cap: {a.assessment_timeout:.0f}s "
              f"({N_ITEMS} words / {a.item_concurrency} in flight x {a.call_timeout:.0f}s + 60)",
              flush=True)
    acquire_lock(a.out_dir)

    # Stop cleanly on Ctrl-C or SIGTERM so the lockfile is released and the next run can resume.
    # Without this a killed collector left its lock behind with a fresh heartbeat and blocked every
    # restart for five minutes — hit twice while chunking the 2026-08-04 wave-2 run.
    def _stop(sig, _frame):
        # os._exit, not sys.exit. concurrent.futures registers an atexit hook that JOINS its worker
        # threads, so a normal exit waits for every in-flight call — up to the full 300s per-word
        # cap — and Ctrl-C looks like a hang. Release the lock by hand and leave immediately;
        # unfinished assessments are simply not written and the next run re-collects them.
        lock = Path(a.out_dir) / ".collector.lock"
        try: lock.unlink()
        except OSError: pass
        print(f"\nstopping on signal {sig}. Lock released; rerun the same command to resume from "
              f"the CSVs.", flush=True)
        sys.stdout.flush()
        os._exit(130)
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    if a.parallel:
        run_parallel(a.models, a.n, a.out_dir, a.batch, a.concurrency, a.min_gap,
                     only=set(a.only.split(",")) if a.only else None,
                     item_workers=a.item_concurrency, progress_every=a.progress_every,
                     assess_workers=a.assessment_concurrency, deadline_s=a.assessment_timeout); return
    if not (a.model and a.provider): sys.exit("need --model and --provider (or --parallel)")
    out = Path(a.out_dir)/f"topup_{a.provider}.csv"
    generate(a.model, a.api_model or a.model, a.provider, a.n, out,
             {"vendor": a.vendor or a.provider},
             dry_run=a.dry_run, batch=a.batch,
             item_workers=a.item_concurrency, deadline_s=a.assessment_timeout)

if __name__ == "__main__":
    main()
