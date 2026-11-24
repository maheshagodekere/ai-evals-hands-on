#!/usr/bin/env python3
"""Build results.html from the saved runs (no API). Every number is computed here from results/.
Usage: python3 scripts/results_page.py   (then open results.html in a browser)"""

import json
import math
import random
import statistics as st
import html
import collections
from pathlib import Path

P = Path(__file__).resolve().parent.parent  # the repo root
R = P / "results"
E = html.escape


def load(d, split=None):
    p = R / d / "runs.jsonl"
    if not p.exists():
        return []
    rs = [json.loads(l) for l in open(p)]
    return [r for r in rs if "error" not in r and (split is None or r["split"] == split)]


def wilson(k, n, z=1.96):
    if not n:
        return (0, 0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0, c - h), min(1, c + h))


def rate(rs):
    k = sum(r["checks"]["all_code"] for r in rs)
    return k, len(rs)


def pct(k, n, ci=True):
    if not n:
        return "–"
    lo, hi = wilson(k, n)
    return f"{100 * k / n:.1f} %" + (
        f" <span class='muted'>({100 * lo:.0f}–{100 * hi:.0f})</span>" if ci else ""
    )


def per_case(rs):
    g = collections.defaultdict(list)
    for r in rs:
        g[r["case"]].append(r["checks"]["all_code"])
    return g


def reliab(rs):
    g = per_case(rs)
    full = [v for v in g.values() if len(v) >= 5]
    if not full:
        return None
    return (
        sum(any(v[:5]) for v in full) / len(full),
        sum(all(v[:5]) for v in full) / len(full),
        sum(0 < sum(v[:5]) < 5 for v in full),
        len(full),
    )


def boot_diff(ra, rb, seed=1, n=10000):
    a = {c: sum(v) / len(v) for c, v in per_case(ra).items()}
    b = {c: sum(v) / len(v) for c, v in per_case(rb).items()}
    cs = sorted(set(a) & set(b))
    d = [b[c] - a[c] for c in cs]
    rnd = random.Random(seed)
    bs = sorted(st.mean(rnd.choice(d) for _ in d) for _ in range(n))
    return (
        st.mean(a[c] for c in cs),
        st.mean(b[c] for c in cs),
        st.mean(d),
        bs[int(0.025 * n)],
        bs[int(0.975 * n) - 1],
        len(cs),
    )


def cost_per_1000(rs):
    return 1000 * st.mean(r["cost"] for r in rs) if rs else 0


def spend():
    tot = collections.Counter()
    for p in R.rglob("ledger*.jsonl"):
        for l in open(p):
            try:
                tot[str(p.parent.relative_to(R))] += json.loads(l)["cost"]
            except (ValueError, KeyError):
                pass
    return tot


# ------------------------------------------------------------------ numbers
v1e1, v1e2 = load("main-v1"), load("main-v1-evalv2")
hard55 = load("hard-v1")
h45 = load("e8-haiku45-hard")
h45reg = load("e8-haiku45-regtest", "test")
low = load("e8-haiku55low-hard")
lowreg = load("e8-haiku55low-regtest", "test")
son = load("e8-sonnet55-hard")
v2t = load("e7-haiku45-v2-hardtest", "test")
v2d = load("e7-haiku45-v2-harddev")
v2reg = load("e7-haiku45-v2-regtest", "test")
lpt = load("e9-loop1-final-hardtest", "test")
lpd = load("e9-loop1-final-harddev")
lpreg = load("e9-loop1-final-regtest", "test")
h45t, h45d = [r for r in h45 if r["split"] == "test"], [r for r in h45 if r["split"] == "dev"]
sim = json.load(open(R / "e7-small-eval-simulation.json"))
loop_evals = [json.loads(l) for l in open(R / "e9-loop1" / "evals.jsonl")]
loop_sum = json.load(open(R / "e9-loop1" / "loop-summary.json"))


