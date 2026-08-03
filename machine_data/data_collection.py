"""
data_collection.py — collect machine CAT (Convergent Association Task) responses with full
open-science provenance.

Adapted from dtzx00/creativity_networks machine_data/data_collection.py (the DAT collector).
Provider adapters, temperature policy, reasoning capture, parallel lanes, resumability and
skip-and-flag behaviour are carried over unchanged so machine CAT and machine DAT are
collected under identical conditions.

DELIVERY: ONE API CALL PER WORD PAIR (locked 2026-08-03, Dawei)
  1 assessment = 1 fetch of 10 cue pairs from Rugu + 10 independent model calls + 1 CSV row.
  Each call carries the instructions and exactly one pair, in a fresh context, so no pair can
  prime another. This matches the human form, where pairs are presented one at a time.
  Note the one real divergence: a human accumulates memory across the 10 items and may revise
  earlier answers with the Previous button; independent calls cannot.

OUTPUT: TWO FILES per provider lane, joined on record_id
  raw/topup_<lane>.csv        wide, analysis-ready: one row per assessment, 76 columns —
                              26 assessment/model/API columns + 5 per item
                              (cue left, cue right, word, request ts, response ts) x 10.
  raw/items_topup_<lane>.csv  long, full provenance: one row per CALL (10 per assessment) with
                              verbatim response text, reasoning trace, per-call token counts,
                              response ids, fingerprints, retries and the prompt hash.
  The bulky text lives in the long file so the wide file stays readable in a spreadsheet.

ITEMS ARE DRAWN FRESH PER ASSESSMENT from GET /api/cat/?language=en, which returns a random
sample of the item pool — mirroring the per-participant randomisation. The drawn pairs are
stored in both files, so every row is self-describing.

NO SCORING HERE. cat_score stays blank. Scoring is a separate later pass using the audited
proximity-only scorer; the platform's own scorer is not used (it blends an uninformative
uniqueness term and redraws an unseeded random baseline per request, so it is not reproducible).

Keys are read from env at runtime; never hard-coded, never written to disk.

Usage:
  python data_collection.py --model "GPT-4o" --api-model gpt-4o-2024-08-06 --provider openai --n 1 --dry-run
  python data_collection.py --parallel --models machine_data/models.csv --n 500
"""
import argparse, csv, hashlib, json, os, re, subprocess, sys, time, threading, queue
import urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
N_ITEMS = 10

# --- item source ---------------------------------------------------------------------------
ITEMS_BASE = os.environ.get("RUGU_API_BASE", "https://api-v2.rugu.io")
ITEMS_PATH = "/api/cat/"

# --- prompt --------------------------------------------------------------------------------
# VERBATIM participant-facing instruction text, reassembled from the CAT frontend component
# (Module-Federation apps/cat/src/translations/en.json, branch dev--test-environment).
# The rules are the instrument and are not paraphrased. Two mechanical edits only, both forced
# by single-item delivery: "each of the 10 word pairs" -> "the following word pair", and the
# output instruction asks for one word instead of a comma-separated list of ten.
# ENGLISH ONLY (locked 2026-08-01, Dawei): the zh-Hans arm is not collected.
ITEM_PROMPT_TEMPLATE = (
    "Convergent Association Task\n\n"
    "Please enter a word that is as similar as possible, in all meanings and uses to the "
    "following word pair.\n\n"
    "Detailed Rules\n"
    "- A - B: Try to be close to both words, not just one.\n"
    "- Apple: Only single, lowercase words in English\n"
    "- Disneyland: No proper nouns (e.g. no specific people or places)\n"
    "- GPA: No specialized vocabulary or technical terms\n"
    "- Computer: Do not rely on objects in your surroundings\n\n"
    "{left} / {right}\n\n"
    "Return only that single word. Do not return anything else."
)
PROMPT_TEMPLATE_SHA256 = hashlib.sha256(ITEM_PROMPT_TEMPLATE.encode()).hexdigest()

def build_item_prompt(left, right):
    return ITEM_PROMPT_TEMPLATE.format(left=left, right=right)

PROVIDER_TEMP_RANGE = {
    "openai": (0, 2), "xai": (0, 2), "deepseek": (0, 2), "qwen": (0, 2), "hunyuan": (0, 2),
    "anthropic": (0, 1), "moonshot": (0, 1), "openrouter": (0, 2),
}
def provider_midpoint(provider):
    lo, hi = PROVIDER_TEMP_RANGE.get(provider, (0, 2))
    return (lo + hi) / 2
