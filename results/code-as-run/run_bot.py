#!/usr/bin/env python3
"""Run the bot over the cases: every case x reps, in parallel, with the code checks. One JSON line per conversation.
Usage: python3 -I run_bot.py CASES.jsonl OUTDIR --model claude-haiku-5-5 --prompt prompt_v1.txt --reps 5
       [--split dev|test|all] [--limit N] [--effort low|medium|high] --results-root RESULTS --cap 30 [--workers 8]"""
import sys, json, argparse, time, concurrent.futures as cf
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalkit as ek


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cases"); ap.add_argument("outdir")
    ap.add_argument("--model", required=True); ap.add_argument("--prompt", required=True)
    ap.add_argument("--reps", type=int, default=1); ap.add_argument("--split", default="all")
    ap.add_argument("--limit", type=int, default=0); ap.add_argument("--effort", default=None)
    ap.add_argument("--results-root", required=True); ap.add_argument("--cap", type=float, required=True)
    ap.add_argument("--workers", type=int, default=8); ap.add_argument("--tag", default="")
    ap.add_argument("--policy", default="policy.md"); ap.add_argument("--eval-version", default="v1")
    a = ap.parse_args()
    ek.configure(a.policy, a.eval_version)
    out = Path(a.outdir); out.mkdir(parents=True, exist_ok=True)
    prompt = Path(a.prompt).read_text()
    cases = [json.loads(l) for l in open(a.cases)]
    if a.split != "all":
        cases = [c for c in cases if c["split"] == a.split]
    if a.limit:
        cases = cases[: a.limit]
    done = set()
    runs_path = out / "runs.jsonl"
    if runs_path.exists():                                   # resume: skip (case, rep) already done
        for l in runs_path.read_text().splitlines():
            r = json.loads(l)
            done.add((r["case"], r["rep"]))
    jobs = [(c, r) for r in range(a.reps) for c in cases if (c["id"], r) not in done]
    (out / "command.json").write_text(json.dumps({"argv": sys.argv, "prompt_text": prompt, "policy": a.policy,
                                                  "eval_version": a.eval_version, "policy_text": ek.POLICY,
                                                  "tools": ek.tools(), "started": time.time()}, indent=1))
    ledger = ek.Ledger(out / "ledger.jsonl", a.cap, a.results_root)
    client = ek.Client(ledger, a.tag or out.name)

    def one(job):
        c, rep = job
        t0 = time.time()
        try:
            o = ek.run_bot(client, a.model, prompt, c, effort=a.effort, tag=f"{c['id']}#{rep}")
        except ek.BudgetExceeded:
            raise
        except Exception as e:
            return {"case": c["id"], "rep": rep, "error": str(e)[:300]}
        chk = ek.code_checks(c, o)
        return {"case": c["id"], "rep": rep, "split": c["split"], "situation": c["situation"], "fare": c["fare"],
                "style": c["style"], "expected": c["expected"], "did": ek.did(o), "checks": chk, "final": o["final"], "first_reply": o["first_reply"],
                "followup_sent": o["followup_sent"],
                "calls": o["calls"], "turns": o["turns"], "stop": o["stop"], "usage": o["usage"], "cost": o["cost"],
                "secs": round(time.time() - t0, 2), "model": a.model}

    n_ok = n_err = 0
    stopped = None
    with cf.ThreadPoolExecutor(a.workers) as ex, open(runs_path, "a") as f:
        futs = [ex.submit(one, j) for j in jobs]
        for fu in cf.as_completed(futs):
            try:
                r = fu.result()
            except ek.BudgetExceeded as e:
                stopped = str(e)
                for g in futs:
                    g.cancel()
                continue
            f.write(json.dumps(r) + "\n"); f.flush()
            n_err += "error" in r
            n_ok += "error" not in r
    print(f"{out.name}: {n_ok} conversations, {n_err} errors, spent ${ledger.mine:.4f}, study total ${ledger.total():.4f}"
          + (f" -- STOPPED: {stopped}" if stopped else ""))


if __name__ == "__main__":
    main()
