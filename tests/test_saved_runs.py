"""Re-score every saved conversation with today's code: code_checks() must give the same six
checks that were saved when each run was made.

This is how the reformat of evalkit.py (21 Nov 2026, after the runs) was checked: no result changed.
"""

import json
import unittest
from pathlib import Path

import evalkit as ek

RESULTS = Path(__file__).resolve().parent.parent / "results"


def load_cases():
    cases = {}
    for name in ("cases.jsonl", "hard-cases.jsonl"):
        for line in (RESULTS / name).read_text().splitlines():
            case = json.loads(line)
            cases[case["id"]] = case
    return cases


class TestSavedRuns(unittest.TestCase):
    def test_code_checks_reproduce_every_saved_run(self):
        cases = load_cases()
        runs = sorted(RESULTS.rglob("runs.jsonl"))
        self.assertGreater(len(runs), 10)
        scored, different = 0, []
        for path in runs:
            for line in path.read_text().splitlines():
                row = json.loads(line)
                if "error" in row or "checks" not in row or row.get("case") not in cases:
                    continue
                case = dict(cases[row["case"]], expected=row["expected"])
                checks = ek.code_checks(case, {"calls": row["calls"], "final": row["final"]})
                if checks != row["checks"]:
                    different.append(f"{path.parent.name} {row['case']} run {row.get('rep')}")
                scored += 1
        self.assertGreater(scored, 4000)
        self.assertEqual(
            different, [], f"{len(different)} of {scored} conversations score differently"
        )


if __name__ == "__main__":
    unittest.main()