def temp_range_str(provider):
    lo, hi = PROVIDER_TEMP_RANGE.get(provider, (0, 2))
    return f"{lo}-{hi}"

# --- schema --------------------------------------------------------------------------------
# 26 assessment-level columns + 5 per item x 10 items = 76 columns.
# Model metadata that lives in models.csv (region, intelligence class, release date) is NOT
# duplicated here; models.csv is the single registry and joins on model_name.
META_FIELDS = [
    "record_id", "model_name", "api_model_requested", "api_model_returned",
    "provider", "vendor", "endpoint_base", "batch", "language",
    "temperature_requested", "temperature_effective", "max_tokens", "seed_base",
    "items_source", "items_fetch_timestamp_utc",
    "assessment_start_utc", "assessment_end_utc", "assessment_duration_ms",
    "n_calls_ok", "n_words_parsed", "parse_status",
    "prompt_tokens_total", "completion_tokens_total", "total_tokens_total",
    "prompt_template_sha256", "cat_score", "collector_version",
]
ITEM_FIELDS = []
for _i in range(N_ITEMS):
    ITEM_FIELDS += [f"cue_{_i}_left", f"cue_{_i}_right", f"word_{_i}",
                    f"item_{_i}_request_utc", f"item_{_i}_response_utc"]
FIELDS = META_FIELDS + ITEM_FIELDS

# one row per CALL — verbatim text, reasoning, and per-call API provenance
LONG_FIELDS = [
    "record_id", "model_name", "api_model_requested", "api_model_returned", "provider",
    "batch", "language", "item_index", "cue_left", "cue_right",
    "request_timestamp_utc", "response_timestamp_utc", "latency_ms",
    "temperature_requested", "temperature_effective", "seed",
    "api_request_id", "response_id", "system_fingerprint", "finish_reason",
    "prompt_tokens", "completion_tokens", "total_tokens",
    "prompt_template_sha256", "prompt_sha256",
    "raw_response_text", "reasoning_text", "word", "parse_status",
    "http_retries", "error", "collector_version",
]

def _collector_version():
    try:
        return "git:" + subprocess.check_output(["git","-C",str(HERE),"rev-parse","--short","HEAD"],text=True).strip()
    except Exception:
        return "git:unknown"
COLLECTOR_VERSION = _collector_version()

def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

def _record_id(model_name, batch, started):
    h = hashlib.sha256(f"{model_name}|{batch}|{started}".encode()).hexdigest()[:12]
    return f"cat_{h}"

# ---- item fetch --------------------------------------------------------------------------
_UA = {"User-Agent": "Mozilla/5.0 (compatible; cat-collector)", "Accept": "application/json"}

def fetch_items(language="en", retries=6, timeout=30):
    """Fetch one fresh random draw of cue pairs. The endpoint 502s intermittently, so retry."""
    url = f"{ITEMS_BASE}{ITEMS_PATH}?language={urllib.parse.quote(language)}"
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=timeout) as r:
                d = json.loads(r.read())
            pairs = [(str(p[0]), str(p[1])) for p in (d.get("data") or []) if len(p) >= 2]
            if len(pairs) == N_ITEMS:
                return pairs, _now()
            last = f"expected {N_ITEMS} pairs, got {len(pairs)}"
        except Exception as e:
            last = str(e)[:120]
        time.sleep(min(1.5 * (attempt + 1), 8))
    raise RuntimeError(f"item fetch failed after {retries} tries: {last}")

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

def _post_full(url, headers, body, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read()), dict(r.headers)

MAX_TOKENS_ANTHROPIC = 4000

# ---- provider adapters ---------------------------------------------------------------------
def _openai_like(base, key, api_model, prompt, temperature, seed=None, extra_headers=None):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if extra_headers: headers.update(extra_headers)
    body = {"model": api_model, "messages": [{"role":"user","content":prompt}], "temperature": temperature}
    if seed is not None: body["seed"] = seed
    d, h = _post_full(f"{base}/chat/completions", headers, body)
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

