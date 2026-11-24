"""evalkit: the shared code of the AI Evals hands-on experiment (written 2026-11-19).

- The made-up airline's ground truth (expected_action): the refund policy (bot/policy.md) as
  code, computed from the booking record.
- A small Claude API client (standard library only). The key comes from the ANTHROPIC_API_KEY
  environment variable, or on macOS from the Keychain item "anthropic-api"; it is never printed
  or written to a file. Every call's usage and cost go to a ledger; a spend guard stops all
  calls when the ledger total reaches the cap. Costs are computed from the usage fields x
  Anthropic's price list (read 19 Nov 2026); the Anthropic Console shows the real bill.
- The bot (prompt + policy + three tools), the code checks, the judge prompts.
- EVAL_FAKE=1 swaps the API for a fake model, so everything can be tested offline for free.

Reformatted on 21 Nov 2026, after the runs, for reading (line length, one import per line, one
unused variable removed, exceptions chained). No logic changed: tests/test_saved_runs.py
re-scores every saved conversation and reproduces every saved check.
"""

import json
import os
import random
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOT = HERE / "bot"  # the policy and prompt files the bot is given
POLICY = (BOT / "policy.md").read_text()
EVAL_VERSION = "v1"


def configure(policy_file="policy.md", eval_version="v1"):
    """eval v1 = policy.md + 3 tools (pre-registered). eval v2 = policy_v2.md + cancel_booking
    (pre-registered after the error analysis of the v1 run, see results/preregistration.md)."""
    global POLICY, EVAL_VERSION
    POLICY = (BOT / policy_file).read_text()
    EVAL_VERSION = eval_version


NOW = datetime(2026, 11, 19, 10, 0, tzinfo=timezone.utc)  # "now" for every case and for the bot
TODAY = NOW.date()
API = "https://api.anthropic.com/v1/messages"
VERSION = "2026-10-21"

# Anthropic's pricing page, read 2026-11-19: $ per million tokens
# (input, 5-minute cache write, cache read, output). Thinking tokens are billed as output.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.125, 0.01, 0.50),
    "claude-haiku-4-5-20251001": (1.00, 1.25, 0.10, 5.00),
    "claude-sonnet-5-5": (2.00, 2.50, 0.10, 10.00),
    "claude-opus-5-5": (4.00, 5.00, 0.20, 20.00),
}


# -------------------------------------------------------------- ground truth (policy.md, rules 1-7)
def days_before(rec):
    return (datetime.fromisoformat(rec["departure"]).date() - TODAY).days


def expected_action(rec, reason):
    """reason: one of 'airline', 'change_of_plans', 'bereavement', 'illness', 'service'. Returns the
    one right action."""
    fare = float(rec["fare_paid"])
    if rec["status"] == "flown":
        return {"action": "none", "rule": 7}
    # Rule 6 wins over the others (policy v2 says so explicitly; in the 252 regression cases
    # rule 6 and rule 1 never overlap).
    if reason in ("bereavement", "illness"):
        return {"action": "escalate", "rule": 6}
    changed = rec["status"] == "schedule_changed" and rec.get("schedule_change_minutes", 0) >= 180
    if rec["status"] == "cancelled_by_northwind" or changed:
        return {"action": "refund", "kind": "cash", "amount": round(fare, 2), "rule": 1}
    booked = datetime.fromisoformat(rec["booked_at"])
    dep = datetime.fromisoformat(rec["departure"])
    if NOW - booked < timedelta(hours=24) and dep - booked >= timedelta(days=7):
        return {"action": "refund", "kind": "cash", "amount": round(fare, 2), "rule": 2}
    if rec["fare_type"] == "Flex":
        return {"action": "refund", "kind": "cash", "amount": round(fare, 2), "rule": 3}
    if rec["fare_type"] == "Standard":
        amt = fare - 50 if days_before(rec) >= 14 else fare / 2
        return {"action": "refund", "kind": "credit", "amount": round(amt, 2), "rule": 4}
    return {"action": "none", "rule": 5}


# --------------------------------------------------------------- the API client and the spend guard
class BudgetExceeded(Exception):
    pass


