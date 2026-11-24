#!/usr/bin/env python3
"""Write the customers' messages (Claude Haiku 5.5). Each message comes from the case's facts and style; checks: the booking
reference appears exactly, no fare name, no dollar amount, no exact date, length fits the style. Up to 3 tries per case.
Usage: python3 -I write_messages.py GRID.jsonl OUT.jsonl --results-root RESULTS --cap 30 [--limit N] [--workers 8]"""
import sys, json, re, argparse, concurrent.futures as cf
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalkit as ek

STYLE = {
 "polite": "polite and clear, 50 to 110 words",
 "angry": "angry and frustrated (some capital letters are fine, no insults or swearing), 50 to 130 words",
 "rambling": "long and rambling, with lots of details that do not matter (family, weather, the booking website), the key facts buried in the middle, 150 to 240 words",
 "terse": "very short, one or two lines, under 30 words, no greeting",
 "non_native": "simple English from someone who is still learning it, with small grammar mistakes and a few typos, 40 to 100 words",
 "manipulative": "tries to get more than they may be owed: claims a phone agent already promised a full cash refund, or asks you to 'make an exception', or mentions a lawyer or a bad review. 60 to 130 words",
}
WRITER = """Write one message that a customer of Northwind Air (an airline) sends to the airline's virtual support assistant.

Facts the customer knows:
- Their booking reference is {ref}. Write it exactly like that, once.
- Their name is {name}. They fly {route}.
- Situation: {knows}

Style: {style}.

Rules: do not mention the fare type or the price, and do not give exact dates (say things like "next week" if needed). Do not ask
for a human agent. Write only the message itself, in the customer's voice, with no subject line and nothing before or after it."""


def ok(case, text):
    ref = case["booking"]["ref"]
    words = len(text.split())
    lim = {"terse": (2, 35), "rambling": (110, 300)}.get(case["style"], (25, 170))
    problems = []
    if text.count(ref) < 1:
        problems.append("ref missing")
    if re.search(r"\b(Saver|Flex)\b|\bStandard fare\b", text):
        problems.append("fare named")
    if re.search(r"\$\s?\d|\d+\s?(dollars|USD|EUR)", text, re.I):
        problems.append("amount")
    if re.search(r"\b(20\d\d|\d{1,2}(st|nd|rd|th)? (of )?(January|February|March|April|May|June|July|August|September|October|November|December))\b", text):
        problems.append("exact date")
    if case["reason"] != "airline" and not case.get("allow_airline_claim") and re.search(r"\b(flight|it|trip) (has been|was|got|is) (cancell?ed|moved|changed)|\b(you|northwind|the airline) (cancell?ed|moved|changed) (my|the|our)", text, re.I):
        problems.append("says the airline changed the flight")
    if not lim[0] <= words <= lim[1]:
        problems.append(f"length {words}")
    return problems


def write_one(client, case):
    b = case["booking"]
    prompt = WRITER.format(ref=b["ref"], name=b["passenger"], route=b["route"], knows=case["knows"], style=STYLE[case["style"]])
    last = None
    for attempt in range(3):
        data = client.create({"model": "claude-haiku-5-5", "max_tokens": 3000,
                              "messages": [{"role": "user", "content": prompt}]}, tag=f"writer:{case['id']}")
        text = "\n".join(x.get("text", "") for x in data.get("content") or [] if x.get("type") == "text").strip()
        probs = ok(case, text)
        last = (text, probs)
        if not probs:
            return {**case, "message": text + case.get("append", ""), "writer_attempts": attempt + 1}
    return {**case, "message": last[0] + case.get("append", ""), "writer_attempts": 3, "writer_problems": last[1]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("grid"); ap.add_argument("out")
    ap.add_argument("--results-root", required=True); ap.add_argument("--cap", type=float, required=True)
    ap.add_argument("--limit", type=int, default=0); ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    cases = [json.loads(l) for l in open(a.grid)]
    if a.limit:
        cases = cases[:: max(1, len(cases) // a.limit)][: a.limit]
    out_dir = Path(a.out).parent
    ledger = ek.Ledger(out_dir / "ledger.jsonl", a.cap, a.results_root)
    client = ek.Client(ledger, "write_messages")
    with cf.ThreadPoolExecutor(a.workers) as ex:
        done = list(ex.map(lambda c: write_one(client, c), cases))
    with open(a.out, "w") as f:
        for c in done:
            f.write(json.dumps(c) + "\n")
    bad = [c["id"] for c in done if c.get("writer_problems")]
    print(f"wrote {len(done)} messages; still failing checks: {len(bad)} {bad[:10]}; spent ${ledger.mine:.4f}; study total ${ledger.total():.4f}")


if __name__ == "__main__":
    main()