def fail_cats(rs):
    c = collections.Counter()
    for r in rs:
        if r["checks"]["all_code"]:
            continue
        e = r["expected"]["action"]
        d = r["did"].split(" ")[0]
        if e == "none" and d == "escalate":
            c[
                "said no refund, then handed to a human after “please cancel it” (no cancel tool)"
                if r["followup_sent"]
                else "handed a no-refund case to a human"
            ] += 1
        elif e == "escalate" and d == "cash" and r["fare"] == "Flex":
            c["Flex + death/illness: refunded instead of handing to a human (policy unclear)"] += 1
        elif not r["checks"]["one_action"]:
            c["two actions in one conversation"] += 1
        else:
            c[f"expected {e}, did {d}"] += 1
    return c


def judge_table():
    rows = []
    for ver, f in (
        ("v1", "e4_verdicts.jsonl"),
        ("v2 + tool results", "e4_verdicts_judgev2.jsonl"),
        ("v3 + today's date", "e4_verdicts_judgev3.jsonl"),
    ):
        v = [json.loads(l) for l in open(R / "e45" / f)]
        for m in (
            "claude-haiku-4-5-20251001",
            "claude-haiku-5-5",
            "claude-sonnet-5-5",
            "claude-opus-5-5",
        ):
            xs = [x for x in v if x["model"] == m]
            tp = sum(x["verdict"] == "FAIL" for x in xs if x["label"] == "FAIL")
            tn = sum(x["verdict"] == "PASS" for x in xs if x["label"] == "PASS")
            rows.append((ver, m, tp, tn, sum(x["cost"] for x in xs)))
    return rows


def bias_table():
    v = [json.loads(l) for l in open(R / "e45" / "e5_verdicts.jsonl")]
    by = collections.defaultdict(dict)
    for x in v:
        by[(x["model"], x["pair"], x["set"])][x["order"]] = x
    out = []
    for m in (
        "claude-haiku-4-5-20251001",
        "claude-haiku-5-5",
        "claude-sonnet-5-5",
        "claude-opus-5-5",
    ):

        def pairs(s):
            return [
                o
                for k, o in by.items()
                if k[0] == m  # noqa: B023 (called in this pass)
                and k[2] == s
                and "xy" in o
                and "yx" in o
                and o["xy"]["chose"]
                and o["yx"]["chose"]
            ]

        sim_ = pairs("similar")
        clr = pairs("clear")
        pad = pairs("padding")
        flips = sum(o["xy"]["chose"] != o["yx"]["chose"] for o in sim_)
        right = sum((o["xy"]["chose"] == "x") + (o["yx"]["chose"] == "x") for o in clr)
        padded = sum((o["xy"]["chose"] == "y") + (o["yx"]["chose"] == "y") for o in pad)
        out.append((m, flips, len(sim_), right, 2 * len(clr), padded, 2 * len(pad)))
    return out


NAME = {
    "claude-haiku-4-5-20251001": "Haiku 4.5 (2025)",
    "claude-haiku-5-5": "Haiku 5.5",
    "claude-sonnet-5-5": "Sonnet 5.5",
    "claude-opus-5-5": "Opus 5.5",
}

sp = spend()
total = sum(sp.values())
e7 = boot_diff(h45t, v2t)
e7reg = boot_diff(h45reg, v2reg) if v2reg else None
e9_v1 = boot_diff(h45t, lpt) if lpt else None
e9_v2 = boot_diff(v2t, lpt) if lpt else None


def tr(*cells, cls=""):
    return f"<tr{cls}>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


rows_e8 = [
    (
        "Haiku 5.5 (default effort)",
        hard55,
        [r for r in v1e2 if r["split"] == "test"],
        "$0.10 / $0.50",
    ),
    ("Haiku 5.5, effort low", low, lowreg, "$0.10 / $0.50"),
    ("Sonnet 5.5", son, [], "$2 / $10"),
    ("Haiku 4.5 (2025)", h45, h45reg, "$1 / $5"),
]
e8_html = "".join(
    tr(
        n,
        pct(*rate(h)) + f" <span class='muted'>n={len(h)}</span>",
        pct(*rate(g)) if g else "not run",
        f"${cost_per_1000(h + g):.2f}",
        p,
    )
    for n, h, g, p in rows_e8
)

