"""The whole loop offline: scripts/run_bot.py with the fake model (EVAL_FAKE=1), then replay.py.
No API key, no cost."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestFakeRun(unittest.TestCase):
    def test_run_bot_and_replay_with_the_fake_model(self):
        env = dict(os.environ, EVAL_FAKE="1")
        env.pop("ANTHROPIC_API_KEY", None)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "fake-test"
            subprocess.run(
                [
                    sys.executable,
                    "scripts/run_bot.py",
                    "results/cases.jsonl",
                    str(out),
                    "--model",
                    "claude-haiku-5-5",
                    "--prompt",
                    "bot/prompt_v1.txt",
                    "--reps",
                    "1",
                    "--limit",
                    "4",
                    "--results-root",
                    tmp,
                    "--cap",
                    "1",
                    "--workers",
                    "2",
                ],
                cwd=ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            rows = [json.loads(line) for line in (out / "runs.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), 4)
            self.assertTrue(all("checks" in r for r in rows))
            replay = subprocess.run(
                [sys.executable, "replay.py", "conv", str(out), rows[0]["case"], "--delay", "0"],
                cwd=ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("Customer:", replay.stdout)


if __name__ == "__main__":
    unittest.main()
