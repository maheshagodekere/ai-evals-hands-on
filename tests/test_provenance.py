"""The code as it ran: results/preregistration.sha256 lists the SHA-256 of each file before each
run. The bot's files (bot/) and the scripts as they ran (results/code-as-run/) must match the last
hash listed for them.

evalkit.py is the one exception: it was changed once after the last run, to fix the spend guard
(Addendum 9 of results/preregistration.md; no API call was made after that).
"""

import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
WHERE = {  # a name in preregistration.sha256 -> the file in this repo
    "policy.md": ROOT / "bot" / "policy.md",
    "policy_v2.md": ROOT / "bot" / "policy_v2.md",
    "prompt_v1.txt": ROOT / "bot" / "prompt_v1.txt",
    "prompt_v2.txt": ROOT / "bot" / "prompt_v2.txt",
    "make_cases.py": RESULTS / "code-as-run" / "make_cases.py",
    "write_messages.py": RESULTS / "code-as-run" / "write_messages.py",
    "run_bot.py": RESULTS / "code-as-run" / "run_bot.py",
    "make_hard_cases.py": RESULTS / "code-as-run" / "make_hard_cases.py",
    "results/e9-loop1/final_prompt_for_bot.txt": RESULTS / "e9-loop1" / "final_prompt_for_bot.txt",
}


def last_hashes():
    last = {}
    for line in (RESULTS / "preregistration.sha256").read_text().splitlines():
        digest, name = line.split(None, 1)
        last[name.strip()] = digest
    return last


class TestProvenance(unittest.TestCase):
    def test_files_match_their_last_hash(self):
        last = last_hashes()
        self.assertEqual(set(last) - set(WHERE), {"evalkit.py"})
        for name, path in WHERE.items():
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), last[name])


if __name__ == "__main__":
    unittest.main()
