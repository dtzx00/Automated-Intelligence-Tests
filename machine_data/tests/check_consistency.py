#!/usr/bin/env python3
"""Fail loudly when the code, the README and the registry stop agreeing.

Written after an external review found the repo saying three different things at once: two model
registries with the collector defaulting to the wrong one, a docstring claiming 65 columns while
the code built 63, and a design note promising a network fetch that had been deleted days earlier.
Documentation drift is invisible until someone reads the repo cold, so it is checked here instead.

    python machine_data/tests/check_consistency.py
"""
import csv, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MD = HERE.parent
sys.path.insert(0, str(MD))
import data_collection as d                                    # noqa: E402

readme = (MD.parent / "README.md").read_text()
lineup = (MD / "MODEL_LINEUP.md").read_text()
code = (MD / "data_collection.py").read_text()
rows = list(csv.DictReader(open(MD / "models.csv")))
live = [r for r in rows if r["status"] == "live"]

CHECKS = [
    ("README states the column count the code builds",
     f"**{len(d.FIELDS)} columns**" in readme),
    ("module docstring states the column count the code builds",
     f"{len(d.FIELDS)} columns" in code.split('"""')[1]),
    ("README names models.csv as the only registry",
     "machine_data/models.csv` is the **only** model registry" in readme),
    ("collector defaults to that registry",
     'default=str(HERE/"models.csv")' in code),
    ("no reference to a second registry in code",
     "models_v2" not in code),
    ("no leftover claim that items are fetched over the network",
     "cue pairs from Rugu" not in code and "from the Rugu CAT" not in readme),
    ("no dead --language flag", "--language" not in code),
    ("no seed column, because no seed is sent",
     "seed_base" not in d.FIELDS and "seed_base" not in readme),
    ("MODEL_LINEUP live count matches the registry",
     f"| **{len(live)}** |" in lineup),
    ("MODEL_LINEUP blocked count matches the registry",
     f"| {sum(1 for r in rows if r['status']=='blocked')} |" in lineup),
    ("every live model resolves to a lane that has an adapter",
     all(d.resolve_lane(r) in d.PROVIDERS for r in live)),
    ("every live model has an api_model_id",
     all((r["api_model_id"] or "").strip() for r in live)),
    ("model names are unique", len({r["model"] for r in rows}) == len(rows)),
    ("no two live models share a lane and an api id",
     len({(d.resolve_lane(r), r["api_model_id"]) for r in live}) == len(live)),
    ("every temperature range belongs to a real lane",
     set(d.PROVIDER_TEMP_RANGE) <= set(d.PROVIDERS)),
    ("pace_exempt values are known and each exempt model is documented",
     lambda: all((r.get("pace_exempt") or "") in ("", "yes") for r in rows)
             and all(r["status"] == "live" and "5-MINUTE RULE" in r["notes"].upper()
                     for r in rows if r.get("pace_exempt") == "yes")
             and all(f"`{r['model']}`" in lineup for r in rows if r.get("pace_exempt") == "yes")),
    ("status values are known",
     {r["status"] for r in rows} <= {"live", "dead", "dropped", "blocked"}),
    ("no live model is known-blocked (0/10 in the shakedown)",
     not [r for r in live if r.get("shakedown_items_ok") == "0"]),
    ("no seed is sent to any provider",
     '"seed"' not in code),
    ("every file open declares utf-8",
     all("encoding=" in ln for ln in code.splitlines()
         if "open(" in ln and "urlopen" not in ln and "os.open(" not in ln)),
    ("a collector crash is reported instead of counted as clean",
     "collector crash" in code),
    # The only check here that EXECUTES the collector. Every other check is a string or registry
    # match, which is exactly why the harvest bug — nine answered items written as zero words —
    # passed 20/20 twice. One hung item must cost one word, not ten.
    ("run_assessment keeps every answered item when the deadline fires", lambda: harvest_holds()),
]

def harvest_holds():
    hung = {"n": 0}
    lock = __import__("threading").Lock()
    def fake(key, api_model, prompt, temperature):
        with lock:
            hung["n"] += 1
            first = hung["n"] == 1
        if first:
            __import__("time").sleep(30)          # one item hangs past the deadline
        return {"text": "instrument", "reasoning_text": "", "api_model_returned": api_model,
                "response_id": "x", "system_fingerprint": "", "finish_reason": "stop",
                "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2,
                "api_request_id": "", "endpoint_base": "fake", "max_tokens": ""}
    d.PROVIDERS["faketest"] = (fake, "FAKE_KEY")
    try:
        pairs = [("piano", "guitar")] * d.N_ITEMS
        row = d.run_assessment("FakeModel", "fake-1", "faketest", {"vendor": "fake"}, "test",
                               "k", pairs=pairs, item_workers=5, deadline_s=3)
    finally:
        d.PROVIDERS.pop("faketest", None)
    raws = __import__("json").loads(row["raw_responses"])
    words = [row[f"word_{i}"] for i in range(d.N_ITEMS)]
    ok = (len(raws) == d.N_ITEMS                                   # every slot accounted for
          and sum(1 for w in words if w) == d.N_ITEMS - 1          # only the hung item is lost
          and sum(1 for e in raws if e.startswith("[ERROR")) == 1)
    if not ok:
        print(f"      raw_responses={len(raws)} words={sum(1 for w in words if w)} "
              f"errors={sum(1 for e in raws if e.startswith('[ERROR'))}")
    return ok

def _run(ok):
    """Evaluate a check. A callable check MUST be called: a lambda object is truthy, so the first
    behavioural check added here silently passed without executing. Found 2026-08-04."""
    if callable(ok):
        try:
            return bool(ok())
        except Exception as e:
            print(f"      (raised {type(e).__name__}: {e})")
            return False
    return bool(ok)

results = [(name, _run(ok)) for name, ok in CHECKS]
bad = [n for n, ok in results if not ok]
for name, ok in results:
    print(("PASS  " if ok else "FAIL  ") + name)
print(f"\n{len(CHECKS)-len(bad)}/{len(CHECKS)} checks passed | "
      f"{len(live)} live, {sum(1 for r in rows if r['status']=='blocked')} blocked, "
      f"{sum(1 for r in rows if r['status']=='dead')} dead, "
      f"{sum(1 for r in rows if r['status']=='dropped')} dropped")
sys.exit(1 if bad else 0)
