#!/usr/bin/env python3
"""Ask for an evaluation of prompt.md on the dev cases. Prints the pass rate and the failing cases."""
import json, time, sys
from pathlib import Path
req, res = Path("eval_requests"), Path("eval_results")
n = len(list(req.glob("*.json"))) + 1
if n > 1:
    sys.exit(f"No evals left: the limit is {1} per session.")
(req / f"{n}.json").write_text(json.dumps({"prompt": Path("prompt.md").read_text(), "t": time.time()}))
print(f"Eval {n} of {1} requested. Running the bot on all dev cases (a few minutes)...", flush=True)
for _ in range(1800):
    p = res / f"{n}.json"
    if p.exists():
        r = json.loads(p.read_text())
        print(f"\nPASS RATE: {r['passed']}/{r['total']} ({100 * r['passed'] / r['total']:.1f} %)")
        for f in r["failures"]:
            print("\n---", f["case"], "| expected:", f["expected"], "| the bot did:", f["did"], "| failed checks:", ", ".join(f["failed"]))
            print("CUSTOMER:", f["message"])
            print("SKYE'S FINAL REPLY:", f["reply"])
        sys.exit(0)
    time.sleep(1)
sys.exit("Timed out waiting for the eval result.")
