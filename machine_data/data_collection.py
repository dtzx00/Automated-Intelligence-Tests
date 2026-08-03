"""
data_collection.py — collect machine CAT (Convergent Association Task) responses with full
open-science provenance.

Adapted from dtzx00/creativity_networks machine_data/data_collection.py (the DAT collector).
Provider adapters, temperature policy, reasoning capture, parallel lanes, resumability and
skip-and-flag behaviour are carried over unchanged so machine CAT and machine DAT are
collected under identical conditions.

WHAT IS DIFFERENT FROM THE DAT COLLECTOR
1. ITEMS ARE DRAWN FRESH PER ASSESSMENT. Every assessment fetches its own 10 cue pairs from
   the live Rugu endpoint (GET /api/cat/?language=xx), which returns a random sample from the
   item pool. This mirrors the human procedure, where cue pairs were randomised per
   participant. The drawn pairs are stored with the response, so every row is self-describing.
2. NO SCORING HERE. cat_score stays blank. Scoring is a separate later pass using the audited
   proximity-only scorer; the platform's own scorer is not used (it blends an uninformative
   uniqueness term and redraws an unseeded random baseline per request, so it is not
   reproducible).

Keys are read from env at runtime; never hard-coded, never written to disk.

Usage:
  python data_collection.py --model "GPT-4o" --api-model gpt-4o-2024-08-06 --provider openai --n 1 --dry-run
  python data_collection.py --parallel --models machine_data/models.csv --n 500
"""
import argparse, csv, hashlib, json, os, re as _re, subprocess, sys, time, threading, queue
import re
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
# The rules are the instrument and are not paraphrased. Only the delivery mechanics differ:
# a human sees one pair at a time in a form, a model receives all ten and answers in one string.
# ENGLISH ONLY (locked 2026-08-01, Dawei): the zh-Hans arm is not collected.
PROMPT_TEMPLATE = (
    "Convergent Association Task\n\n"
    "Please enter a word that is as similar as possible, in all meanings and uses to each of "
    "the {n} word pairs.\n\n"
    "Detailed Rules\n"
    "- A - B: Try to be close to both words, not just one.\n"
    "- Apple: Only single, lowercase words in English\n"
    "- Disneyland: No proper nouns (e.g. no specific people or places)\n"
    "- GPA: No specialized vocabulary or technical terms\n"
    "- Computer: Do not rely on objects in your surroundings\n\n"
    "{items}\n\n"
    "Return your final response as a single string with each answer separated by commas: "
    "\"answer_1, answer_2, ..., answer_{n}\". Do not return anything else."
)

def build_prompt(pairs):
    items = "\n".join(f"{i+1}. {a} / {b}" for i, (a, b) in enumerate(pairs))
    return PROMPT_TEMPLATE.format(n=len(pairs), items=items)

PROMPT_TEMPLATE_SHA256 = hashlib.sha256(PROMPT_TEMPLATE.encode()).hexdigest()

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

ITEM_COLS = []
for _i in range(N_ITEMS):
    ITEM_COLS += [f"cue_{_i}_left", f"cue_{_i}_right", f"word_{_i}"]

FIELDS = ["record_id","model_name","api_model_requested","api_model_returned","provider","vendor",
          "endpoint_base","batch","region","reasoning","model_year","language",
          "temperature_requested","temperature_effective","temp_range_used","seed",
          "items_source","items_fetch_timestamp_utc","items_json",
          "request_timestamp_utc","response_timestamp_utc","latency_ms",
          "api_request_id","response_id","system_fingerprint","finish_reason",
          "prompt_tokens","completion_tokens","total_tokens",
          "prompt_template_sha256","prompt_sha256",
          "raw_response_text","reasoning_text","parse_status","n_words_parsed"] \
         + ITEM_COLS + ["cat_score","collector_version"]

def _collector_version():
    try:
        return "git:" + subprocess.check_output(["git","-C",str(HERE),"rev-parse","--short","HEAD"],text=True).strip()
    except Exception:
        return "git:unknown"
COLLECTOR_VERSION = _collector_version()

def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

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
    m = _re.search(r"<think(?:ing)?>(.*?)</think(?:ing)?>", text, _re.DOTALL|_re.IGNORECASE)
    if not m: return "", text
    reasoning = m.group(1).strip()
    clean = _re.sub(r"<think(?:ing)?>.*?</think(?:ing)?>", "", text, flags=_re.DOTALL|_re.IGNORECASE).strip()
    return reasoning, clean

def _post_full(url, headers, body, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read()), dict(r.headers)

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
        "endpoint_base": base,
    }