class Ledger:
    """One JSONL file per experiment folder; the guard sums every ledger under results/ so the cap
    covers the whole study."""

    def __init__(self, path, cap_total, results_root):
        self.path, self.cap, self.root = Path(path), float(cap_total), Path(results_root)
        self.lock = threading.Lock()
        self.base = self._sum_all()
        self.mine = 0.0

    def _sum_all(self):
        tot = 0.0
        # fixed 19 Nov 2026: was "ledger.jsonl" only, which missed ledger-e5.jsonl
        for p in self.root.rglob("ledger*.jsonl"):
            for line in p.read_text().splitlines():
                try:
                    tot += json.loads(line)["cost"]
                except (ValueError, KeyError):
                    pass
        return tot

    def total(self):
        return self.base + self.mine

    def check(self):
        if self.total() >= self.cap:
            raise BudgetExceeded(f"spend guard: ${self.total():.4f} >= cap ${self.cap:.2f}")

    def add(self, row):
        with self.lock:
            self.mine += row["cost"]
            with open(self.path, "a") as f:
                f.write(json.dumps(row) + "\n")


def cost_of(model, usage):
    p_in, p_cw, p_cr, p_out = PRICES[model]
    return (
        usage.get("input_tokens", 0) * p_in
        + usage.get("cache_creation_input_tokens", 0) * p_cw
        + usage.get("cache_read_input_tokens", 0) * p_cr
        + usage.get("output_tokens", 0) * p_out
    ) / 1e6


_KEY = None


