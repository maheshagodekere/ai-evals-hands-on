#!/usr/bin/env python3
"""E9, the loop: Claude Code improves the bot's prompt against an eval on the DEV cases, in a sandbox.

The agent's folder (WS) holds: prompt.md (the bot's instructions; the policy is appended by the harness and cannot be edited),
policy.md (read-only), dev_cases.jsonl (the 126 dev cases with their expected actions), run_eval.py (asks for an eval).
run_eval.py writes eval_requests/N.json; THIS process (outside the sandbox, holding the key) runs the bot on the dev cases
(1 run each, Haiku 5.5, the same harness and checks as the main runs) and writes eval_results/N.json, which the agent's
script prints. At most MAX_EVALS evals per loop run. The agent has no network, cannot write outside WS, cannot change the
policy, the cases, the eval script or the results, and never sees the key or the test set.
After the agent stops, the final prompt is saved; the test-set run is a separate run_bot.py call.

Usage: python3 -I run_loop.py --name loop1 --results-root RESULTS --cap 30 [--agent-budget 2.5] [--max-turns 80]
"""
import sys, os, json, time, shutil, argparse, subprocess, threading, hashlib, concurrent.futures as cf
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalkit as ek

HERE = Path(__file__).resolve().parent
MAX_EVALS = 10
POLICY_BLOCK = "\n\n<policy>\n{policy}\n</policy>"

TASK = """You are improving the system prompt of "Skye", an AI customer-support bot for an airline (Northwind Air). Skye handles
cancellation and refund requests with four tools: lookup_booking, issue_refund, cancel_booking and escalate_to_agent.

- prompt.md is Skye's system prompt. Edit it to make Skye handle more cases correctly. The airline's refund policy (policy.md)
  is added after your prompt automatically; you cannot change the policy.
- dev_cases.jsonl has the evaluation cases: each customer's message, their booking record and the correct outcome.
- Run `python3 run_eval.py` to score the current prompt.md on all the dev cases. It prints the pass rate and every failing case.
  Each eval takes a few minutes and you may run it at most {max_evals} times, so make each one count.
- Only edit prompt.md. Do not edit any other file.

Goal: the highest pass rate you can reach. When you are done, say so and summarize what you changed."""

RUN_EVAL = r'''#!/usr/bin/env python3
"""Ask for an evaluation of prompt.md on the dev cases. Prints the pass rate and the failing cases."""
import json, time, sys
from pathlib import Path
req, res = Path("eval_requests"), Path("eval_results")
n = len(list(req.glob("*.json"))) + 1
if n > MAXEV:
    sys.exit(f"No evals left: the limit is {MAXEV} per session.")
(req / f"{n}.json").write_text(json.dumps({"prompt": Path("prompt.md").read_text(), "t": time.time()}))
print(f"Eval {n} of {MAXEV} requested. Running the bot on all dev cases (a few minutes)...", flush=True)
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
'''


def bot_prompt_from(prompt_md):
    return prompt_md.rstrip() + POLICY_BLOCK


def start_prompt():
    v1 = (HERE / "prompt_v1.txt").read_text()
    head = v1.split("\n\n<policy>")[0]
    assert bot_prompt_from(head).replace("{policy}", "x") == v1.replace("{policy}", "x")
    return head + "\n"


