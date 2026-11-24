#!/usr/bin/env python3
"""Summaries for the AI Evals experiment (no API). Usage:
python3 scripts/analyze.py summary RUNS_DIR [--judge JUDGED.jsonl]      -> summary.json + printed table
python3 scripts/analyze.py compare RUNS_A RUNS_B [--first50]            -> difference in mean per-run pass rate, bootstrap 95 % CI
"""

import json
import math
import random
import argparse
import statistics as st
from collections import defaultdict
from pathlib import Path

CHECKS = ["looked_up", "right_action", "right_amount", "one_action", "no_internal_id", "replied"]


def load(d):
    rows = [json.loads(l) for l in open(Path(d) / "runs.jsonl")]
    return [r for r in rows if "error" not in r], [r for r in rows if "error" in r]


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0, c - h), min(1, c + h))


def passed(r, judged=None):
    ok = r["checks"]["all_code"]
    if judged is not None:
        ok = ok and judged.get((r["case"], r["rep"])) != "FAIL"
    return ok


def summary(d, judged_path=None):
    rows, errs = load(d)
    judged = None
    if judged_path:
        judged = {(j["case"], j["rep"]): j["verdict"] for j in map(json.loads, open(judged_path))}
    by_case = defaultdict(list)
    for r in rows:
        by_case[r["case"]].append(passed(r, judged))
    n = len(rows)
    k = sum(passed(r, judged) for r in rows)
    out = {
        "dir": str(d),
        "conversations": n,
        "errors": len(errs),
        "pass": k,
        "pass_rate": k / n if n else 0,
        "pass_rate_ci": wilson(k, n),
        "cases": len(by_case),
    }
    out["per_check"] = {c: sum(r["checks"][c] for r in rows) / n for c in CHECKS}
    full = {c: v for c, v in by_case.items() if len(v) >= 5}
    if full:
        out["pass_at_5"] = sum(any(v[:5]) for v in full.values()) / len(full)
        out["pass_pow_5"] = sum(all(v[:5]) for v in full.values()) / len(full)
        out["mean_case_rate"] = st.mean(sum(v[:5]) / 5 for v in full.values())
        out["flaky_cases"] = sum(0 < sum(v[:5]) < 5 for v in full.values())
    for key in ("situation", "style", "fare", "split"):
        g = defaultdict(lambda: [0, 0])
        for r in rows:
            g[r[key]][0] += passed(r, judged)
            g[r[key]][1] += 1
        out["by_" + key] = {a: round(b[0] / b[1], 3) for a, b in sorted(g.items())}
    rep0 = [r for r in rows if r["rep"] == 0]
    out["run0_pass_rate"] = sum(passed(r, judged) for r in rep0) / len(rep0) if rep0 else None
    cost = [r["cost"] for r in rows]
    out["cost_total"] = sum(cost)
    out["cost_per_1000"] = 1000 * st.mean(cost) if cost else 0
    out["followup_share"] = sum(r.get("followup_sent", False) for r in rows) / n if n else 0
    out["mean_secs"] = st.mean(r["secs"] for r in rows) if rows else 0
    wrong = defaultdict(int)
    for r in rows:
        if not r["checks"]["all_code"]:
            e = r["expected"]
            exp = e["action"] + (" " + e["kind"] if e["action"] == "refund" else "")
            wrong[f"expected {exp} -> did {r['did'].split(' ')[0]}"] += 1
    out["failure_patterns"] = dict(sorted(wrong.items(), key=lambda x: -x[1]))
    return out


def case_rates(d):
    rows, _ = load(d)
    g = defaultdict(list)
    for r in rows:
        g[r["case"]].append(r["checks"]["all_code"])
    return {c: sum(v) / len(v) for c, v in g.items()}


def compare(da, db, first=None, seed_order=7, boots=10000):
    a, b = case_rates(da), case_rates(db)
    common = sorted(set(a) & set(b))
    random.Random(seed_order).shuffle(common)
    if first:
        common = common[:first]
    diffs = [b[c] - a[c] for c in common]
    mean = st.mean(diffs)
    rnd = random.Random(1)
    bs = sorted(st.mean(rnd.choice(diffs) for _ in diffs) for _ in range(boots))
    return {
        "cases": len(common),
        "a": st.mean(a[c] for c in common),
        "b": st.mean(b[c] for c in common),
        "diff": mean,
        "ci95": (bs[int(0.025 * boots)], bs[int(0.975 * boots) - 1]),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("a")
    ap.add_argument("b", nargs="?")
    ap.add_argument("--judge")
    ap.add_argument("--first", type=int)
    x = ap.parse_args()
    if x.cmd == "summary":
        s = summary(x.a, x.judge)
        Path(x.a, "summary.json" if not x.judge else "summary-judged.json").write_text(
            json.dumps(s, indent=1)
        )
        print(json.dumps(s, indent=1))
    else:
        print(json.dumps(compare(x.a, x.b, x.first), indent=1))
