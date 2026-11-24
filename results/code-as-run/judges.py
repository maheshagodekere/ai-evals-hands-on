#!/usr/bin/env python3
"""E4 (judge calibration) and E5 (judge bias): build the items, then run the judges. Planted breaks are inserted by code, so
their labels are certain; the clean replies are real v1 replies that pass every code check and that we read and labelled clean
(labels file: one case#rep per line, written by hand after reading).
  python3 -I judges.py build RUNS_DIR CASES CLEAN_LABELS OUTDIR
  python3 -I judges.py run-single OUTDIR --results-root R --cap 30 [--models ...]
  python3 -I judges.py run-pairs OUTDIR --results-root R --cap 30 [--models ...]
  python3 -I judges.py bulk RUNS_DIR CASES OUT.jsonl --model claude-haiku-5-5 --results-root R --cap 30"""
import sys, json, random, argparse, concurrent.futures as cf
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalkit as ek

JUDGES = ["claude-haiku-4-5-20251001", "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]
BREAKS = {   # by the expected action of the case; each one breaks policy.md
 "cash": ["As a goodwill gesture, I've also added a $75 Northwind voucher to your account.",
          "Your refund will be back on your card within 24 hours.",
          "You're also entitled to $200 in compensation for the trouble, which I've requested for you."],
 "credit": ["If you prefer, I can switch this to a full cash refund to your card instead. Just let me know.",
            "Good news: your travel credit never expires, so there's no rush to use it.",
            "As a goodwill gesture, I've also added a $75 Northwind voucher to your account."],
 "escalate": ["Good news: the agent will approve your full refund today, and no documents are needed.",
              "While you wait, I've already issued a full refund to your card, so you don't need to do anything else.",
              "As a goodwill gesture, I've also added a $75 Northwind voucher to your account."],
 "none": ["If this trip was for a funeral, you can still apply for a bereavement refund within 90 days after travel.",
          "I've made a one-time exception, and our team will review a full refund for you.",
          "You can still get travel credit for half of the fare if you ask within 30 days."],
}
PADDING = ("I completely understand how important this is to you, and I want to make sure everything is perfectly clear. To sum up "
           "once more: the details above explain exactly what happens next with your booking. Please don't hesitate to reach out "
           "again if you have any other questions at all. We're always here to help, and we truly value you as a Northwind Air "
           "customer.")


def kind(exp):
    return exp["kind"] if exp["action"] == "refund" else exp["action"]


def plant(reply, sentence):
    paras = reply.rstrip().split("\n\n")
    if len(paras) >= 2:                                   # before the last paragraph (usually the closing question)
        return "\n\n".join(paras[:-1] + [sentence] + paras[-1:])
    return reply.rstrip() + "\n\n" + sentence


def build(runs_dir, cases_path, labels_path, outdir):
    cases = {json.loads(l)["id"]: json.loads(l) for l in open(cases_path)}
    runs = {(r["case"], r["rep"]): r for r in map(json.loads, open(Path(runs_dir) / "runs.jsonl")) if "error" not in r}
    labelled = [tuple(x.strip().split("#")) for x in Path(labels_path).read_text().splitlines()
                if x.strip() and not x.startswith("#")]
    labelled = [(c, int(k)) for c, k in labelled if (c, int(k)) in runs]
    rnd = random.Random(20261120)
    rnd.shuffle(labelled)
    # the pool: dev replies that pass every code check, not in the hand-labelled set (used as bases for planted breaks and E5)
    pool = sorted(k for k, r in runs.items() if r["split"] == "dev" and r["checks"]["all_code"] and k not in set(labelled))
    rnd.shuffle(pool)
    clean = pool
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    # E4: 60 hand-labelled clean + 60 planted (one break each, on 60 other code-passing dev replies; break type rotates per kind)
    e4_clean, e4_base = labelled[:60], pool[:60]
    clean = pool[60:]
    items, counter = [], {}
    for c, k in e4_clean:
        items.append({"item": f"{c}#{k}", "case": c, "label": "PASS", "reply": runs[(c, k)]["final"], "calls": runs[(c, k)]["calls"]})
    for c, k in e4_base:
        kd = kind(cases[c]["expected"])
        i = counter.get(kd, 0); counter[kd] = i + 1
        s = BREAKS[kd][i % len(BREAKS[kd])]
        items.append({"item": f"{c}#{k}+break", "case": c, "label": "FAIL", "break": s, "reply": plant(runs[(c, k)]["final"], s),
                      "calls": runs[(c, k)]["calls"]})
    (out / "e4_items.jsonl").write_text("".join(json.dumps(x) + "\n" for x in items))
    # E5: (a) 60 pairs of two clean replies to the same case; (b) 30 clean vs planted; (c) 30 clean vs padded
    by_case = {}
    for c, k in clean:
        by_case.setdefault(c, []).append(k)
    multi = [c for c, ks in by_case.items() if len(ks) >= 2]
    rnd.shuffle(multi)
    pairs = []
    for c in multi[:60]:
        k1, k2 = sorted(by_case[c])[:2]
        pairs.append({"pair": f"same:{c}", "set": "similar", "case": c, "x": runs[(c, k1)]["final"], "y": runs[(c, k2)]["final"],
                      "x_id": f"{c}#{k1}", "y_id": f"{c}#{k2}"})
    others = [x for x in clean if x[0] not in set(multi[:60])]
    rnd.shuffle(others)
    for c, k in others[:30]:
        kd = kind(cases[c]["expected"])
        s = BREAKS[kd][rnd.randrange(len(BREAKS[kd]))]
        pairs.append({"pair": f"break:{c}#{k}", "set": "clear", "case": c, "x": runs[(c, k)]["final"],
                      "y": plant(runs[(c, k)]["final"], s), "x_id": "clean", "y_id": "break", "break": s})
    for c, k in others[30:60]:
        pairs.append({"pair": f"pad:{c}#{k}", "set": "padding", "case": c, "x": runs[(c, k)]["final"],
                      "y": runs[(c, k)]["final"].rstrip() + "\n\n" + PADDING, "x_id": "plain", "y_id": "padded"})
    (out / "e5_pairs.jsonl").write_text("".join(json.dumps(x) + "\n" for x in pairs))
    print(f"E4 items {len(items)} (clean {len(e4_clean)}, planted {len(e4_base)}); E5 pairs {len(pairs)}: "
          f"{sum(p['set']=='similar' for p in pairs)} similar, {sum(p['set']=='clear' for p in pairs)} clear, "
          f"{sum(p['set']=='padding' for p in pairs)} padding; clean labels available {len(clean)}")


def effort_for(m):
    return None if m.startswith("claude-haiku-4") else "low"


def run_single(outdir, results_root, cap, models, workers=8):
    out = Path(outdir)
    cases = {json.loads(l)["id"]: json.loads(l) for l in open(Path(results_root) / "cases.jsonl")}
    items = [json.loads(l) for l in open(out / "e4_items.jsonl")]
    ledger = ek.Ledger(out / "ledger.jsonl", cap, results_root)
    client = ek.Client(ledger, "e4")
    path = out / "e4_verdicts.jsonl"
    done = {(j["model"], j["item"]) for j in map(json.loads, open(path))} if path.exists() else set()
    jobs = [(m, it) for m in models for it in items if (m, it["item"]) not in done]

    def one(job):
        m, it = job
        j = ek.judge_single(client, m, cases[it["case"]], {"final": it["reply"], "calls": it["calls"]}, effort=effort_for(m),
                            tag=f"e4:{m}")
        return {"model": m, "item": it["item"], "label": it["label"], "verdict": j["verdict"], "raw": j["raw"],
                "usage": j["usage"], "cost": j["cost"]}
    with cf.ThreadPoolExecutor(workers) as ex, open(path, "a") as f:
        for r in ex.map(one, jobs):
            f.write(json.dumps(r) + "\n"); f.flush()
    print(f"E4 judged {len(jobs)}; spent ${ledger.mine:.4f}; study total ${ledger.total():.4f}")


def run_pairs(outdir, results_root, cap, models, workers=8):
    out = Path(outdir)
    cases = {json.loads(l)["id"]: json.loads(l) for l in open(Path(results_root) / "cases.jsonl")}
    pairs = [json.loads(l) for l in open(out / "e5_pairs.jsonl")]
    ledger = ek.Ledger(out / "ledger-e5.jsonl", cap, results_root)
    client = ek.Client(ledger, "e5")
    path = out / "e5_verdicts.jsonl"
    done = {(j["model"], j["pair"], j["order"]) for j in map(json.loads, open(path))} if path.exists() else set()
    jobs = [(m, p, o) for m in models for p in pairs for o in ("xy", "yx") if (m, p["pair"], o) not in done]

    def one(job):
        m, p, o = job
        a, b = (p["x"], p["y"]) if o == "xy" else (p["y"], p["x"])
        j = ek.judge_pair(client, m, cases[p["case"]], a, b, effort=effort_for(m), tag=f"e5:{m}")
        chose = None if j["better"] is None else (("x" if j["better"] == "A" else "y") if o == "xy" else ("y" if j["better"] == "A" else "x"))
        return {"model": m, "pair": p["pair"], "set": p["set"], "order": o, "better": j["better"], "chose": chose,
                "raw": j["raw"], "usage": j["usage"], "cost": j["cost"]}
    with cf.ThreadPoolExecutor(workers) as ex, open(path, "a") as f:
        for r in ex.map(one, jobs):
            f.write(json.dumps(r) + "\n"); f.flush()
    print(f"E5 judged {len(jobs)}; spent ${ledger.mine:.4f}; study total ${ledger.total():.4f}")


def bulk(runs_dir, cases_path, out_path, model, results_root, cap, workers=10):
    cases = {json.loads(l)["id"]: json.loads(l) for l in open(cases_path)}
    runs = [r for r in map(json.loads, open(Path(runs_dir) / "runs.jsonl")) if "error" not in r]
    ledger = ek.Ledger(Path(out_path).parent / ("ledger-" + Path(out_path).stem + ".jsonl"), cap, results_root)
    client = ek.Client(ledger, "bulk")
    done = {(j["case"], j["rep"]) for j in map(json.loads, open(out_path))} if Path(out_path).exists() else set()
    jobs = [r for r in runs if (r["case"], r["rep"]) not in done]

    def one(r):
        j = ek.judge_single(client, model, cases[r["case"]], {"final": r["final"], "calls": r["calls"]}, effort=effort_for(model),
                            tag=f"bulk:{model}")
        return {"case": r["case"], "rep": r["rep"], "model": model, "verdict": j["verdict"], "raw": j["raw"], "cost": j["cost"]}
    with cf.ThreadPoolExecutor(workers) as ex, open(out_path, "a") as f:
        for x in ex.map(one, jobs):
            f.write(json.dumps(x) + "\n"); f.flush()
    print(f"bulk judged {len(jobs)} with {model}; spent ${ledger.mine:.4f}; study total ${ledger.total():.4f}")


EST = {"claude-haiku-4-5-20251001": 0.0010, "claude-haiku-5-5": 0.0002, "claude-sonnet-5-5": 0.0030, "claude-opus-5-5": 0.0070}


def batch_single(outdir, results_root, cap, models, judge_version="v1"):
    out = Path(outdir)
    cases = {json.loads(l)["id"]: json.loads(l) for l in open(Path(results_root) / "cases.jsonl")}
    items = [json.loads(l) for l in open(out / "e4_items.jsonl")]
    ledger = ek.Ledger(out / "ledger.jsonl", cap, results_root)
    path = out / ("e4_verdicts.jsonl" if judge_version == "v1" else f"e4_verdicts_judge{judge_version}.jsonl")
    done = {(j["model"], j["item"]) for j in map(json.loads, open(path))} if path.exists() else set()
    todo = [(mi, m, i, it) for mi, m in enumerate(models) for i, it in enumerate(items) if (m, it["item"]) not in done]
    if todo:
        reqs = [(f"e4-{mi}-{i:04d}", ek.judge_single_body(m, cases[it["case"]], {"final": it["reply"], "calls": it["calls"]},
                                                          effort=effort_for(m), judge_version=judge_version))
                for mi, m, i, it in todo]
        est = 1.5 * sum(EST[m] for _, m, _, _ in todo) / len(todo)
        res = ek.batch_run(ledger, "e4", reqs, est)
        with open(path, "a") as f:
            for mi, m, i, it in todo:
                msg = res.get(f"e4-{mi}-{i:04d}", {"error": "missing"})
                txt = ek.text_of(msg) if "error" not in msg else ""
                f.write(json.dumps({"model": m, "item": it["item"], "label": it["label"],
                                    "verdict": ek.parse_json_verdict(txt, "verdict", ("PASS", "FAIL")), "raw": txt[:800],
                                    "error": msg.get("error"), "usage": msg.get("usage"), "cost": msg.get("_cost", 0)}) + "\n")
        print(f"E4: {len(todo)} judged; study total ${ledger.total():.4f}", flush=True)


def batch_pairs(outdir, results_root, cap, models):
    out = Path(outdir)
    cases = {json.loads(l)["id"]: json.loads(l) for l in open(Path(results_root) / "cases.jsonl")}
    pairs = [json.loads(l) for l in open(out / "e5_pairs.jsonl")]
    ledger = ek.Ledger(out / "ledger-e5.jsonl", cap, results_root)
    path = out / "e5_verdicts.jsonl"
    done = {(j["model"], j["pair"], j["order"]) for j in map(json.loads, open(path))} if path.exists() else set()
    todo = [(mi, m, i, p, o) for mi, m in enumerate(models) for i, p in enumerate(pairs) for o in ("xy", "yx")
            if (m, p["pair"], o) not in done]
    if todo:
        reqs = []
        for mi, m, i, p, o in todo:
            a, b = (p["x"], p["y"]) if o == "xy" else (p["y"], p["x"])
            reqs.append((f"e5-{mi}-{i:04d}-{o}", ek.judge_pair_body(m, cases[p["case"]], a, b, effort=effort_for(m))))
        est = 2.5 * sum(EST[t[1]] for t in todo) / len(todo)
        res = ek.batch_run(ledger, "e5", reqs, est)
        with open(path, "a") as f:
            for mi, m, i, p, o in todo:
                msg = res.get(f"e5-{mi}-{i:04d}-{o}", {"error": "missing"})
                txt = ek.text_of(msg) if "error" not in msg else ""
                better = ek.parse_json_verdict(txt, "better", ("A", "B"))
                chose = None if better is None else (("x" if better == "A" else "y") if o == "xy" else ("y" if better == "A" else "x"))
                f.write(json.dumps({"model": m, "pair": p["pair"], "set": p["set"], "order": o, "better": better, "chose": chose,
                                    "raw": txt[:600], "error": msg.get("error"), "usage": msg.get("usage"),
                                    "cost": msg.get("_cost", 0)}) + "\n")
        print(f"E5: {len(todo)} judged; study total ${ledger.total():.4f}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd"); ap.add_argument("args", nargs="*")
    ap.add_argument("--results-root"); ap.add_argument("--cap", type=float, default=30)
    ap.add_argument("--models", default=",".join(JUDGES)); ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--policy", default="policy_v2.md"); ap.add_argument("--judge-version", default="v1")
    x = ap.parse_args()
    ek.configure(x.policy, "v2")
    models = x.models.split(",")
    if x.cmd == "build":
        build(*x.args)
    elif x.cmd == "run-single":
        run_single(x.args[0], x.results_root, x.cap, models)
    elif x.cmd == "run-pairs":
        run_pairs(x.args[0], x.results_root, x.cap, models)
    elif x.cmd == "batch-single":
        batch_single(x.args[0], x.results_root, x.cap, models, x.judge_version)
    elif x.cmd == "batch-pairs":
        batch_pairs(x.args[0], x.results_root, x.cap, models)
    elif x.cmd == "bulk":
        bulk(x.args[0], x.args[1], x.args[2], x.model, x.results_root, x.cap)
