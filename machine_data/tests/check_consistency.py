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
     lambda: all((r.get("pace_exempt") or "") in ("", "yes") for r in REG)
             and all(r["status"] == "live" and "5-MINUTE RULE" in r["notes"].upper()
                     for r in REG if r.get("pace_exempt") == "yes")
             and all(f"`{r['model']}`" in LINEUP for r in REG if r.get("pace_exempt") == "yes")),
    ("status values are known",
     {r["status"] for r in rows} <= {"live", "dead", "dropped", "blocked"}),
    ("no live model is known-blocked (0/10 in the shakedown)",
     not [r for r in live if r.get("shakedown_items_ok") == "0"]),
    ("no seed is sent to any provider",
     '"seed"' not in code),
    ("every file open declares utf-8",
     all("encoding=" in ln for ln in code.splitlines()
         if "open(" in ln and "urlopen" not in ln)),
    ("a collector crash is reported instead of counted as clean",
     "collector crash" in code),
]

bad = [n for n, ok in CHECKS if not ok]
for name, ok in CHECKS:
    print(("PASS  " if ok else "FAIL  ") + name)
print(f"\n{len(CHECKS)-len(bad)}/{len(CHECKS)} checks passed | "
      f"{len(live)} live, {sum(1 for r in rows if r['status']=='blocked')} blocked, "
      f"{sum(1 for r in rows if r['status']=='dead')} dead, "
      f"{sum(1 for r in rows if r['status']=='dropped')} dropped")
sys.exit(1 if bad else 0)
