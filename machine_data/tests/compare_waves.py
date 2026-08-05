#!/usr/bin/env python3
"""Compare two collection runs model by model.

Written to answer one question after the 2026-08-04 review: how much of the "too slow" diagnosis in
the first wave was the harvest bug discarding answers we had already paid for?

    python machine_data/tests/compare_waves.py <wave1_dir> <wave2_dir>

Reports, per model, words collected, item slots with NO ENTRY AT ALL (the bug's signature), cap and
deadline errors, and mean seconds per landed word. Absent slots must be zero in a fixed run.
"""
import csv, glob, json, statistics, sys
from datetime import datetime
from pathlib import Path

csv.field_size_limit(sys.maxsize)
N = 10
_ts = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))

def load(d):
    out = {}
    for f in sorted(glob.glob(str(Path(d) / "topup_*.csv"))):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            out.setdefault(r["model_name"], []).append(r)
    return out

def stats(rows):
    words = absent = capped = deadline = other = 0
    lat = []
    for r in rows:
        raw = json.loads(r["raw_responses"])
        absent += N - len(raw)                       # slots with no entry at all
        for i in range(N):
            if r[f"word_{i}"]:
                words += 1
                a, b = r[f"item_{i}_request_utc"], r[f"item_{i}_response_utc"]
                if a and b: lat.append((_ts(b) - _ts(a)).total_seconds())
            elif i < len(raw) and raw[i].startswith("[ERROR"):
                e = raw[i].lower()
                if "cap" in e: capped += 1
                elif "deadline" in e: deadline += 1
                else: other += 1
    return {"assessments": len(rows), "slots": N * len(rows), "words": words, "absent": absent,
            "capped": capped, "deadline": deadline, "other": other,
            "mean_s": statistics.mean(lat) if lat else 0.0}

def main(d1, d2):
    w1, w2 = load(d1), load(d2)
    models = sorted(set(w1) | set(w2))
    print(f"{'model':24}{'wave1 words':>12}{'wave2 words':>12}{'w1 absent':>11}{'w2 absent':>11}"
          f"{'w1 s/word':>11}{'w2 s/word':>11}  note")
    tot = {k: [0, 0] for k in ("words", "slots", "absent", "capped", "deadline")}
    for m in models:
        a = stats(w1.get(m, [])); b = stats(w2.get(m, []))
        for k in tot:
            tot[k][0] += a[k]; tot[k][1] += b[k]
        note = ""
        if not w2.get(m): note = "not collected in wave 2"
        elif not w1.get(m): note = "new in wave 2"
        elif a["words"] == 0 and b["words"] > 0: note = "RECOVERED — wave 1 verdict was the bug"
        elif b["words"] > a["words"]: note = f"+{b['words']-a['words']} words"
        elif b["words"] < a["words"]: note = f"{b['words']-a['words']} words"
        print(f"{m:24}{a['words']:>12}{b['words']:>12}{a['absent']:>11}{b['absent']:>11}"
              f"{a['mean_s']:>11.0f}{b['mean_s']:>11.0f}  {note}")
    print(f"\n{'TOTAL':24}{tot['words'][0]:>12}{tot['words'][1]:>12}"
          f"{tot['absent'][0]:>11}{tot['absent'][1]:>11}")
    print(f"\nwave 1: {tot['words'][0]}/{tot['slots'][0]} words, {tot['absent'][0]} slots absent, "
          f"{tot['capped'][0]} capped, {tot['deadline'][0]} deadline")
    print(f"wave 2: {tot['words'][1]}/{tot['slots'][1]} words, {tot['absent'][1]} slots absent, "
          f"{tot['capped'][1]} capped, {tot['deadline'][1]} deadline")
    if tot["absent"][1]:
        print("\nFAIL: wave 2 still has slots with no entry — the harvest is still losing items.")
        return 1
    print("\nOK: every item slot in wave 2 has a record. No answer was silently discarded.")
    return 0

if __name__ == "__main__":
    if len(sys.argv) != 3: sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