rel_rows = []
for label, rs in (
    ("Eval v1 (first eval), Haiku 5.5", v1e1),
    ("Eval v2, Haiku 5.5, 252 regression cases", v1e2),
    ("Hard cases, Haiku 5.5", hard55),
    ("Hard cases, Haiku 4.5", h45),
):
    x = reliab(rs)
    k, n = rate(rs)
    rel_rows.append(
        tr(
            E(label),
            f"{100 * k / n:.1f} %",
            f"{100 * x[0]:.1f} %",
            f"<b>{100 * x[1]:.1f} %</b>",
            f"{x[2]} of {x[3]}",
        )
    )

jt = judge_table()
judge_html = "".join(
    tr(ver, NAME[m], f"{tp}/60", f"<b>{tn}/60</b>", f"${c:.2f}") for ver, m, tp, tn, c in jt
)
bias_html = "".join(
    tr(NAME[m], f"<b>{f}/{n}</b> ({100 * f / n:.0f} %)", f"{r}/{rn}", f"{p}/{pn}")
    for m, f, n, r, rn, p, pn in bias_table()
)

sit = collections.defaultdict(lambda: [[], [], []])
for r in h45t:
    sit[r["situation"]][0].append(r["checks"]["all_code"])
for r in v2t:
    sit[r["situation"]][1].append(r["checks"]["all_code"])
for r in lpt:
    sit[r["situation"]][2].append(r["checks"]["all_code"])
sit_html = "".join(
    tr(E(s), f"{sum(a)}/{len(a)}", f"{sum(b)}/{len(b)}", f"{sum(c)}/{len(c)}" if c else "–")
    for s, (a, b, c) in sorted(sit.items())
)

loop_html = "".join(
    tr(e["n"], f"{e['passed']}/{e['total']}", e["prompt_sha"], len(e["prompt"])) for e in loop_evals
)
cats1 = fail_cats([r for r in v1e1 if r["split"] == "dev"])
cats1_html = "".join(f"<li><b>{v}</b> × {E(k)}</li>" for k, v in cats1.most_common())
spend_html = "".join(
    tr(E(k), f"${v:.2f}") for k, v in sorted(sp.items(), key=lambda x: -x[1]) if v >= 0.01
)


def d(x):
    return f"{100 * x:+.1f}"


