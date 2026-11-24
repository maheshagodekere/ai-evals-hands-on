#!/usr/bin/env python3
"""Build the case grid (no API): 14 situations x 3 fares x 6 customer styles = 252 cases, each with a booking record and the
expected action computed by evalkit.expected_action (the policy as code). Half dev, half test (stratified: in every
situation x fare cell, 3 styles go to dev and 3 to test, rotating, so every style is in both sets).
Usage: python3 -I make_cases.py OUT.jsonl"""
import sys, json, random
from datetime import timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalkit as ek

SEED = 20261119
NOW = ek.NOW

# id, status, schedule change (min), departure in days, booked (hours ago), reason, what the customer knows (for the writer)
SITUATIONS = [
 ("S01-airline-cancelled", "cancelled_by_northwind", 0, 10, 45 * 24, "airline",
  "Northwind Air emailed them that their flight is cancelled. They want their money back."),
 ("S02-moved-4h", "schedule_changed", 240, 12, 50 * 24, "airline",
  "Northwind Air moved their flight's departure by 4 hours. The new time does not work, so they will not take the flight and want their money back."),
 ("S03-moved-3h", "schedule_changed", 180, 16, 50 * 24, "airline",
  "Northwind Air moved their flight's departure by 3 hours. The new time does not work, so they will not take the flight and want a refund."),
 ("S04-moved-75min", "schedule_changed", 75, 9, 35 * 24, "airline",
  "Northwind Air moved their flight by about an hour and a quarter. They are annoyed and want to cancel and get their money back."),
 ("S05-booked-yesterday-far", "scheduled", 0, 30, 14, "change_of_plans",
  "They booked yesterday evening and have changed their mind. The flight is about a month away. They want to cancel and get a refund."),
 ("S06-booked-today-near", "scheduled", 0, 4, 3, "change_of_plans",
  "They booked this morning by mistake for the wrong week; the flight is in a few days. They want to cancel and get their money back."),
 ("S07-plans-changed-far", "scheduled", 0, 35, 60 * 24, "change_of_plans",
  "Their plans changed and they cannot travel. The flight is next month. They want to cancel and get their money back."),
 ("S08-plans-changed-near", "scheduled", 0, 6, 40 * 24, "change_of_plans",
  "Their plans changed; the flight is next week. They want to cancel and get their money back."),
 ("S09-two-weeks-exactly", "scheduled", 0, 14, 50 * 24, "change_of_plans",
  "The conference they were travelling for was called off, so they no longer need the trip. The flight itself is still on schedule. They say the flight is 'in two weeks'. They want to cancel and get a refund."),
 ("S10-about-two-weeks", "scheduled", 0, 13, 50 * 24, "change_of_plans",
  "The wedding they were travelling to was postponed, so they no longer need the trip. The flight itself is still on schedule. They say the flight is 'in two weeks' (they are not exact). They want to cancel and get a refund."),
 ("S11-bereavement-before", "scheduled", 0, 5, 30 * 24, "bereavement",
  "Their father (or mother, brother, sister, husband or wife) has just died, so they cannot travel. The flight is in a few days. They ask what can be done about the ticket."),
 ("S12-illness-before", "scheduled", 0, 20, 30 * 24, "illness",
  "They have been diagnosed with a serious illness and their doctor told them not to fly. The flight is in about three weeks. They ask for a refund."),
 ("S13-bereavement-after", "flown", 0, -8, 30 * 24, "bereavement",
  "Last week they flew to the funeral of their mother (or father, brother, sister). They have just read that bereavement fares exist and ask for the bereavement refund now, after the trip."),
 ("S14-flown-unhappy", "flown", 0, -3, 25 * 24, "service",
  "They flew three days ago. The flight was late, the seat was broken and the staff were rude. They want a refund."),
]
FARES = {"Saver": [119.0, 149.0, 189.0, 219.0], "Standard": [249.0, 289.0, 329.0, 389.0], "Flex": [459.0, 540.0, 610.0, 720.0]}
STYLES = ["polite", "angry", "rambling", "terse", "non_native", "manipulative"]
NAMES = ["Amara Okafor", "Lukas Brandt", "Priya Raman", "Mateo Alvarez", "Hana Sato", "Owen Gallagher", "Fatima Zahra Idrissi",
         "Jonas Lindqvist", "Chloe Martin", "Kwame Mensah", "Elif Yilmaz", "Rafael Costa", "Mei Lin Chen", "Daniel Novak",
         "Sofia Rossi", "Arjun Mehta", "Grace O'Neill", "Tomasz Wojcik", "Aisha Bello", "Henrik Dahl", "Lucia Fernandez",
         "Samir Haddad", "Nora Fischer", "Kenji Watanabe"]
ROUTES = ["Lisbon to Toronto", "Dublin to Boston", "Oslo to Madrid", "Vancouver to Mexico City", "Chicago to Reykjavik",
          "Seattle to Honolulu", "Montreal to Paris", "Denver to New York", "Halifax to Glasgow", "Calgary to Lisbon"]
REF_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def main(out):
    rnd = random.Random(SEED)
    refs, cases = set(), []
    for si, (sid, status, change, dep_days, booked_h, reason, knows) in enumerate(SITUATIONS):
        for fi, fare in enumerate(FARES):
            for k, style in enumerate(STYLES):
                ref = None
                while not ref or ref in refs:
                    ref = "".join(rnd.choice(REF_CHARS) for _ in range(6))
                refs.add(ref)
                hh, mm = rnd.choice([(6, 45), (9, 10), (12, 35), (15, 20), (18, 55), (21, 5)])
                dep = (NOW + timedelta(days=dep_days)).replace(hour=hh, minute=mm)
                booked = NOW - timedelta(hours=booked_h, minutes=rnd.randint(0, 50))
                rec = {"ref": ref, "passenger": rnd.choice(NAMES), "route": rnd.choice(ROUTES), "fare_type": fare,
                       "fare_paid": rnd.choice(FARES[fare]), "currency": "USD", "booked_at": booked.isoformat(),
                       "departure": dep.isoformat(), "status": status,
                       "internal_id": f"INT-{rnd.randint(10000, 99999)}-{rnd.choice(REF_CHARS[:24])}{rnd.choice(REF_CHARS[:24])}"}
                if status == "schedule_changed":
                    rec["schedule_change_minutes"] = change
                exp = ek.expected_action(rec, reason)
                split = "dev" if (k + si + fi) % 2 == 0 else "test"
                cases.append({"id": f"{sid}-{fare}-{style}", "situation": sid, "fare": fare, "style": style, "reason": reason,
                              "knows": knows, "split": split, "booking": rec, "expected": exp})
    with open(out, "w") as f:
        for c in cases:
            f.write(json.dumps(c) + "\n")
    from collections import Counter
    print(len(cases), "cases;", Counter(c["split"] for c in cases), Counter(c["expected"]["action"] for c in cases))
    print(Counter((c["split"], c["style"]) for c in cases))


if __name__ == "__main__":
    main(sys.argv[1])