def _anthropic(base, key, api_model, prompt, temperature, seed=None):
    headers = {"x-api-key": key, "anthropic-version":"2023-06-01", "Content-Type":"application/json"}
    body = {"model": api_model, "max_tokens":MAX_TOKENS_ANTHROPIC, "temperature":temperature,
            "messages":[{"role":"user","content":prompt}]}
    d, h = _post_full(f"{base}/messages", headers, body)
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

PROVIDERS = {
    "openai":    (lambda k,m,p,t,s: _openai_like("https://api.openai.com/v1", k, m, p, t, s), "OPENAI_API_KEY", True),
    "anthropic": (lambda k,m,p,t,s: _anthropic("https://api.anthropic.com/v1", k, m, p, t, s), "ANTHROPIC_API_KEY", False),
    "xai":       (lambda k,m,p,t,s: _openai_like("https://api.x.ai/v1", k, m, p, t, None), "XAI_API_KEY", False),
    "deepseek":  (lambda k,m,p,t,s: _openai_like("https://api.deepseek.com/v1", k, m, p, t, s), "DEEPSEEK_API_KEY", True),
    "qwen":      (lambda k,m,p,t,s: _openai_like("https://dashscope.aliyuncs.com/compatible-mode/v1", k, m, p, t, s), "QWEN_API_KEY", True),
    "hunyuan":   (lambda k,m,p,t,s: _openai_like("https://tokenhub.tencentmaas.com/v1", k, m, p, t, None), "HUNYUAN_API_KEY", False),
    "moonshot":  (lambda k,m,p,t,s: _openai_like("https://api.moonshot.ai/v1", k, m, p, t, None), "MOONSHOT_API_KEY", False),
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

def parse_word(text):
    """Extract exactly one single-word answer, or fail loudly.

    Models are told to return only the word, but some prepend their working
    ("bowl / salary - both can be earned -> **prize**"). Scan lines from the BOTTOM and accept
    the first line that reduces to one valid word; strip markdown, list markers, a leading
    "answer:"-style label, and surrounding punctuation. If nothing reduces cleanly, store no
    word and mark the call failed. Never guess which token was meant.
    """
    for line in reversed([l for l in (text or "").splitlines() if l.strip()]):
        s = re.sub(r"[*_`\"]", "", line)
        s = re.sub(r"^\s*(?:\d+[.)]|[-•])\s*", "", s)
        s = re.sub(r"^\s*(?:answer|word|response)\s*[:\-]\s*", "", s, flags=re.IGNORECASE)
        s = s.strip().strip(".,;:!?").strip().lower()
        if WORD_RE.match(s):
            return s, "ok"
    return "", "failed"

def call_once(provider, key, api_model, prompt, target_temp, seed):
    fn = PROVIDERS[provider][0]
    try:
        return fn(key, api_model, prompt, target_temp, seed if PROVIDERS[provider][2] else None), target_temp
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode()
        except Exception: pass
        if e.code == 400 and "temperature" in body.lower():
            return fn(key, api_model, prompt, 1.0, None), 1.0
        raise RuntimeError(f"HTTP {e.code}: {body[:200]}")

TRANSIENT_BITS = ("429", "timed out", "timeout", "temporarily", "connection", "reset",
                  " 500", " 502", " 503", " 504", " 520", " 521", " 522", " 524")
def _is_transient(msg):
    m = msg.lower()
    return any(b.strip() in m for b in TRANSIENT_BITS)

def call_item(provider, key, api_model, prompt, target_temp, seed, max_retries=6):
    """One call for one cue pair, with bounded retry on transient failures.
    Returns (payload|None, temp_used, retries, error_str)."""
    retries = 0
    while True:
        try:
            payload, temp_used = call_once(provider, key, api_model, prompt, target_temp, seed)
            return payload, temp_used, retries, ""
        except Exception as e:
            msg = str(e)
            if _is_transient(msg) and retries < max_retries:
                retries += 1
                time.sleep(min(2.0 * retries, 15))
                continue
            return None, target_temp, retries, msg[:200]

ENDPOINTS = {
    "openai": "https://api.openai.com/v1", "anthropic": "https://api.anthropic.com/v1",
    "xai": "https://api.x.ai/v1", "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "hunyuan": "https://tokenhub.tencentmaas.com/v1", "moonshot": "https://api.moonshot.ai/v1",
}

# ---- one assessment = 10 calls --------------------------------------------------------------
def run_assessment(model_name, api_model, prov, meta, language, seed_base, batch, key,
                   pairs=None, fetched_at=None):
    """Fetch 10 pairs (unless supplied), call the model once per pair, and return
    (wide_row, [10 long rows]). A failed item leaves its word blank and is flagged; the other
    nine are still valid data, so the assessment is kept and marked partial."""
    if pairs is None:
        pairs, fetched_at = fetch_items(language)
    target_temp = provider_midpoint(prov)
    started = _now(); t_start = time.time()
    record_id = _record_id(model_name, batch, started)

    long_rows, words, item_ts = [], [], []
    api_model_returned = ""; temp_effective = ""; max_tokens = ""
    ptok = ctok = ttok = 0; n_ok = 0

    for i, (left, right) in enumerate(pairs):
        prompt = build_item_prompt(left, right)
        seed = seed_base * 100 + i
        req_ts = _now(); t0 = time.time()
        payload, temp_used, retries, err = call_item(prov, key, api_model, prompt, target_temp, seed)
        resp_ts = _now(); latency = int((time.time() - t0) * 1000)

        if payload is None:
            word, status, raw, reasoning = "", "failed", "", ""
        else:
            word, status = parse_word(payload["text"])
            raw, reasoning = payload["text"], payload.get("reasoning_text", "")
            api_model_returned = api_model_returned or payload.get("api_model_returned", "")
            temp_effective = temp_used
            max_tokens = payload.get("max_tokens", "") or max_tokens
            for k, acc in (("prompt_tokens", "p"), ("completion_tokens", "c"), ("total_tokens", "t")):
                v = payload.get(k) or 0
                try: v = int(v)
                except Exception: v = 0
                if acc == "p": ptok += v
                elif acc == "c": ctok += v
                else: ttok += v
            if status == "ok": n_ok += 1

        words.append(word); item_ts.append((req_ts, resp_ts))
        long_rows.append({
            "record_id": record_id, "model_name": model_name, "api_model_requested": api_model,
            "api_model_returned": (payload or {}).get("api_model_returned", ""), "provider": prov,
            "batch": batch, "language": language, "item_index": i,
            "cue_left": left, "cue_right": right,
            "request_timestamp_utc": req_ts, "response_timestamp_utc": resp_ts, "latency_ms": latency,
            "temperature_requested": target_temp, "temperature_effective": temp_used,
            "seed": seed if PROVIDERS[prov][2] else "",
            "api_request_id": (payload or {}).get("api_request_id", ""),
            "response_id": (payload or {}).get("response_id", ""),
            "system_fingerprint": (payload or {}).get("system_fingerprint", ""),
            "finish_reason": (payload or {}).get("finish_reason", ""),
            "prompt_tokens": (payload or {}).get("prompt_tokens", ""),
            "completion_tokens": (payload or {}).get("completion_tokens", ""),
            "total_tokens": (payload or {}).get("total_tokens", ""),
            "prompt_template_sha256": PROMPT_TEMPLATE_SHA256,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "raw_response_text": raw, "reasoning_text": reasoning, "word": word,
            "parse_status": status, "http_retries": retries, "error": err,
            "collector_version": COLLECTOR_VERSION,
        })

    ended = _now()
    n_words = sum(1 for w in words if w)
    parse_status = "ok" if n_words == N_ITEMS else ("failed" if n_words == 0 else "partial")
    row = {
        "record_id": record_id, "model_name": model_name, "api_model_requested": api_model,
        "api_model_returned": api_model_returned, "provider": prov, "vendor": meta.get("vendor", ""),
        "endpoint_base": ENDPOINTS.get(prov, ""), "batch": batch, "language": language,
        "temperature_requested": target_temp, "temperature_effective": temp_effective,
        "max_tokens": max_tokens, "seed_base": seed_base if PROVIDERS[prov][2] else "",
        "items_source": f"{ITEMS_BASE}{ITEMS_PATH}?language={language}",
        "items_fetch_timestamp_utc": fetched_at,
        "assessment_start_utc": started, "assessment_end_utc": ended,
        "assessment_duration_ms": int((time.time() - t_start) * 1000),
        "n_calls_ok": n_ok, "n_words_parsed": n_words, "parse_status": parse_status,
        "prompt_tokens_total": ptok, "completion_tokens_total": ctok, "total_tokens_total": ttok,
        "prompt_template_sha256": PROMPT_TEMPLATE_SHA256,
        "cat_score": "", "collector_version": COLLECTOR_VERSION,
    }
    for i in range(N_ITEMS):
        row[f"cue_{i}_left"]  = pairs[i][0] if i < len(pairs) else ""
        row[f"cue_{i}_right"] = pairs[i][1] if i < len(pairs) else ""
        row[f"word_{i}"]      = words[i] if i < len(words) else ""
        row[f"item_{i}_request_utc"]  = item_ts[i][0] if i < len(item_ts) else ""
        row[f"item_{i}_response_utc"] = item_ts[i][1] if i < len(item_ts) else ""
    return row, long_rows


# ---- io -------------------------------------------------------------------------------------
def _append(path, fields, rows):
    if not rows: return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists: w.writeheader()
        w.writerows(rows)

def write_assessment(out_csv, long_csv, row, long_rows):
    _append(out_csv, FIELDS, [row])
    _append(long_csv, LONG_FIELDS, long_rows)

def existing_count(out_csv, model_name):
    if not out_csv.exists(): return 0
    with open(out_csv) as f:
        return sum(1 for r in csv.DictReader(f) if r["model_name"] == model_name)

_write_locks = {}
_wl_guard = threading.Lock()
def write_lock(path):
    with _wl_guard:
        if path not in _write_locks: _write_locks[path] = threading.Lock()
        return _write_locks[path]

def load_live(models_csv, only=None):
    """Group models by resolved API lane. Models with no known lane are reported, never dropped
    silently — a missing endpoint must be fixed, not skipped."""
    lanes, unrouted = {}, []
    for r in csv.DictReader(open(models_csv)):
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

class LaunchGate:
    def __init__(self, min_gap):
        self.min_gap = min_gap; self.lock = threading.Lock(); self.last = 0.0
    def wait(self):
        with self.lock:
            now = time.time(); delta = now - self.last
            if delta < self.min_gap: time.sleep(self.min_gap - delta)
            self.last = time.time()

def collect_one(model_row, n, out_csv, long_csv, batch, gate, key, stop, language="en"):
    prov = resolve_lane(model_row); name = model_row["model"]
    api = model_row.get("api_model_id") or model_row["model"]
    meta = {"vendor": model_row.get("provider","")}
    have = existing_count(out_csv, name); made = have
    lk = write_lock(str(out_csv))
    dead = 0
    while made < n and not stop.is_set():
        try:
            pairs, fetched_at = fetch_items(language)
        except RuntimeError as e:
            print(f"FAIL {name} ({prov}): item fetch — {str(e)[:80]}", flush=True)
            return name, made-have, f"error:items:{str(e)[:50]}"
        gate.wait()
        row, long_rows = run_assessment(name, api, prov, meta, language, 1000 + made, batch, key,
                                        pairs=pairs, fetched_at=fetched_at)
        with lk: write_assessment(out_csv, long_csv, row, long_rows)
        made += 1
        if row["n_calls_ok"] == 0:
            dead += 1
            if dead >= 3:
                err = next((r["error"] for r in long_rows if r["error"]), "all calls failed")
                print(f"FAIL {name} ({prov}): {err[:90]}", flush=True)
                return name, made-have, f"error:{err[:60]}"
        else:
            dead = 0
    return name, made-have, "done"

def run_lane(prov, models, n, out_dir, batch, concurrency, min_gap, stop, language, lane_results=None):
    key = os.environ.get(PROVIDERS[prov][1])
    if not key:
        print(f"LANE {prov}: MISSING KEY {PROVIDERS[prov][1]} — skipped", flush=True); return
    out_csv = Path(out_dir)/f"topup_{prov}.csv"
    long_csv = Path(out_dir)/f"items_topup_{prov}.csv"
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
                name, got, st = collect_one(m, n, out_csv, long_csv, batch, gate, key, stop, language)
                results.append((name, got, st))
                print(f"  [{prov}] {name}: +{got} ({st})", flush=True)
            finally:
                q.task_done()
    ts = [threading.Thread(target=worker, daemon=True) for _ in range(max(1,concurrency))]
    for t in ts: t.start()
    for t in ts: t.join()
    if lane_results is not None: lane_results.extend(results)
    print(f"LANE DONE: {prov}", flush=True)

def run_parallel(models_csv, n, out_dir, batch, concurrency, min_gap, language, only=None):
    lanes = load_live(models_csv, only)
    if not lanes: sys.exit("no live lanes matched")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    print(f"START {len(lanes)} lanes @ n={n} assessments ({n*N_ITEMS} calls/model), "
          f"concurrency={concurrency}, min-gap={min_gap}s, batch={batch}", flush=True)
    stop = threading.Event()
    results = []; threads = []
    for prov, models in lanes.items():
        t = threading.Thread(target=run_lane, args=(prov, models, n, out_dir, batch, concurrency,
                                                    min_gap, stop, language, results), daemon=True)
        t.start(); threads.append(t)
    try:
        for t in threads: t.join()
    except KeyboardInterrupt:
        stop.set(); print("STOPPING (data already flushed per assessment)", flush=True)
    skipped = [(name, st) for (name, got, st) in results if st.startswith("error")]
    print("ALL LANES COMPLETE", flush=True)
    if skipped:
        print("\n=== SKIPPED (errored — NOT collected, NOT swapped) ===", flush=True)
        for name, st in skipped: print(f"  {name}: {st}", flush=True)
    else:
        print("No models skipped — all attempted models collected cleanly.", flush=True)
    return results

def generate(model_name, api_model, provider, n, out_csv, long_csv, meta, language="en",
             dry_run=False, batch="cat_collect_2026", pace=0.1):
    key = os.environ.get(PROVIDERS[provider][1])
    if not key: sys.exit(f"Missing env key {PROVIDERS[provider][1]} for provider {provider}")
    made = 0
    while made < n:
        row, long_rows = run_assessment(model_name, api_model, provider, meta, language,
                                        1000 + made, batch, key)
        made += 1
        if dry_run:
            print(json.dumps({k: row[k] for k in (
                "record_id","model_name","api_model_returned","provider","temperature_effective",
                "n_calls_ok","n_words_parsed","parse_status","total_tokens_total",
                "assessment_duration_ms")}, ensure_ascii=False, indent=2))
            for lr in long_rows:
                print(f"  item {lr['item_index']}: {lr['cue_left']} / {lr['cue_right']} -> "
                      f"{lr['word'] or '(FAILED)'}  [{lr['latency_ms']}ms, {lr['total_tokens']} tok]"
                      f"{' ERR ' + lr['error'][:60] if lr['error'] else ''}")
            return [row]
        write_assessment(out_csv, long_csv, row, long_rows)
        time.sleep(pace)
    print(f"[{provider}/{api_model}] wrote {made} assessments ({made*N_ITEMS} calls) -> {out_csv}")

def main():
    ap = argparse.ArgumentParser(description="Collect machine CAT responses, one API call per word pair.")
    ap.add_argument("--model"); ap.add_argument("--api-model"); ap.add_argument("--provider", choices=list(PROVIDERS))
    ap.add_argument("--n", type=int, default=5, help="assessments per model (each = 10 API calls)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--language", default="en", help="en only; the Chinese arms are not collected")
    ap.add_argument("--vendor", default="", help="vendor label; defaults to the lane name")
    ap.add_argument("--batch", default="cat_collect_2026"); ap.add_argument("--out-dir", default=str(HERE/"raw"))
    ap.add_argument("--parallel", action="store_true")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--min-gap", type=float, default=0.5)
    ap.add_argument("--only")
    ap.add_argument("--models", default=str(HERE/"models.csv"))
    a = ap.parse_args()
    if a.parallel:
        run_parallel(a.models, a.n, a.out_dir, a.batch, a.concurrency, a.min_gap, a.language,
                     only=set(a.only.split(",")) if a.only else None); return
    if not (a.model and a.provider): sys.exit("need --model and --provider (or --parallel)")
    out = Path(a.out_dir)/f"topup_{a.provider}.csv"
    long_out = Path(a.out_dir)/f"items_topup_{a.provider}.csv"
    generate(a.model, a.api_model or a.model, a.provider, a.n, out, long_out,
             {"vendor": a.vendor or a.provider},
             language=a.language, dry_run=a.dry_run, batch=a.batch)

if __name__ == "__main__":
    main()
