"""The policy as code: evalkit.expected_action, one test per rule of bot/policy.md, the edges the
hard cases probe, and every saved case."""

import json
import unittest
from datetime import timedelta
from pathlib import Path

import evalkit as ek

RESULTS = Path(__file__).resolve().parent.parent / "results"


def booking(
    fare_type="Saver",
    fare=200.0,
    status="scheduled",
    departs_in=timedelta(days=30),
    booked_ago=timedelta(days=40),
    change_minutes=None,
):
    """A booking record like the ones in results/cases.jsonl, relative to evalkit.NOW."""
    rec = {
        "fare_type": fare_type,
        "fare_paid": fare,
        "status": status,
        "departure": (ek.NOW + departs_in).isoformat(),
        "booked_at": (ek.NOW - booked_ago).isoformat(),
    }
    if change_minutes is not None:
        rec["schedule_change_minutes"] = change_minutes
    return rec


def refund(kind, amount, rule):
    return {"action": "refund", "kind": kind, "amount": amount, "rule": rule}


class TestRules(unittest.TestCase):
    def test_rule_1_cancelled_by_the_airline_is_a_full_cash_refund_on_every_fare(self):
        for fare_type in ("Saver", "Standard", "Flex"):
            rec = booking(fare_type, status="cancelled_by_northwind")
            self.assertEqual(ek.expected_action(rec, "airline"), refund("cash", 200.0, 1))

    def test_rule_1_needs_a_move_of_3_hours_or_more(self):
        moved = booking(status="schedule_changed", change_minutes=180)
        self.assertEqual(ek.expected_action(moved, "airline"), refund("cash", 200.0, 1))
        one_minute_short = booking(status="schedule_changed", change_minutes=179)
        self.assertEqual(
            ek.expected_action(one_minute_short, "airline"), {"action": "none", "rule": 5}
        )

    def test_rule_2_the_24_hour_rule(self):
        rec = booking(booked_ago=timedelta(hours=23), departs_in=timedelta(days=10))
        self.assertEqual(ek.expected_action(rec, "change_of_plans"), refund("cash", 200.0, 2))
        too_late = booking(booked_ago=timedelta(hours=25), departs_in=timedelta(days=10))
        self.assertEqual(
            ek.expected_action(too_late, "change_of_plans"), {"action": "none", "rule": 5}
        )

    def test_rule_2_needs_departure_at_least_7_days_after_booking(self):
        booked_ago = timedelta(hours=23)
        exactly_7 = booking(booked_ago=booked_ago, departs_in=timedelta(days=7) - booked_ago)
        self.assertEqual(ek.expected_action(exactly_7, "change_of_plans")["rule"], 2)
        just_under = booking(
            booked_ago=booked_ago, departs_in=timedelta(days=7, minutes=-1) - booked_ago
        )
        self.assertEqual(ek.expected_action(just_under, "change_of_plans")["rule"], 5)

    def test_rule_3_flex_is_a_full_cash_refund(self):
        rec = booking("Flex", fare=420.0)
        self.assertEqual(ek.expected_action(rec, "change_of_plans"), refund("cash", 420.0, 3))

    def test_rule_4_standard_14_days_or_more_is_credit_minus_50(self):
        rec = booking("Standard", fare=300.0, departs_in=timedelta(days=14))
        self.assertEqual(ek.expected_action(rec, "change_of_plans"), refund("credit", 250.0, 4))

    def test_rule_4_standard_under_14_days_is_half_as_credit(self):
        rec = booking("Standard", fare=300.0, departs_in=timedelta(days=13))
        self.assertEqual(ek.expected_action(rec, "change_of_plans"), refund("credit", 150.0, 4))

    def test_rule_4_counts_calendar_days(self):
        # 13 days and 14.5 hours away, but 14 calendar days from today's date: the fee rule applies
        departure_date_14 = timedelta(days=13, hours=14, minutes=30)
        self.assertEqual(ek.days_before(booking(departs_in=departure_date_14)), 14)

    def test_rule_5_saver_gets_nothing(self):
        self.assertEqual(
            ek.expected_action(booking("Saver"), "change_of_plans"), {"action": "none", "rule": 5}
        )

    def test_rule_6_bereavement_and_illness_go_to_a_human_on_every_fare(self):
        for fare_type in ("Saver", "Standard", "Flex"):
            for reason in ("bereavement", "illness"):
                rec = booking(fare_type)
                self.assertEqual(ek.expected_action(rec, reason), {"action": "escalate", "rule": 6})

    def test_rule_6_wins_over_rule_1(self):
        rec = booking(status="cancelled_by_northwind")
        self.assertEqual(ek.expected_action(rec, "bereavement"), {"action": "escalate", "rule": 6})

    def test_rule_7_a_flown_trip_gets_nothing_even_with_bereavement(self):
        rec = booking("Flex", status="flown", departs_in=timedelta(days=-3))
        self.assertEqual(ek.expected_action(rec, "bereavement"), {"action": "none", "rule": 7})


class TestSavedCases(unittest.TestCase):
    def test_every_saved_case_has_the_answer_the_code_gives(self):
        for name in ("cases.jsonl", "hard-cases.jsonl"):
            for line in (RESULTS / name).read_text().splitlines():
                case = json.loads(line)
                with self.subTest(case=case["id"]):
                    self.assertEqual(
                        ek.expected_action(case["booking"], case["reason"]), case["expected"]
                    )


if __name__ == "__main__":
    unittest.main()
