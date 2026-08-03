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

OUTPUT: ONE file per provider lane, raw/topup_<lane>.csv — one row per assessment, 65 columns:
  15 assessment/model/API columns + 5 per item (cue left, cue right, word, request timestamp,
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
import argparse, csv, hashlib, json, os, random, re, subprocess, sys, time, threading, queue
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
    return q, _now()

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
    "openai": (0, 2), "xai": (0, 2), "deepseek": (0, 2), "qwen": (0, 2), "hunyuan": (0, 2),
    "anthropic": (0, 1), "moonshot": (0, 1), "openrouter": (0, 2),
}
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
# Deliberately absent: endpoint_base (1:1 with provider, mapped in code), language (constant en),
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


# ---- one assessment = 10 calls --------------------------------------------------------------
def run_assessment(model_name, api_model, prov, meta, language, seed_base, batch, key,
                   pairs=None, fetched_at=None):
    """Fetch 10 pairs (unless supplied), call the model once per pair, return one row.

    A failed call leaves its word blank and records "[ERROR: ...]" in raw_responses for that
    item. The other nine are still valid data, so the assessment is always kept.
    """
    if pairs is None:
        pairs, fetched_at = draw_items()
    target_temp = provider_midpoint(prov)
    started = _now(); t_start = time.time()
    record_id = _record_id(model_name, batch, started)

    words, item_ts, raws, reasonings = [], [], [], []
    api_model_returned = ""; temp_effective = ""; max_tokens = ""

    for i, (left, right) in enumerate(pairs):
        prompt = build_item_prompt(left, right)
        seed = seed_base * 100 + i
        req_ts = _now()
        payload, temp_used, retries, err = call_item(prov, key, api_model, prompt, target_temp, seed)
        resp_ts = _now()

        if payload is None:
            words.append(""); raws.append(f"[ERROR: {err}]"); reasonings.append("")
        else:
            word, _status = parse_word(payload["text"])
            words.append(word)
            raws.append(payload["text"])
            reasonings.append(payload.get("reasoning_text", ""))
            api_model_returned = api_model_returned or payload.get("api_model_returned", "")
            temp_effective = temp_used
            max_tokens = payload.get("max_tokens", "") or max_tokens
        item_ts.append((req_ts, resp_ts))

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
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not exists: w.writeheader()
        w.writerows(rows)

def write_assessment(out_csv, row):
    _append(out_csv, FIELDS, [row])

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

def collect_one(model_row, n, out_csv, batch, gate, key, stop, language="en"):
    prov = resolve_lane(model_row); name = model_row["model"]
    api = model_row.get("api_model_id") or model_row["model"]
    meta = {"vendor": model_row.get("provider","")}
    have = existing_count(out_csv, name); made = have
    lk = write_lock(str(out_csv))
    dead = 0
    while made < n and not stop.is_set():
        pairs, fetched_at = draw_items()
        gate.wait()
        row = run_assessment(name, api, prov, meta, language, 1000 + made, batch, key,
                             pairs=pairs, fetched_at=fetched_at)
        with lk: write_assessment(out_csv, row)
        made += 1
        if not any(row[f"word_{i}"] for i in range(N_ITEMS)):
            dead += 1
            if dead >= 3:
                errs = json.loads(row["raw_responses"])
                err = next((e for e in errs if e.startswith("[ERROR")), "all calls failed")
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
                name, got, st = collect_one(m, n, out_csv, batch, gate, key, stop, language)
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

def generate(model_name, api_model, provider, n, out_csv, meta, language="en",
             dry_run=False, batch="cat_collect_2026", pace=0.1):
    key = os.environ.get(PROVIDERS[provider][1])
    if not key: sys.exit(f"Missing env key {PROVIDERS[provider][1]} for provider {provider}")
    made = 0
    while made < n:
        row = run_assessment(model_name, api_model, provider, meta, language, 1000 + made, batch, key)
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
    generate(a.model, a.api_model or a.model, a.provider, a.n, out,
             {"vendor": a.vendor or a.provider},
             language=a.language, dry_run=a.dry_run, batch=a.batch)

if __name__ == "__main__":
    main()