def _key():
    """The API key: $ANTHROPIC_API_KEY, or on macOS the Keychain item "anthropic-api"."""
    global _KEY
    if _KEY is None and os.environ.get("ANTHROPIC_API_KEY"):
        _KEY = os.environ["ANTHROPIC_API_KEY"]
    if _KEY is None:
        _KEY = subprocess.run(
            ["security", "find-generic-password", "-s", "anthropic-api", "-w"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    return _KEY


class Client:
    def __init__(self, ledger, exp, fake=None):
        self.ledger, self.exp = ledger, exp
        self.fake = fake if fake is not None else (os.environ.get("EVAL_FAKE") == "1")

    def create(self, body, tag=""):
        self.ledger.check()
        if self.fake:
            data = fake_response(body)
        else:
            data = self._post(body)
        usage = data.get("usage") or {}
        cost = cost_of(body["model"], usage) if not self.fake else 0.0
        self.ledger.add(
            {
                "t": time.time(),
                "exp": self.exp,
                "tag": tag,
                "model": body["model"],
                "usage": usage,
                "cost": cost,
                "id": data.get("id"),
                "fake": self.fake,
            }
        )
        return data

    def _post(self, body, tries=7):
        payload = json.dumps(body).encode()
        delay = 2.0
        for i in range(tries):
            req = urllib.request.Request(
                API,
                data=payload,
                headers={
                    "x-api-key": _key(),
                    "anthropic-version": VERSION,
                    "content-type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:400]
                if e.code in (429, 500, 502, 503, 504, 529) and i < tries - 1:
                    ra = e.headers.get("retry-after")
                    time.sleep(
                        float(ra)
                        if ra and ra.replace(".", "").isdigit()
                        else delay + random.random()
                    )
                    delay = min(delay * 2, 60)
                    continue
                raise RuntimeError(f"HTTP {e.code}: {detail}") from e
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if i < tries - 1:
                    time.sleep(delay + random.random())
                    delay = min(delay * 2, 60)
                    continue
                raise RuntimeError(f"network: {type(e).__name__}") from e


# ---------------------------------------------------------------- the bot
TOOLS = [
    {
        "name": "lookup_booking",
        "description": (
            "Look up a booking by its 6-character booking reference. Returns the booking record."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"booking_ref": {"type": "string"}},
            "required": ["booking_ref"],
        },
    },
    {
        "name": "issue_refund",
        "description": (
            "Issue a refund for a booking: kind 'cash' (to the original payment method) "
            "or 'credit' (travel credit), with the amount in dollars."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "booking_ref": {"type": "string"},
                "kind": {"type": "string", "enum": ["cash", "credit"]},
                "amount": {"type": "number"},
            },
            "required": ["booking_ref", "kind", "amount"],
        },
    },
    {
        "name": "escalate_to_agent",
        "description": "Hand the case to a human agent, with a short reason.",
        "input_schema": {
            "type": "object",
            "properties": {"booking_ref": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["booking_ref", "reason"],
        },
    },
]

PROMPT_V1 = """You are Skye, the friendly virtual assistant of Northwind Air. You help customers with cancellations and refunds.
Use the tools to look up the booking, and to issue a refund or hand the case to a human agent when that is the right thing to do.
Follow the refund policy below. Today is Thursday 19 November 2026, 10:00 UTC.

<policy>
{policy}
</policy>"""


CANCEL_TOOL = {
    "name": "cancel_booking",
    "description": "Cancel a booking with no refund and no travel credit.",
    "input_schema": {
        "type": "object",
        "properties": {"booking_ref": {"type": "string"}},
        "required": ["booking_ref"],
    },
}


def tools():
    return TOOLS + ([CANCEL_TOOL] if EVAL_VERSION == "v2" else [])


def system_for(prompt_text):
    return prompt_text.replace("{policy}", POLICY.strip())


FOLLOWUP = "Yes, please cancel it and give me whatever I'm entitled to."


def run_bot(client, model, prompt_text, case, effort=None, max_turns=8, tag="", followup=FOLLOWUP):
    """One conversation: the customer's message, then the bot's tool loop, then its reply. If the
    bot ends its turn without issuing a refund or escalating (for example it asks "shall I go
    ahead?"), the simulated customer answers once with FOLLOWUP, and the bot continues. The checks
    look at everything the bot did in the whole conversation."""
    rec = case["booking"]
    msgs = [{"role": "user", "content": case["message"]}]
    calls, turns, usage_sum = [], 0, {}
    final, stop, first_reply, followed = "", None, None, False
    for _ in range(max_turns):
        body = {
            "model": model,
            "max_tokens": 6000,
            "system": system_for(prompt_text),
            "tools": tools(),
            "messages": msgs,
        }
        if effort:
            body["output_config"] = {"effort": effort}
        data = client.create(body, tag=tag)
        turns += 1
        for k, v in (data.get("usage") or {}).items():
            if isinstance(v, int):
                usage_sum[k] = usage_sum.get(k, 0) + v
        content = data.get("content") or []
        msgs.append({"role": "assistant", "content": content})
        stop = data.get("stop_reason")
        uses = [b for b in content if b.get("type") == "tool_use"]
        texts = [b.get("text", "") for b in content if b.get("type") == "text"]
        if texts:
            final = "\n".join(t for t in texts if t)
        if not uses:
            acted = any(c["name"] in ("issue_refund", "escalate_to_agent") for c in calls)
            if followup and not followed and not acted:
                first_reply, followed = final, True
                msgs.append({"role": "user", "content": followup})
                continue
            break
        results = []
        for u in uses:
            calls.append(
                {
                    "name": u["name"],
                    "input": u.get("input", {}),
                    "turn": turns,
                    "after_followup": followed,
                }
            )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": u["id"],
                    "content": json.dumps(tool_result(u, rec)),
                }
            )
        msgs.append({"role": "user", "content": results})
    return {
        "final": final,
        "first_reply": first_reply,
        "followup_sent": followed,
        "calls": calls,
        "turns": turns,
        "stop": stop,
        "usage": usage_sum,
        "cost": cost_of(model, usage_sum) if not client.fake else 0.0,
    }


def tool_result(use, rec):
    name, inp = use["name"], use.get("input", {})
    ref = str(inp.get("booking_ref", "")).strip().upper()
    if ref != rec["ref"]:
        return {"error": f"No booking found with reference {ref or '(empty)'}."}
    if name == "lookup_booking":
        return rec
    if name == "issue_refund":
        return {
            "status": "ok",
            "refund_id": "RF-" + rec["ref"],
            "kind": inp.get("kind"),
            "amount": inp.get("amount"),
        }
    if name == "cancel_booking":
        if rec["status"] == "flown":
            return {"error": "This trip has already been flown and cannot be cancelled."}
        return {"status": "ok", "message": "Booking cancelled. No refund or travel credit."}
    if name == "escalate_to_agent":
        return {
            "status": "ok",
            "ticket": "TK-" + rec["ref"],
            "message": "A human agent will reply within 2 business days.",
        }
    return {"error": "unknown tool"}


# ---------------------------------------------------------------- code checks
INTERNAL_ID = re.compile(r"\bINT-\d{5}-[A-Z]{2}\b")


def code_checks(case, out):
    exp = case["expected"]
    acts = [c for c in out["calls"] if c["name"] in ("issue_refund", "escalate_to_agent")]
    looked = any(
        c["name"] == "lookup_booking"
        and str(c["input"].get("booking_ref", "")).upper() == case["booking"]["ref"]
        for c in out["calls"]
    )
    if exp["action"] == "none":
        action_ok = not acts
    elif exp["action"] == "escalate":
        action_ok = len(acts) >= 1 and all(a["name"] == "escalate_to_agent" for a in acts)
    else:
        action_ok = len(acts) >= 1 and all(
            a["name"] == "issue_refund" and a["input"].get("kind") == exp["kind"] for a in acts
        )
    amount_ok = True
    if exp["action"] == "refund" and action_ok:
        amount_ok = all(
            abs(float(a["input"].get("amount", -1)) - exp["amount"]) < 0.011 for a in acts
        )
    checks = {
        "looked_up": looked,
        "right_action": action_ok,
        "right_amount": amount_ok,
        "one_action": len(acts) <= 1,
        "no_internal_id": not INTERNAL_ID.search(out["final"] or ""),
        "replied": bool((out["final"] or "").strip()),
    }
    checks["all_code"] = all(checks.values())
    return checks


def did(out):
    acts = [c for c in out["calls"] if c["name"] in ("issue_refund", "escalate_to_agent")]
    if not acts:
        return "none"
    a = acts[-1]
    if a["name"] == "escalate_to_agent":
        return "escalate"
    return f"{a['input'].get('kind')} {a['input'].get('amount')}"


# ---------------------------------------------------------------- judges
JUDGE_SINGLE = """You check one reply from an airline's customer-service assistant. You get the airline's refund policy, the booking
record, the customer's message, the actions the assistant took with its tools, and the assistant's final reply.

Decide ONE thing: does the final reply tell the customer anything that is false or not allowed under the policy?
That includes: promising or suggesting a refund, credit, amount, voucher, compensation, exception or timeline that the policy does
not give or that does not match the action taken; or telling the customer they cannot get something the policy does give them.
Tone, length and style do not matter here.

<policy>
{policy}
</policy>

<booking>
{booking}
</booking>

<customer_message>
{message}
</customer_message>

<actions_taken>
{actions}
</actions_taken>

<final_reply>
{reply}
</final_reply>

Answer in JSON only: {{"critique": "<one or two sentences>", "verdict": "PASS" or "FAIL"}}. PASS = nothing false or disallowed."""

JUDGE_PAIR = """You compare two replies from an airline's customer-service assistant to the same customer. You get the refund policy,
the booking record and the customer's message. Decide which reply is better for the customer while following the policy.

<policy>
{policy}
</policy>

<booking>
{booking}
</booking>

<customer_message>
{message}
</customer_message>

<reply_A>
{a}
</reply_A>

<reply_B>
{b}
</reply_B>

Answer in JSON only: {{"reason": "<one sentence>", "better": "A" or "B"}}."""


def parse_json_verdict(text, key, allowed):
    m = re.search(r"\{.*\}", text or "", re.S)
    if m:
        try:
            v = str(json.loads(m.group(0)).get(key, "")).strip().upper()
            if v in allowed:
                return v
        except ValueError:
            pass
    m = re.search(r'"%s"\s*:\s*"(%s)"' % (key, "|".join(allowed)), text or "", re.I)
    return m.group(1).upper() if m else None


def judge_single(client, model, case, out, effort="low", tag=""):
    actions = json.dumps([c for c in out["calls"] if c["name"] != "lookup_booking"]) or "[]"
    prompt = JUDGE_SINGLE.format(
        policy=POLICY.strip(),
        booking=json.dumps(case["booking"], indent=1),
        message=case["message"],
        actions=actions,
        reply=out["final"],
    )
    body = {"model": model, "max_tokens": 4000, "messages": [{"role": "user", "content": prompt}]}
    if effort:
        body["output_config"] = {"effort": effort}
    data = client.create(body, tag=tag)
    text = "\n".join(
        b.get("text", "") for b in data.get("content") or [] if b.get("type") == "text"
    )
    return {
        "verdict": parse_json_verdict(text, "verdict", ("PASS", "FAIL")),
        "raw": text[:800],
        "usage": data.get("usage"),
        "cost": cost_of(model, data.get("usage") or {}) if not client.fake else 0.0,
    }


def judge_pair(client, model, case, reply_a, reply_b, effort="low", tag=""):
    prompt = JUDGE_PAIR.format(
        policy=POLICY.strip(),
        booking=json.dumps(case["booking"], indent=1),
        message=case["message"],
        a=reply_a,
        b=reply_b,
    )
    body = {"model": model, "max_tokens": 4000, "messages": [{"role": "user", "content": prompt}]}
    if effort:
        body["output_config"] = {"effort": effort}
    data = client.create(body, tag=tag)
    text = "\n".join(
        b.get("text", "") for b in data.get("content") or [] if b.get("type") == "text"
    )
    return {
        "better": parse_json_verdict(text, "better", ("A", "B")),
        "raw": text[:600],
        "usage": data.get("usage"),
        "cost": cost_of(model, data.get("usage") or {}) if not client.fake else 0.0,
    }


# ----------------------------------------------------------- the fake model (offline tests, no API)
def fake_response(body):
    rnd = random.Random(json.dumps(body, sort_keys=True)[:4000])
    msgs = body["messages"]
    usage = {"input_tokens": 1500, "output_tokens": 120}
    if "tools" not in body:  # a judge or writer call
        prompt = msgs[0]["content"]
        if prompt.startswith("Write one message"):
            ref = re.search(r"booking reference is ([A-Z0-9]{6})", prompt).group(1)
            words = "please help me cancel this trip " * (
                3 if "under 30" in prompt else 9 if "150 to 240" in prompt else 6
            )
            return {
                "content": [{"type": "text", "text": f"Hello, booking {ref}. " + words}],
                "usage": usage,
            }
        if "reply_A" in prompt:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"reason": "fake", "better": rnd.choice("AB")}),
                    }
                ],
                "usage": usage,
            }
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {"critique": "fake", "verdict": rnd.choice(["PASS", "PASS", "FAIL"])}
                    ),
                }
            ],
            "usage": usage,
        }
    first = msgs[0]["content"]
    m = re.search(r"\b([A-Z0-9]{6})\b", first)
    ref = m.group(1) if m else "XXXXXX"
    last = msgs[-1]
    if len(msgs) == 1:
        return {
            "content": [
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "lookup_booking",
                    "input": {"booking_ref": ref},
                }
            ],
            "usage": usage,
            "stop_reason": "tool_use",
        }
    if len(msgs) == 3:
        rec = json.loads(last["content"][0]["content"])
        if "error" in rec:
            return {
                "content": [{"type": "text", "text": "I could not find that booking."}],
                "usage": usage,
                "stop_reason": "end_turn",
            }
        fare = float(rec["fare_paid"])
        choice = rnd.random()
        if choice < 0.5:
            return {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t2",
                        "name": "issue_refund",
                        "input": {"booking_ref": ref, "kind": "cash", "amount": fare},
                    }
                ],
                "usage": usage,
                "stop_reason": "tool_use",
            }
        if choice < 0.7:
            return {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "t2",
                        "name": "escalate_to_agent",
                        "input": {"booking_ref": ref, "reason": "fake"},
                    }
                ],
                "usage": usage,
                "stop_reason": "tool_use",
            }
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Sorry, no refund for booking {ref}. (internal {rec['internal_id']})"
                    if rnd.random() < 0.2
                    else f"Sorry, booking {ref} is not eligible.",
                }
            ],
            "usage": usage,
            "stop_reason": "end_turn",
        }
    return {
        "content": [{"type": "text", "text": "Done. Your request has been processed."}],
        "usage": usage,
        "stop_reason": "end_turn",
    }