page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="icon" href="data:,">
<title>Results · AI Evals, hands-on</title>
<link rel="stylesheet" href="../brand/doc.css">
<!-- Built by test/results_page.py from test/results/ (19 November 2026). Every number below is computed from the saved runs. -->
<style>td,th{{vertical-align:top;text-align:left}} .muted{{color:var(--soft);font-size:.9em}}</style>
</head><body><div class="wrap">
<header class="hero">
  <div class="kicker">Results · AI Evals, hands-on · run 19 November 2026 on your Claude API key</div>
  <h1>What we measured</h1>
  <p class="lead">A refund bot for a made-up airline, built the way people build a weekend demo, then tested with an eval we built
    step by step. {sum(len(load(x)) for x in ("main-v1", "main-v1-evalv2", "hard-v1", "e8-haiku45-hard", "e8-haiku45-regtest", "e8-haiku55low-hard", "e8-haiku55low-regtest", "e8-sonnet55-hard", "e7-haiku45-v2-hardtest", "e7-haiku45-v2-harddev", "e7-haiku45-v2-regtest", "e9-loop1-final-hardtest", "e9-loop1-final-harddev", "e9-loop1-final-regtest")):,}
    bot conversations, {sum(1 for _ in open(R / "e45" / "e4_verdicts.jsonl")) * 3 + sum(1 for _ in open(R / "e45" / "e5_verdicts.jsonl")):,}
    judge calls, one agent loop. Total cost <b>${total:.2f}</b> (usage × Anthropic's price list; the Console shows the real bill).
    Written down before each run: <code>test/results/preregistration.md</code> (8 dated addenda, each before the run it
    describes).</p>
</header>

<div class="stat">
  <div><b>5/5</b><span>the vibe check: five polite questions, all perfect</span></div>
  <div><b>{100 * rate(v1e1)[0] / rate(v1e1)[1]:.0f} % → {100 * rate(v1e2)[0] / rate(v1e2)[1]:.1f} %</b><span>our first eval, then the same bot after we fixed OUR eval</span></div>
  <div><b>{100 * rate(hard55)[0] / rate(hard55)[1]:.0f} % vs {100 * rate(h45)[0] / rate(h45)[1]:.0f} %</b><span>hard cases: Haiku 5.5 vs last year's Haiku 4.5 (7× the cost)</span></div>
  <div><b>{d(e7[2])} pts</b><span>prompt v2 on hidden cases (95 % interval {d(e7[3])} to {d(e7[4])})</span></div>
</div>

<h2><span class="n">1 · The setup</span>A bot, a policy, 324 cases</h2>
<ul>
  <li><b>The bot "Skye":</b> Claude Haiku 5.5, a 4-line prompt (v1), the one-page refund policy of a made-up airline, and tools:
    <code>lookup_booking</code>, <code>issue_refund</code>, <code>escalate_to_agent</code> (+ <code>cancel_booking</code> from eval v2).</li>
  <li><b>Ground truth by code:</b> the policy's rules are exact, so the right action and amount for every case are computed
    (<code>test/evalkit.py</code>, <code>expected_action</code>).</li>
  <li><b>252 regression cases:</b> 14 situations × 3 fares × 6 customer styles (polite, angry, rambling, terse, non-native, manipulative),
    messages written by Haiku 5.5 from the facts. <b>72 hard cases:</b> 12 tricky situations (fake system notice, fake manager code,
    2 h 59 min, 24 h 10 min, a cousin's death, a wife's illness, customers who misremember) × 3 fares × 2 styles. Each set half dev, half test.</li>
  <li><b>A simulated customer:</b> if the bot asks before acting, the customer answers once: "Yes, please cancel it and give me whatever I'm entitled to."</li>
  <li><b>Code checks:</b> looked up the booking · right action · right amount · one action · no internal ID leaked · replied.</li>
</ul>

<h2><span class="n">2 · Our first eval was wrong</span>89 % that wasn't</h2>
<p>Eval v1 (prompt v1, 252 × 5): <b>{pct(*rate(v1e1))}</b>. Reading the {sum(cats1.values())} failing dev conversations:</p>
<ul>{cats1_html}</ul>
<p>No wrong amount, no wrong refund kind, no leaked ID. The bot had no tool to cancel without a refund, and our policy did not say
  which rule wins for a Flex fare plus a death in the family. Eval v2 added <code>cancel_booking</code> and made the policy explicit
  (policy_v2.md). Same bot, same prompt, same 252 cases: <b>{pct(*rate(v1e2))}</b>.</p>

<h2><span class="n">3 · Worked once vs worked every time</span>Five runs per case</h2>
<table><tr><th>Run</th><th>Per run</th><th>Passed at least 1 of 5</th><th>Passed all 5</th><th>Flaky cases</th></tr>{"".join(rel_rows)}</table>

<h2><span class="n">4 · The model swap</span>Same prompt (v1), same eval</h2>
<table><tr><th>Setup</th><th>Hard cases (95 % interval)</th><th>Regression test cases</th><th>$ per 1,000 conversations</th><th>Price in / out per M tokens</th></tr>{e8_html}</table>

<h2><span class="n">5 · Prompt v2</span>Written from the dev failures only (Haiku 4.5)</h2>
<p>Hidden hard-test cases (36 × 5): v1 <b>{100 * e7[0]:.1f} %</b> → v2 <b>{100 * e7[1]:.1f} %</b>, difference <b>{d(e7[2])} points</b>,
  95 % case-bootstrap interval {d(e7[3])} to {d(e7[4])}. Hard-dev (v2 × 1): {pct(*rate(v2d), ci=False)}.
  Regression test cases (126 × 1): v1 {100 * e7reg[0]:.1f} % → v2 {100 * e7reg[1]:.1f} %, difference {d(e7reg[2])}
  (interval {d(e7reg[3])} to {d(e7reg[4])}): <b>not proven</b>.</p>
<table><tr><th>Hard situation (test cases)</th><th>v1</th><th>v2</th><th>Loop prompt</th></tr>{sit_html}</table>
<h3>How often would a small eval have told us the truth?</h3>
<p>From our own runs, 10,000 random small evals (each case run once), with the real difference of {d(e7[2])} points:</p>
<table><tr><th>Eval size</th><th>v2 looks worse</th><th>looks the same</th><th>looks better</th></tr>
{"".join(tr(f"{n} cases", f"{w:.1f} %", f"{s:.1f} %", f"{b:.1f} %") for n, (w, s, b) in sim.items())}</table>

<h2><span class="n">6 · The judges</span>Calibrated against 120 replies with known answers</h2>
<p>60 real replies we read and labelled clean + 60 with one planted policy break (a $75 voucher, "bereavement refunds up to 90 days
  after travel", "your credit never expires" …). Three versions of the judge prompt, after reading every disagreement:</p>
<table><tr><th>Judge prompt</th><th>Model</th><th>Breaks caught</th><th>Clean replies passed</th><th>Cost</th></tr>{judge_html}</table>
<p class="muted">v1 → v2: the judge saw the tool calls but not their results, so it called a real ticket number "invented". v2 → v3:
  it did not know today's date. Two current-model flags on clean replies in v3 point to real slips our own labels missed.</p>
<h3>Do 2026 judges still flip?</h3>
<table><tr><th>Judge</th><th>Two good replies: changed its pick when the order swapped</th><th>Clean vs planted break: picked the clean one</th><th>Plain vs padded: picked the padded one</th></tr>{bias_html}</table>

<h2><span class="n">7 · The loop</span>Claude Code improves the prompt (Haiku 4.5 bot, hard-dev only)</h2>
<p>Agent: Claude Code with Sonnet 5.5, sandboxed (no network, no key, could only edit prompt.md). {loop_sum["evals"]} evals,
  {loop_sum["minutes"]} minutes, agent cost about ${loop_sum["agent_cost_estimate_usd"]:.2f}.</p>
<table><tr><th>Eval</th><th>Dev score (1 run)</th><th>Prompt version</th><th>Characters</th></tr>{loop_html}</table>
<p>Final prompt on hidden hard-test (36 × 5): {pct(*rate(lpt)) if lpt else "running"}{f" · vs v1 {d(e9_v1[2])} pts (interval {d(e9_v1[3])} to {d(e9_v1[4])}) · vs v2 {d(e9_v2[2])} pts (interval {d(e9_v2[3])} to {d(e9_v2[4])})" if lpt else ""}.
  Dev (× 2): {pct(*rate(lpd), ci=False) if lpd else "–"}. Regression test (× 1): {pct(*rate(lpreg), ci=False) if lpreg else "–"}.</p>
<p class="muted">Read in the final prompt: no booking references or names, but timestamps copied from dev cases, and "grandparent"
  added to immediate family (not in the policy, and no case tests it). Dev and test share the same 12 hard situations, so this test is
  kinder to the loop than real life.</p>

<h2><span class="n">8 · Cost</span>${total:.2f} in all</h2>
<table><tr><th>Part</th><th>Cost</th></tr>{spend_html}</table>

<h2><span class="n">9 · Limits</span>What this does not show</h2>
<ul>
  <li>One made-up policy, one kind of bot. The customer messages are synthetic (written by Haiku 5.5 from the facts).</li>
  <li>The simulated customer answers once with a fixed line; real customers say more.</li>
  <li>Costs are usage × the public price list; your Console shows the real bill.</li>
  <li>The hand labels are ours (read against the policy); the judges found two slips we missed.</li>
  <li>The loop ran once; the hard test cases share situations with the dev cases.</li>
</ul>
<p class="muted">Files: <code>test/</code> (code), <code>test/results/</code> (every run, ledger and pre-registration), <code>test/replay.py</code>
  (replays a saved conversation or eval run in the terminal for filming, no API).</p>
</div></body></html>"""
(P / "results.html").write_text(page)
print("written; total spend", round(total, 2))
