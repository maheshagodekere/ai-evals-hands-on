#!/usr/bin/env python3
"""Replay saved results in the terminal: no API call, no key, nothing spent. It only prints
what is already saved in results/.

  python3 replay.py conv RUNS_DIR CASE_ID [--rep 0] [--delay 0.9]
      one conversation, step by step, with its code checks
  python3 replay.py eval RUNS_DIR [--rep 0] [--speed 0.04] [--split dev]
      a whole eval run: one line per case, with a live score
  python3 replay.py eval RUNS_DIR --all-runs [...]
      all five runs of every case (e.g. 252 cases x 5 = 1,260 conversations)

Example: python3 replay.py conv results/main-v1 S10-about-two-weeks-Standard-polite
"""

import sys
import json
import time
import argparse
import textwrap
from pathlib import Path


def fill_keep_lines(text, width=100):
    """Wrap each line of a reply on its own, so the bot's lists and paragraphs keep their shape (2026-11-21: textwrap.fill
    joined them into one block). A list item's continuation lines are indented under its text."""
    out = []
    for line in text.strip().split("\n"):
        if not line.strip():
            if out and out[-1] != "":
                out.append("")
            continue
        lead = len(line) - len(line.lstrip())
        body = line.strip()
        hang = lead + (
            2 if body[:2] in ("- ", "* ") else 3 if body[:1].isdigit() and body[1:3] == ". " else 0
        )
        out += textwrap.wrap(
            " ".join(body.split()), width, initial_indent=" " * lead, subsequent_indent=" " * hang
        ) or [""]
    return "\n".join(out)


B, D, G, R, Y, C, X = (
    "\033[1m",
    "\033[2m",
    "\033[32m",
    "\033[31m",
    "\033[33m",
    "\033[36m",
    "\033[0m",
)


def typed(text, cps=220):
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(1 / cps)
    print()


def load(runs_dir):
    rows = [json.loads(l) for l in open(Path(runs_dir) / "runs.jsonl")]
    return [r for r in rows if "error" not in r]


def conv(a):
    rows = load(a.runs_dir)
    r = next(x for x in rows if x["case"] == a.case and x["rep"] == a.rep)
    cases = {}
    for name in ("cases.jsonl", "hard-cases.jsonl"):  # the regression set and the hard set
        for f in (
            Path(a.runs_dir).parent / name,
            Path(__file__).resolve().parent / "results" / name,
        ):
            if f.exists():
                cases.update({json.loads(l)["id"]: json.loads(l) for l in open(f)})
                break
    c = cases[a.case]
    print(f"{D}case {a.case} · run {a.rep} · model {r['model']}{X}\n")
    print(f"{C}{B}Customer:{X}")
    typed(textwrap.fill(c["message"], 100))
    time.sleep(a.delay)

    def show_calls(calls):
        for call in calls:
            # the whole tool input, wrapped (cutting it short hid quoted text)
            n = len(call["name"]) + 2
            parts = textwrap.wrap(
                "(" + json.dumps(call["input"]) + ")",
                100,
                initial_indent=" " * n,
                subsequent_indent="    ",
            )
            print(f"\n{Y}● {call['name']}{X}{D}{parts[0][n:]}{X}")
            for part in parts[1:]:
                print(f"{D}{part}{X}")
            time.sleep(a.delay)
            if call["name"] == "lookup_booking":
                b = c["booking"]
                print(
                    f"{D}  fare {b['fare_type']} · paid ${b['fare_paid']:.2f} · departs {b['departure'][:10]} · status {b['status']}{X}"
                )
                time.sleep(a.delay)

    known = all("after_followup" in x for x in r["calls"])
    if known:
        before = [x for x in r["calls"] if not x.get("after_followup")]
        after = [x for x in r["calls"] if x.get("after_followup")]
    elif r.get("followup_sent"):
        # main-v1 and main-v1-evalv2 did not save which calls came after the customer's "yes". The
        # order follows from the rule in evalkit.run_bot (and the pre-registration): the customer
        # says "yes" only if the bot ended its turn WITHOUT refunding or escalating, so those calls
        # came after it. In every run that did save the order (hard-v1, e8-*), lookups came before
        # and every other call after, with no exception.
        before = [x for x in r["calls"] if x["name"] == "lookup_booking"]
        after = [x for x in r["calls"] if x["name"] != "lookup_booking"]
    else:
        before, after = r["calls"], []
    show_calls(before)
    if r.get("followup_sent") and r.get("first_reply"):
        print(f"\n{B}Skye:{X}")
        typed(fill_keep_lines(r["first_reply"]), 400)  # the whole reply, never cut short
        print(f"\n{C}{B}Customer:{X} Yes, please cancel it and give me whatever I'm entitled to.")
        time.sleep(a.delay)
        show_calls(after)
    print(f"\n{B}Skye:{X}")
    typed(fill_keep_lines(r["final"]), 400)  # the whole reply, never cut short
    time.sleep(a.delay)
    if a.no_checks:  # a vibe check: read by eye, no eval
        return
    e = r["expected"]
    exp = e["action"] + (f" {e['kind']} ${e['amount']:.2f}" if e["action"] == "refund" else "")
    print(
        f"\n{B}The eval:{X} expected {B}{exp}{X} (policy rule {e.get('rule')}) · the bot did {B}{r['did']}{X}"
    )
    for k, v in r["checks"].items():
        if k != "all_code":
            print(f"  {G + '✓' if v else R + '✗'}{X} {k.replace('_', ' ')}")
            time.sleep(a.delay / 3)
    print(f"\n{B}{G + 'PASS' if r['checks']['all_code'] else R + 'FAIL'}{X}")


def run_eval(a):
    rows = [
        r
        for r in load(a.runs_dir)
        if (a.all_runs or r["rep"] == a.rep) and (a.split == "all" or r["split"] == a.split)
    ]
    rows.sort(key=lambda r: (r["rep"], r["case"]))
    ok = 0
    what = (
        f"{len(rows)} conversations ({len(rows) // len({r['rep'] for r in rows})} cases × {len({r['rep'] for r in rows})} runs)"
        if a.all_runs
        else f"{len(rows)} cases"
    )
    print(f"{B}Running the eval: {what}{X}  {D}({Path(a.runs_dir).name}){X}\n")
    for i, r in enumerate(rows, 1):
        p = r["checks"]["all_code"]
        ok += p
        mark = f"{G}✓{X}" if p else f"{R}✗{X}"
        extra = "" if p else f"  {D}expected {r['expected']['action']}, did {r['did']}{X}"
        run = f" {D}run {r['rep'] + 1}{X}" if a.all_runs else ""
        print(f"{mark} {r['case']:<46}{run}{extra}")
        sys.stdout.write(f"\r{D}{ok}/{i} passed ({100 * ok / i:.1f} %){X}\n")
        time.sleep(a.speed)
    print(f"\n{B}Pass rate: {ok}/{len(rows)} = {100 * ok / len(rows):.1f} %{X}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["conv", "eval"])
    ap.add_argument("runs_dir")
    ap.add_argument("case", nargs="?")
    ap.add_argument("--rep", type=int, default=0)
    ap.add_argument("--delay", type=float, default=0.9)
    ap.add_argument("--speed", type=float, default=0.04)
    ap.add_argument("--split", default="all")
    ap.add_argument("--all-runs", action="store_true")
    ap.add_argument(
        "--no-checks",
        action="store_true",
        help="conv: stop after the reply (a vibe check, read by eye)",
    )
    a = ap.parse_args()
    conv(a) if a.cmd == "conv" else run_eval(a)