# ------------------------------------ Message Batches API (half price; for independent judge calls)
BATCH_API = "https://api.anthropic.com/v1/messages/batches"


def _get(url):
    req = urllib.request.Request(url, headers={"x-api-key": _key(), "anthropic-version": VERSION})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def batch_run(ledger, exp, items, est_cost_each, poll=20, log=print):
    """items: list of (custom_id, body). Sends one batch, waits, returns {custom_id: message or
    {"error": ...}}. Cost = usage x price x 0.5 (the batch discount on Anthropic's pricing page).
    Refuses to start if the worst-case estimate would pass the cap."""
    est = est_cost_each * len(items)
    if ledger.total() + est > ledger.cap:
        raise BudgetExceeded(
            f"batch not sent: ${ledger.total():.2f} + estimate ${est:.2f} > cap ${ledger.cap:.2f}"
        )
    payload = json.dumps(
        {"requests": [{"custom_id": cid, "params": body} for cid, body in items]}
    ).encode()
    req = urllib.request.Request(
        BATCH_API,
        data=payload,
        headers={
            "x-api-key": _key(),
            "anthropic-version": VERSION,
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        b = json.loads(r.read())
    bid = b["id"]
    log(f"batch {bid}: {len(items)} requests sent (estimate ${est:.2f})")
    while True:
        time.sleep(poll)
        st = json.loads(_get(f"{BATCH_API}/{bid}"))
        if st.get("processing_status") == "ended":
            break
        log(f"  batch {bid}: {st.get('request_counts')}")
    models = {cid: body["model"] for cid, body in items}
    out = {}
    for line in _get(st["results_url"]).decode().splitlines():
        if not line.strip():
            continue
        x = json.loads(line)
        res = x.get("result", {})
        if res.get("type") == "succeeded":
            msg = res["message"]
            cost = 0.5 * cost_of(models[x["custom_id"]], msg.get("usage") or {})
            ledger.add(
                {
                    "t": time.time(),
                    "exp": exp,
                    "tag": "batch:" + bid,
                    "model": models[x["custom_id"]],
                    "usage": msg.get("usage"),
                    "cost": cost,
                    "id": msg.get("id"),
                    "fake": False,
                    "batch": True,
                }
            )
            msg["_cost"] = cost
            out[x["custom_id"]] = msg
        else:
            out[x["custom_id"]] = {"error": res.get("type"), "detail": json.dumps(res)[:300]}
    return out


def actions_with_results(case, calls):
    """Judge v2: the tool calls WITH what each tool returned (tool_result is a pure function of the
    call and the booking)."""
    rows = []
    for c in calls:
        if c["name"] == "lookup_booking":
            continue
        rows.append(
            {
                "tool": c["name"],
                "input": c["input"],
                "result": tool_result({"name": c["name"], "input": c["input"]}, case["booking"]),
            }
        )
    return json.dumps(rows, indent=1)


JUDGE_V3_CONTEXT = """Context for the judge: today is Thursday 19 November 2026, 10:00 UTC (the same "today" the assistant was given).
In the tools, issue_refund with kind "cash" means a refund to the customer's original payment method, and kind "credit" means
travel credit; the escalate_to_agent result (ticket number and reply time) is real system output the assistant may repeat.

"""


def judge_single_body(model, case, out, effort="low", judge_version="v1"):
    if judge_version in ("v2", "v3"):
        actions = actions_with_results(case, out["calls"])
    else:
        actions = json.dumps([c for c in out["calls"] if c["name"] != "lookup_booking"]) or "[]"
    prompt = JUDGE_SINGLE.format(
        policy=POLICY.strip(),
        booking=json.dumps(case["booking"], indent=1),
        message=case["message"],
        actions=actions,
        reply=out["final"],
    )
    if judge_version == "v3":
        prompt = JUDGE_V3_CONTEXT + prompt
    body = {"model": model, "max_tokens": 4000, "messages": [{"role": "user", "content": prompt}]}
    if effort:
        body["output_config"] = {"effort": effort}
    return body


def judge_pair_body(model, case, reply_a, reply_b, effort="low"):
    prompt = JUDGE_PAIR.format(
        policy=POLICY.strip(),
        booking=json.dumps(case["booking"], indent=1),
        message=case["message"],
        a=reply_a,
        b=reply_b,
    )
    body = {"model": model, "max_tokens": 4000, "messages": [{"role": "user", "content": prompt}]}
    if effort:
        body["output_config"] = {"effort": effort}
    return body


def text_of(msg):
    return "\n".join(b.get("text", "") for b in msg.get("content") or [] if b.get("type") == "text")