def serve_evals(ws, outdir, ledger, stop_flag, cases, workers=10, bot_model="claude-haiku-5-5", max_evals=10):
    client = ek.Client(ledger, outdir.name + "-evals", fake=os.environ.get("EVAL_FAKE_WATCHER") == "1" or None)
    seen = set()
    log = open(outdir / "evals.jsonl", "a")
    while not stop_flag.is_set():
        for p in sorted((ws / "eval_requests").glob("*.json"), key=lambda x: int(x.stem)):
            if p.name in seen:
                continue
            seen.add(p.name)
            n = int(p.stem)
            if n > max_evals:
                continue
            prompt_md = json.loads(p.read_text())["prompt"]
            prompt = bot_prompt_from(prompt_md)

            def one(c):
                try:
                    o = ek.run_bot(client, bot_model, prompt, c, tag=f"loop-eval{n}:{c['id']}")
                except ek.BudgetExceeded:
                    raise
                except Exception as e:
                    return c, None, str(e)[:200]
                return c, o, None
            rows = []
            with cf.ThreadPoolExecutor(workers) as ex:
                for c, o, err in ex.map(one, cases):
                    if o is None:
                        rows.append({"case": c["id"], "error": err})
                        continue
                    chk = ek.code_checks(c, o)
                    rows.append({"case": c["id"], "checks": chk, "did": ek.did(o), "expected": c["expected"],
                                 "message": c["message"], "reply": o["final"], "calls": o["calls"], "cost": o["cost"]})
            ok = [r for r in rows if "checks" in r and r["checks"]["all_code"]]
            fails = [{"case": r["case"], "expected": r["expected"], "did": r.get("did", "error"),
                      "failed": [k for k, v in r.get("checks", {}).items() if not v and k != "all_code"] or ["error"],
                      "message": r.get("message", ""), "reply": (r.get("reply") or "")[:600]}
                     for r in rows if r not in ok]
            res = {"n": n, "passed": len(ok), "total": len(rows), "failures": fails}
            (ws / "eval_results" / f"{n}.json").write_text(json.dumps(res))
            log.write(json.dumps({"n": n, "t": time.time(), "passed": len(ok), "total": len(rows),
                                  "prompt_sha": hashlib.sha256(prompt_md.encode()).hexdigest()[:12], "prompt": prompt_md,
                                  "rows": rows}) + "\n")
            log.flush()
            print(f"  eval {n}: {len(ok)}/{len(rows)} (study total ${ledger.total():.2f})", flush=True)
        time.sleep(1)


def settings_for(ws, secret_dir):
    deny_write = [str(ws / f) for f in ("policy.md", "dev_cases.jsonl", "run_eval.py", "TASK.md")]
    deny_dirs = [str(ws / "eval_results")]
    home = Path(os.path.expanduser("~"))
    deny_read = [str(secret_dir), str(HERE), str(home / ".ssh"), str(home / ".aws"), str(home / ".config"),
                 str(home / ".claude"), str(home / "work"), str(home / "Library")]
    s = {"autoMemoryEnabled": False,
         "permissions": {"deny": ["WebFetch", "WebSearch"] + [f"Read(/{d}/**)" for d in deny_read]
                         + [f"Edit(/{p})" for p in deny_write] + [f"Write(/{p})" for p in deny_write]
                         + [f"Edit(/{d}/**)" for d in deny_dirs] + [f"Write(/{d}/**)" for d in deny_dirs],
                         "blockWritesOutsideWorkingDirectories": True},
         "sandbox": {"enabled": True, "failIfUnavailable": True, "autoAllowBashIfSandboxed": True, "allowUnsandboxedCommands": False,
                     "filesystem": {"denyRead": deny_read, "denyWrite": deny_write + deny_dirs},
                     "network": {"allowedDomains": [], "strictAllowlist": True}},
         "apiKeyHelper": f"/bin/cat {secret_dir}/key"}
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True); ap.add_argument("--results-root", required=True)
    ap.add_argument("--cap", type=float, required=True); ap.add_argument("--agent-budget", type=float, default=2.5)
    ap.add_argument("--max-turns", type=int, default=80); ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--claude-bin", default=shutil.which("claude"))
    ap.add_argument("--cases", default=None, help="cases file (default RESULTS/cases.jsonl); the dev split is used")
    ap.add_argument("--bot-model", default="claude-haiku-5-5"); ap.add_argument("--max-evals", type=int, default=MAX_EVALS)
    ap.add_argument("--task", default=None, help="override the agent's task text (smoke tests only)")
    a = ap.parse_args()
    ek.configure("policy_v2.md", "v2")
    root = Path("/tmp/ev-loop").resolve() / a.name
    ws, secret, home = root / "ws", root / "secret", root / "home"
    if root.exists():
        sys.exit(f"{root} exists; use a new --name")
    for d in (ws / "eval_requests", ws / "eval_results", secret, home):
        d.mkdir(parents=True)
    outdir = Path(a.results_root) / f"e9-{a.name}"
    outdir.mkdir(parents=True)
    (ws / "prompt.md").write_text(start_prompt())
    shutil.copy(HERE / "policy_v2.md", ws / "policy.md")
    dev = [json.loads(l) for l in open(a.cases or (Path(a.results_root) / "cases.jsonl")) if json.loads(l)["split"] == "dev"]
    with open(ws / "dev_cases.jsonl", "w") as f:
        for c in dev:
            f.write(json.dumps({"id": c["id"], "message": c["message"], "booking": c["booking"],
                                "correct_outcome": c["expected"]}) + "\n")
    (ws / "run_eval.py").write_text(RUN_EVAL.replace("MAXEV", str(a.max_evals)))
    task = a.task or TASK.format(max_evals=a.max_evals)
    (ws / "TASK.md").write_text(task)
    kp = secret / "key"
    kp.write_text("fake-key" if os.environ.get("EVAL_FAKE") == "1" else ek._key())
    a._task = task
    os.chmod(kp, 0o600)
    os.chmod(secret, 0o700)
    try:
        run(a, ws, outdir, settings_path := root / "settings.json", secret, home, root, dev, kp)
    finally:
        if kp.exists():
            kp.unlink()                          # our own temp key file, removed even if the run breaks