def _anthropic(base, key, api_model, prompt, temperature, seed=None):
    headers = {"x-api-key": key, "anthropic-version":"2023-06-01", "Content-Type":"application/json"}
    body = {"model": api_model, "max_tokens":4000, "temperature":temperature,
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


def parse_words(text, n=N_ITEMS):
    """Extract exactly n single-word answers, or fail loudly.

    Models are told to return only a comma-separated string, but some prepend their working
    ("1. bowl / salary - both can be earned -> **prize**") even when not asked. A naive
    comma/newline split turns that preamble into fake answers, so instead: scan lines from the
    BOTTOM, take the first line that yields exactly n valid single-word tokens, and if no line
    does, mark the row failed and store no words. Never guess.
    """
    WORD = re.compile(r"^[a-z][a-z'-]{0,29}$")

    def tokens(line):
        line = re.sub(r"[*_`]", "", line)                    # markdown emphasis
        line = re.sub(r"^\s*(?:\d+[.)]|[-•])\s*", "", line)   # list markers
        parts = [t.strip().strip('."\'').lower() for t in line.split(",")]
        return [t for t in parts if t]

    lines = [l for l in (text or "").splitlines() if l.strip()]
    for line in reversed(lines):
        toks = tokens(line)
        if len(toks) == n and all(WORD.match(t) for t in toks):
            return toks, "ok"
    # last resort: the whole response as one comma-separated string
    toks = tokens(" ".join(lines))
    if len(toks) == n and all(WORD.match(t) for t in toks):
        return toks, "ok"
    return [], "failed"

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

def build_row(name, api, prov, meta, language, pairs, fetched_at, prompt, payload,
              target_temp, temp_used, seed, req_ts, resp_ts, latency, batch):
    words, status = parse_words(payload["text"])
    row = {
        "record_id":"", "model_name":name, "api_model_requested":api,
        "api_model_returned":payload.get("api_model_returned",""), "provider":prov,
        "endpoint_base":payload.get("endpoint_base",""), "batch":batch, "vendor":meta.get("vendor",""),
        "region":meta.get("region",""), "reasoning":meta.get("reasoning",""),
        "model_year":meta.get("year",""), "language":language,
        "temperature_requested":target_temp, "temperature_effective":temp_used,
        "temp_range_used":temp_range_str(prov), "seed":seed if PROVIDERS[prov][2] else "",
        "items_source":f"{ITEMS_BASE}{ITEMS_PATH}?language={language}",
        "items_fetch_timestamp_utc":fetched_at,
        "items_json":json.dumps([list(p) for p in pairs], ensure_ascii=False),
        "request_timestamp_utc":req_ts, "response_timestamp_utc":resp_ts, "latency_ms":latency,
        "api_request_id":payload.get("api_request_id",""), "response_id":payload.get("response_id",""),
        "system_fingerprint":payload.get("system_fingerprint",""), "finish_reason":payload.get("finish_reason",""),
        "prompt_tokens":payload.get("prompt_tokens",""), "completion_tokens":payload.get("completion_tokens",""),
        "total_tokens":payload.get("total_tokens",""),
        "prompt_template_sha256":PROMPT_TEMPLATE_SHA256,
        "prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest(),
        "raw_response_text":payload["text"], "reasoning_text":payload.get("reasoning_text",""),
        "parse_status":status, "n_words_parsed":len(words) if words else 0,
        "cat_score":"", "collector_version":COLLECTOR_VERSION,
    }
    for i in range(N_ITEMS):
        row[f"cue_{i}_left"]  = pairs[i][0] if i < len(pairs) else ""
        row[f"cue_{i}_right"] = pairs[i][1] if i < len(pairs) else ""
        row[f"word_{i}"]      = words[i] if words and i < len(words) else ""
    return row

def write_rows(out_csv, rows):
    if not rows: return
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    exists = out_csv.exists()
    with open(out_csv, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists: w.writeheader()
        w.writerows(rows)

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
        # models.csv may or may not carry a status column; absent means live
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
    prov = resolve_lane(model_row); name = model_row["model"]; api = model_row["api_model_id"] or model_row["model"]
    meta = {"region": model_row.get("region",""), "reasoning": model_row.get("reasoning",""),
            "year": model_row.get("year") or (model_row.get("release_date","") or "")[:4],
            "vendor": model_row.get("provider","")}
    have = existing_count(out_csv, name); made = have
    target_temp = provider_midpoint(prov)
    lk = write_lock(str(out_csv))
    consec_transient = 0
    while made < n and not stop.is_set():
        seed = 1000 + made
        try:
            pairs, fetched_at = fetch_items(language)
        except RuntimeError as e:
            print(f"FAIL {name} ({prov}): item fetch — {str(e)[:80]}", flush=True)
            return name, made-have, f"error:items:{str(e)[:50]}"
        prompt = build_prompt(pairs)
        gate.wait()
        req_ts = _now(); t0 = time.time()
        try:
            payload, temp_used = call_once(prov, key, api, prompt, target_temp, seed)
        except Exception as e:
            msg = str(e)
            transient = ("429" in msg or "timed out" in msg.lower() or "timeout" in msg.lower()
                         or "temporarily" in msg.lower() or "connection" in msg.lower()
                         or "reset" in msg.lower() or " 500" in msg or " 502" in msg or " 503" in msg
                         or " 504" in msg or " 520" in msg or " 521" in msg or " 522" in msg or " 524" in msg)
            if transient:
                consec_transient += 1
                if consec_transient <= 8:
                    time.sleep(min(2.0*consec_transient, 15)); continue
            print(f"FAIL {name} ({prov}): {msg[:80]}", flush=True)
            return name, made-have, f"error:{msg[:60]}"
        consec_transient = 0
        resp_ts = _now(); latency = int((time.time()-t0)*1000)
        row = build_row(name, api, prov, meta, language, pairs, fetched_at, prompt, payload,
                        target_temp, temp_used, seed, req_ts, resp_ts, latency, batch)
        with lk: write_rows(out_csv, [row])
        made += 1
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
    stop = threading.Event()
    print(f"START {len(lanes)} lanes @ n={n}, concurrency={concurrency}, min-gap={min_gap}s, batch={batch}", flush=True)
    results = []; threads = []
    for prov, models in lanes.items():
        t = threading.Thread(target=run_lane, args=(prov, models, n, out_dir, batch, concurrency, min_gap, stop, language, results), daemon=True)
        t.start(); threads.append(t)
    try:
        for t in threads: t.join()
    except KeyboardInterrupt:
        stop.set(); print("STOPPING (data already flushed per-row)", flush=True)
    skipped = [(name, st) for (name, got, st) in results if st.startswith("error")]
    print("ALL LANES COMPLETE", flush=True)
    if skipped:
        print("\n=== SKIPPED (errored — NOT collected, NOT swapped) ===", flush=True)
        for name, st in skipped: print(f"  {name}: {st}", flush=True)
    else:
        print("No models skipped — all attempted models collected cleanly.", flush=True)
    return results

def generate(model_name, api_model, provider, n, out_csv, meta, language="en", dry_run=False,
             batch="cat_collect_2026", pace=0.1):
    key = os.environ.get(PROVIDERS[provider][1])
    if not key: sys.exit(f"Missing env key {PROVIDERS[provider][1]} for provider {provider}")
    target_temp = provider_midpoint(provider); made = 0
    while made < n:
        pairs, fetched_at = fetch_items(language)
        prompt = build_prompt(pairs)
        seed = 1000 + made
        req_ts = _now(); t0 = time.time()
        payload, temp_used = call_once(provider, key, api_model, prompt, target_temp, seed)
        resp_ts = _now(); latency = int((time.time()-t0)*1000)
        row = build_row(model_name, api_model, provider, meta, language, pairs, fetched_at, prompt,
                        payload, target_temp, temp_used, seed, req_ts, resp_ts, latency, batch)
        made += 1
        if dry_run:
            print(json.dumps({k: row[k] for k in ("model_name","provider","language","temperature_effective",
                  "parse_status","n_words_parsed","total_tokens","latency_ms","items_json","raw_response_text")},
                  ensure_ascii=False, indent=2))
            return [row]
        write_rows(out_csv, [row]); time.sleep(pace)
    print(f"[{provider}/{api_model}] wrote {made} rows -> {out_csv}")

def main():
    ap = argparse.ArgumentParser(description="Collect machine CAT responses (items drawn fresh per assessment).")
    ap.add_argument("--model"); ap.add_argument("--api-model"); ap.add_argument("--provider", choices=list(PROVIDERS))
    ap.add_argument("--n", type=int, default=5); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--language", default="en", help="en only; the Chinese arms are not collected")
    ap.add_argument("--vendor", default="", help="vendor label; defaults to the lane name")
    ap.add_argument("--region", default=""); ap.add_argument("--reasoning", default=""); ap.add_argument("--year", default="")
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
    out = Path(a.out_dir) / f"topup_{a.provider}.csv"
    generate(a.model, a.api_model or a.model, a.provider, a.n, out,
             {"region": a.region, "reasoning": a.reasoning, "year": a.year,
              "vendor": a.vendor or a.provider},
             language=a.language, dry_run=a.dry_run, batch=a.batch)

if __name__ == "__main__":
    main()
