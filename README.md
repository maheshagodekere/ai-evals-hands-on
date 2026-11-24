# AI Evals Hands-On: My First Eval Was Wrong

The code and every saved run behind the video *AI Evals Hands-On: My First Eval Was Wrong* on
[my YouTube channel](https://www.youtube.com/@maheshagodekere).

I built a small customer-service bot, Skye, for a made-up airline, Northwind Air. Skye handles
cancellations and refunds with three tools and a one-page refund policy. Then I built an eval for
it: 252 test cases, every case run five times, six checks written in code, and LLM judges. My
first eval was wrong. Everything is here, so you can check every number yourself, and then build
your own.

## Contents

1. [Quick start — two ways to run](#1-quick-start--two-ways-to-run)
2. [Requirements and setup](#2-requirements-and-setup)
3. [What is inside](#3-what-is-inside)
4. [How the bot and the eval work](#4-how-the-bot-and-the-eval-work)
5. [The experiment, step by step](#5-the-experiment-step-by-step)
6. [The results](#6-the-results)
7. [Run it yourself](#7-run-it-yourself)
8. [Command reference](#8-command-reference)
9. [Data formats](#9-data-formats)
10. [Tests](#10-tests)
11. [Troubleshooting](#11-troubleshooting)
12. [Honest limits](#12-honest-limits)
13. [Provenance](#13-provenance)
14. [License](#14-license)

## 1. Quick start — two ways to run

A live AI bot always calls a model API. Every real Claude conversation from the video (1,260+ runs) is saved in `results/`, so you can replay and re-score everything locally before spending anything — or plug in your own `ANTHROPIC_API_KEY` to run live experiments.

| Mode | Needs API key? | What you can run |
|---|---|---|
| **1. Offline replay & re-scoring** | **No** ($0) | Replay any saved Claude conversation or full 1,260-run eval from `results/` with `replay.py`, inspect prompt diffs, and run all 16 unit tests that re-score every saved trace. |
| **2. Live LLM bot & judge runs** | **Yes** (`ANTHROPIC_API_KEY`) | Run live bot conversations (`scripts/run_bot.py`) and LLM judges (`scripts/judges.py`) with a hard dollar spend cap (`--cap`). |

Clone once (Python 3.10+, standard library only — nothing to install):

```sh
git clone https://github.com/maheshagodekere/ai-evals-hands-on.git
cd ai-evals-hands-on
```

### Way 1: Without an API key (replay saved Claude runs & re-score locally)

```sh
# 1. Replay one saved Claude conversation, step by step, with its six code checks
python3 replay.py conv results/main-v1 S10-about-two-weeks-Standard-polite

# 2. Replay an entire saved eval run: 252 cases x 5 runs = 1,260 saved conversations
python3 replay.py eval results/main-v1 --all-runs

# 3. Run the unit tests: re-score every saved conversation locally with today's code
python3 -m unittest
```

### Way 2: With an Anthropic API key (run live Claude models)

```sh
export ANTHROPIC_API_KEY="your-key-here"

# Small live run: 10 cases x 1 run on Claude Haiku 5.5 with a $1 hard spend cap
python3 scripts/run_bot.py results/cases.jsonl runs/my-first-run \
    --model claude-haiku-5-5 --prompt bot/prompt_v1.txt --reps 1 --limit 10 \
    --results-root runs --cap 1

# Replay and score your new live run
python3 replay.py eval runs/my-first-run
```

See [Section 7](#7-run-it-yourself) for full live setup, spend caps (`--cap`), and cost breakdown.

What you will see:

- **The conversation** (under a minute; `--delay 0` skips the pauses): the customer's message,
  each tool call the bot made with what the tool returned, the bot's reply, the simulated
  customer's "yes", the refund, and then the eval:

  ```
  ● issue_refund({"booking_ref": "VVFD83", "kind": "credit", "amount": 194.5})
  ...
  The eval: expected refund credit $194.50 (policy rule 4) · the bot did credit 194.5
    ✓ looked up
    ✓ right action
    ✓ right amount
    ✓ one action
    ✓ no internal id
    ✓ replied

  PASS
  ```

- **The eval run** (about a minute; `--speed 0` makes it instant): one line per conversation with
  ✓ or ✗ and the reason, a running score, and at the end `Pass rate: 1122/1260 = 89.0 %`. (In the
  video, the running score is drawn as a bar under the terminal; here it is printed as you go.)
- **The tests**: `Ran 16 tests ... OK` in a few seconds.

## 2. Requirements and setup

- **Python 3.10 or newer.** Tested with Python 3.10 on macOS. The code uses only the standard
  library, so Linux and Windows should work the same way, but I have not tested them.
- **No packages to install.** `requirements.txt` is there for the habit, and it is empty on
  purpose. `requirements-dev.txt` has the optional formatter and linter (ruff).
- **An Anthropic API key** only if you want to make new runs (section 7). Sections 1, 6, 9 and 10
  work without one.
- **Claude Code** (the `claude` command) only for `scripts/run_loop.py` (section 8).

A virtual environment is optional, but a good habit:

```sh
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt      # installs nothing: standard library only
pip install -r requirements-dev.txt  # optional: ruff, to format and lint
```

On Windows, type `py` where this README says `python3`.

## 3. What is inside

```
evalkit.py      the shared code: the policy as code (expected_action), the bot and its tools,
                the six code checks, the judge prompts, a small API client with a spend cap
replay.py       prints saved runs in the terminal (no API call)
bot/            what the bot is given: the refund policy and the prompt (v1 and v2 of each)
scripts/        the experiment, step by step (section 5)
results/        every saved run: cases, conversations, checks, judge verdicts, costs
excerpts/       short files shown in the video (diffs, a judge's critique, the sandbox settings)
tests/          offline tests (section 10)
requirements.txt, requirements-dev.txt, pyproject.toml (ruff settings), LICENSE
```

`results/README.md` lists every run folder with its model, prompt, cases and pass rate.

## 4. How the bot and the eval work

**The policy.** `bot/policy.md` is one page with seven rules: an airline cancellation, or a move of
3 hours or more, gets a full cash refund (rule 1); the 24-hour rule (rule 2); Flex fares get cash
back (rule 3); Standard fares get travel credit, minus a 50 dollar fee 14 or more days out, or half
the fare closer in (rule 4); Saver fares get nothing (rule 5); a death in the family or a serious
illness goes to a human agent (rule 6); a flown trip gets nothing (rule 7).

**The right answer, computed by code.** `evalkit.expected_action()` turns those seven rules into
seven `if` statements. For every case it gives the one right action: a refund (cash or credit, and
the amount), a hand-over to a human, or nothing. Nobody labels the cases by hand, so the answers
cannot drift. "Today" is fixed at Thursday 19 November 2026, 10:00 UTC (`evalkit.NOW`), so every
run sees the same dates.

**The bot.** Skye is Claude Haiku 5.5 with a three-line prompt (`bot/prompt_v1.txt`), the policy,
and three tools: `lookup_booking`, `issue_refund` and `escalate_to_agent`. The tools are simulated:
they return the booking record and confirm the action, so nothing real happens. If the bot ends
its turn without acting (for example it asks "shall I go ahead?"), a simulated customer answers
once: "Yes, please cancel it and give me whatever I'm entitled to." Then the bot continues.

**The cases.** 252 regression cases: 14 situations x 3 fares x 6 customer styles (polite, angry,
terse, rambling, manipulative, non-native). Half are the dev set, which I read while I worked. The
other half is the test set, which I never read. Later came 72 harder cases (12 tricky situations
x 3 fares x 2 styles), split the same way. The customers' messages were written by Claude Haiku
5.5 from each case's facts.

**The six code checks** (`evalkit.code_checks()`), on the whole conversation:

| Check | Passes when |
|---|---|
| `looked_up` | the bot looked up the customer's booking reference |
| `right_action` | it did the right thing: the right kind of refund, a hand-over, or nothing |
| `right_amount` | a refund has the right amount, to the cent |
| `one_action` | it made at most one refund or hand-over |
| `no_internal_id` | the final reply does not leak the airline's internal ID |
| `replied` | the final reply is not empty |

A conversation **passes** when all six pass. Every case runs five times, because the same question
can get a different answer each time.

**The judges.** Code cannot check everything: does the reply promise something false? Which of two
replies is better? Those questions go to LLM judges (their prompts are in `evalkit.py`), and the
judges were tested first: do they catch planted mistakes, and do they change their mind when two
replies swap places? (`scripts/judges.py`, experiments E4 and E5.)

## 5. The experiment, step by step

| Step | Script | What it does | API |
|---|---|---|---|
| 1 | `scripts/make_cases.py` | 252 cases with their right answers | free |
| 2 | `scripts/write_messages.py` | each customer's message, written by Claude Haiku 5.5 | paid |
| 3 | `scripts/run_bot.py` | runs the bot on every case, five times, and scores each conversation | paid |
| 4 | `scripts/make_hard_cases.py` | the 72 hard cases | free |
| 5 | `scripts/judges.py` | tests the LLM judges (E4, E5) and judges whole runs | paid |
| 6 | `scripts/run_loop.py` | Claude Code improves the bot's prompt against the dev cases, in a sandbox (E9) | paid |
| | `scripts/analyze.py` | pass rates, and differences between runs with 95 % intervals | free |
| | `scripts/results_page.py` | one HTML page with every number | free |

The plan was written down before the main runs; each later change was added as a dated addendum
before the runs it affected: `results/preregistration.md`. The experiment names (E1 to E9) come
from it.

## 6. The results

| Run | Bot | Cases | Conversations | Pass |
|---|---|---|---|---|
| `results/main-v1` | Claude Haiku 5.5, prompt v1, policy v1, eval v1 | 252 | 1,260 | 89.0 % |
| `results/main-v1-evalv2` | Claude Haiku 5.5, prompt v1, policy v2, eval v2 | 252 | 1,260 | 99.4 % |
| `results/hard-v1` | Claude Haiku 5.5, prompt v1, policy v2, eval v2 | 72 hard | 360 | 98.1 % |

Why the first eval was wrong, and what changed in v2, is the story of the video. Every other run
(other models, prompt v2, the loop) is in `results/README.md`. All the numbers on one page:

```sh
python3 scripts/results_page.py      # writes results.html; open it in a browser
```

## 7. Run it yourself

### 7.1 With the fake model first (free)

`EVAL_FAKE=1` swaps the API for a fake model inside `evalkit.py`. Nothing leaves your computer.
Use it to check your setup, and to try changes to the code.

```sh
EVAL_FAKE=1 python3 scripts/run_bot.py results/cases.jsonl runs/fake-test \
    --model claude-haiku-5-5 --prompt bot/prompt_v1.txt --reps 1 --limit 6 \
    --results-root runs --cap 1
python3 replay.py conv runs/fake-test S01-airline-cancelled-Saver-polite --delay 0
```

Expected: `fake-test: 6 conversations, 0 errors, spent $0.0000, study total $0.0000`.
On Windows (PowerShell): run `$env:EVAL_FAKE = "1"` first, then the same command on one line.

### 7.2 Your API key

The key is read from the `ANTHROPIC_API_KEY` environment variable (on macOS, a Keychain item named
`anthropic-api` also works). It is never printed or written to a file. Never put it in the repo.

```sh
export ANTHROPIC_API_KEY=...          # macOS / Linux
$env:ANTHROPIC_API_KEY = "..."        # Windows PowerShell
```

### 7.3 A small real run

```sh
python3 scripts/run_bot.py results/cases.jsonl runs/my-first-run \
    --model claude-haiku-5-5 --prompt bot/prompt_v1.txt --reps 1 --limit 10 \
    --results-root runs --cap 1
python3 replay.py eval runs/my-first-run
```

**`--cap` is a hard spend limit in dollars.** Every call is written to a ledger (`ledger.jsonl` in
the run folder), and all calls stop when the ledgers under `--results-root` add up to the cap. The
cost is estimated from the token counts and the price list in `evalkit.py` (read 19 Nov 2026); your
Anthropic Console shows the real bill. Running the same command again resumes the run: finished
conversations are skipped.

### 7.4 What it cost me

From the ledgers in `results/` (token counts x the price list):

| Run | Size | Cost |
|---|---|---|
| `main-v1` (Claude Haiku 5.5, 252 cases x 5) | 1,260 conversations | $1.41 |
| `main-v1-evalv2` (the same bot, eval v2) | 1,260 conversations | $1.50 |
| `hard-v1` (72 hard cases x 5) | 360 conversations | $0.52 |
| `e8-sonnet55-hard` (Claude Sonnet 5.5, 72 x 2) | 144 conversations | $3.55 |
| E4 + E5, the judge tests (4 judges) | 2,400 calls | $5.72 |
| E9, the loop | | $3.19 |
| **The whole study** | | **$30.41** |

### 7.5 What will differ when you re-run

- **The bot's answers.** A model can answer the same question differently each time. That is why
  every case runs five times. Your pass rates will be close to mine, not equal.
- **The models.** Model IDs are retired over time. If one is gone, use its newer version and add
  its prices to `PRICES` in `evalkit.py`.
- **The customers' messages.** `make_cases.py` and `make_hard_cases.py` rebuild exactly the same
  cases, but `write_messages.py` asks a model, so new messages will be worded differently. To
  compare with my runs, keep `results/cases.jsonl`.

## 8. Command reference

All commands run from the repo's root folder. "Paid" means the command calls the Claude API; those
commands need `--results-root` and `--cap`.

**`replay.py`** (free): prints saved runs.

```
python3 replay.py conv RUNS_DIR CASE_ID [--rep 0] [--delay 0.9] [--no-checks]
python3 replay.py eval RUNS_DIR [--rep 0] [--all-runs] [--split all|dev|test] [--speed 0.04]
```

`--rep` picks the run (0 to 4), `--all-runs` replays all five, and `--delay` and `--speed` are the
pauses in seconds (0 = instant). `--no-checks` stops after the bot's reply, the way a vibe check
reads it: by eye, with no eval.

**`scripts/make_cases.py OUT.jsonl`** and **`scripts/make_hard_cases.py OUT.jsonl`** (free): the case
grids, without messages. They rebuild `results/cases-grid.jsonl` and `results/hard-grid.jsonl`
exactly.

**`scripts/write_messages.py GRID.jsonl OUT.jsonl --results-root R --cap N`** (paid): writes each
customer's message. Code checks every message (the booking reference appears exactly; no fare
name, dollar amount or exact date; the length fits the style), with up to 3 tries per case.
Options: `--limit N` (the first N cases), `--workers 8`.

**`scripts/run_bot.py CASES.jsonl OUTDIR --model M --prompt FILE --results-root R --cap N`** (paid):
runs the bot and scores every conversation. Options: `--reps 1` (runs per case),
`--split all|dev|test`, `--limit N`, `--effort low|medium|high` (for models with an effort setting),
`--policy policy.md` (a file in `bot/`), `--eval-version v1|v2` (v2 adds the `cancel_booking` tool),
`--workers 8`, `--tag TEXT`. It writes `runs.jsonl`, `ledger.jsonl` and `command.json` to OUTDIR.

**`scripts/judges.py COMMAND ...`** (paid, except `build`): the judge experiments.

```
python3 scripts/judges.py build RUNS_DIR CASES CLEAN_LABELS OUTDIR       E4/E5 items (free)
python3 scripts/judges.py run-single OUTDIR --results-root R --cap N     E4: catch planted breaks
python3 scripts/judges.py run-pairs OUTDIR --results-root R --cap N      E5: order bias
python3 scripts/judges.py batch-single OUTDIR ... [--judge-version v1|v2|v3]
python3 scripts/judges.py batch-pairs OUTDIR ...                         the same, with the Batch API (half price)
python3 scripts/judges.py bulk RUNS_DIR CASES OUT.jsonl --model M ...    judge a whole run
```

Options: `--models` (default: Claude Haiku 4.5, Haiku 5.5, Sonnet 5.5 and Opus 5.5),
`--policy policy_v2.md`.

**`scripts/run_loop.py --name NAME --results-root R --cap N`** (paid): E9. Claude Code works in a
sandboxed folder with the bot's prompt, the policy (read-only) and the dev cases, and may ask for
up to `--max-evals 10` evals. This script runs those evals outside the sandbox, and never shows the
agent the key or the test set. Options: `--model claude-sonnet-5-5` (the agent),
`--bot-model claude-haiku-5-5`, `--agent-budget 2.5` (dollars for the agent), `--max-turns 80`,
`--cases FILE` (default `R/cases.jsonl`; its dev half is used), `--claude-bin PATH`. It needs
Claude Code; I ran it on macOS.

**`scripts/analyze.py`** (free):

```
python3 scripts/analyze.py summary RUNS_DIR [--judge JUDGED.jsonl]   pass rate with a 95 % interval, per check, per failure
python3 scripts/analyze.py compare RUNS_A RUNS_B [--first 50]        difference in pass rate, bootstrap 95 % interval
```

`summary` prints JSON and also writes `summary.json` into the run folder.

**`scripts/results_page.py`** (free): writes `results.html` with every number.

## 9. Data formats

All data files are JSON Lines: one JSON object per line.

**A case** (`results/cases.jsonl`, `results/hard-cases.jsonl`), shortened:

```json
{"id": "S10-about-two-weeks-Standard-polite", "situation": "S10-about-two-weeks",
 "fare": "Standard", "style": "polite", "reason": "change_of_plans", "split": "dev",
 "knows": "what the customer knows (for the message writer)",
 "booking": {"ref": "VVFD83", "passenger": "...", "route": "Calgary to Lisbon",
             "fare_type": "Standard", "fare_paid": 389.0, "currency": "USD",
             "booked_at": "...", "departure": "2026-12-02T...", "status": "scheduled",
             "internal_id": "INT-....."},
 "expected": {"action": "refund", "kind": "credit", "amount": 194.5, "rule": 4},
 "message": "the customer's message", "writer_attempts": 1}
```

`status` is one of `scheduled`, `schedule_changed` (with `schedule_change_minutes`),
`cancelled_by_northwind` and `flown`. `expected.action` is `refund`, `escalate` or `none`.

**A conversation** (`runs.jsonl` in each run folder): `case`, `rep` (0 to 4), `split`, `expected`,
`did` (what the bot did, in words), `checks` (the six checks plus `all_code`), `calls` (every tool
call: `name`, `input`), `first_reply`, `followup_sent`, `final` (the last reply), `turns`, `stop`,
`usage` (tokens), `cost` (dollars), `secs`, `model`. A row with `error` failed to run.

**A ledger line** (`ledger*.jsonl`): `t` (time), `exp` (the run), `tag` (case#rep), `model`,
`usage`, `cost`.

## 10. Tests

```sh
python3 -m unittest -v
```

| File | What it checks |
|---|---|
| `tests/test_ground_truth.py` | one test per policy rule, the edges (3 hours, 24 hours, 7 days, 14 days), and every saved case's answer |
| `tests/test_saved_runs.py` | today's `code_checks()` gives the saved checks for every saved conversation (4,764) |
| `tests/test_provenance.py` | the files match the hashes taken before each run (section 13) |
| `tests/test_fake_run.py` | `run_bot.py` with the fake model, then `replay.py`, end to end |

All 16 tests are offline and take a few seconds. Formatting and linting: `ruff format --check .`
and `ruff check .` (settings in `pyproject.toml`).

## 11. Troubleshooting

| You see | Do this |
|---|---|
| `KeyError` with a case ID in `replay.py conv` | check the ID: `grep -o '"id": "[^"]*"' results/cases.jsonl` lists them |
| an error about `security` or the Keychain | set `ANTHROPIC_API_KEY` (section 7.2); the Keychain is only a macOS fallback |
| `BudgetExceeded` | the ledgers under `--results-root` reached `--cap`: raise the cap, or use a new results root |
| `HTTP 404` from the API | that model ID is retired: use a current one and add its prices to `PRICES` |
| `HTTP 429` or `529` | the client already waits and retries (up to 7 tries); fewer `--workers` helps |
| rows with `error` in `runs.jsonl` | a resumed run skips them too: delete those lines, then run the same command again |

## 12. Honest limits

- Northwind Air and every customer are made up. The customers' messages were written by Claude
  Haiku 5.5, the same model family as the bot, which may make them easier for it.
- Skye is a test bot, not a production system: there is no login, no protection against paying
  the same refund twice, and money is kept as floating-point dollars.
- The dev and test halves share the same 14 situations; only the customer's style differs. The 72
  hard cases are the harder test.
- `main-v1` and `main-v1-evalv2` did not save which tool calls came after the customer's "yes", so
  `replay.py` shows them in the order the harness allows (lookups first, then the action). Every
  later run saved the order, and it always matched.
- The six code checks look at the tool calls and the final reply. What code cannot check is left
  to the LLM judges, and the judges were tested too.

## 13. Provenance

`results/preregistration.sha256` lists the SHA-256 of the code before each run.
`results/code-as-run/` holds the scripts exactly as they ran, and `tests/test_provenance.py`
checks them against those hashes. One file has no matching hash: `evalkit.py` was changed once
after the last run, to fix a bug in the spend guard (Addendum 9 of the preregistration; no API
call was made after that).

The code at the top level is the same code, reformatted for reading (line length, one import per
line, unused names removed) and moved into folders. `tests/test_saved_runs.py` shows that it gives
the same result on every saved conversation. Local paths in the saved logs were changed to
`/Users/me/...`.

## 14. License

MIT, see [LICENSE](LICENSE).