def run(a, ws, outdir, settings, secret, home, root, dev, kp):
    settings.write_text(json.dumps(settings_for(ws, secret), indent=1))
    task = a._task
    ledger = ek.Ledger(outdir / "ledger.jsonl", a.cap, a.results_root)
    need = a.agent_budget + a.max_evals * (0.45 if "haiku-4" in a.bot_model else 0.2)
    if ledger.total() + need > a.cap:
        sys.exit(f"not started: study total ${ledger.total():.2f} + this loop's worst case ${need:.2f} > cap ${a.cap:.2f}")
    stop = threading.Event()
    th = threading.Thread(target=serve_evals, args=(ws, outdir, ledger, stop, dev),
                          kwargs={"bot_model": a.bot_model, "max_evals": a.max_evals}, daemon=True)
    th.start()
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin:" + str(Path(sys.executable).parent), "TZ": "UTC", "LANG": "en_US.UTF-8",
           "CLAUDE_CONFIG_DIR": str(root / "claude-config"), "DISABLE_AUTOUPDATER": "1", "DISABLE_TELEMETRY": "1",
           "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [a.claude_bin, "-p", task, "--output-format", "stream-json", "--verbose", "--model", a.model,
           "--max-turns", str(a.max_turns), "--max-budget-usd", str(a.agent_budget), "--permission-mode", "acceptEdits",
           "--tools", "Bash,Read,Edit,Write", "--settings", str(settings), "--strict-mcp-config", "--disable-slash-commands",
           "--no-session-persistence"]
    (outdir / "command.json").write_text(json.dumps({"cmd": cmd, "cwd": str(ws), "task": task, "start_prompt": start_prompt(),
                                                     "settings": json.loads(settings.read_text())}, indent=1))
    t0 = time.time()
    with open(outdir / "stream.jsonl", "w") as so, open(outdir / "stderr.txt", "w") as se:
        p = subprocess.run(cmd, cwd=ws, env=env, stdout=so, stderr=se, stdin=subprocess.DEVNULL, timeout=4 * 3600)
    time.sleep(3)
    stop.set()
    th.join(timeout=30)
    kp.unlink()                                   # our own temp key file
    shutil.copy(ws / "prompt.md", outdir / "final_prompt.md")
    shutil.copytree(ws, outdir / "ws-final", ignore=shutil.ignore_patterns("dev_cases.jsonl"))
    res = None
    for line in (outdir / "stream.jsonl").read_text().splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "result":
            res = ev
    summary = {"name": a.name, "exit": p.returncode, "minutes": round((time.time() - t0) / 60, 1),
               "agent_cost_estimate_usd": (res or {}).get("total_cost_usd"), "turns": (res or {}).get("num_turns"),
               "evals": len(list((ws / "eval_results").glob("*.json"))), "study_total_usd": round(ledger.total(), 4)}
    ledger.add({"t": time.time(), "exp": outdir.name + "-agent", "tag": "claude-code total_cost_usd (client estimate)",
                "model": a.model, "usage": (res or {}).get("usage") or {}, "cost": float((res or {}).get("total_cost_usd") or 0),
                "fake": False})
    summary["study_total_usd"] = round(ledger.total(), 4)
    (outdir / "loop-summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
