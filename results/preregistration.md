# Pre-registration: AI Evals hands-on (written 2026-11-19, after the pilot, before any main run)

Approved by the user: "if you feel longer video will be good go ahead" (full plan, hard stop $30; Claude API only, after
"dont use openrouter api. I have claude API"). Pilot spent $0.20 (results/pilot/).

## Fixed before the main runs
- Feature: the Northwind Air refund bot. Model claude-haiku-5-5, API version 2026-10-21, default effort, tools lookup_booking /
  issue_refund / escalate_to_agent. Prompt v1 = prompt_v1.txt (sha256 in results/main-v1/command.json). Policy = policy.md.
- Simulated customer: if the bot ends a turn without refunding or escalating, the customer answers once:
  "Yes, please cancel it and give me whatever I'm entitled to." (Pilot finding: the bot asks before acting; the first eval,
  without this reply, wrongly marked correct conversations as failures. "Yes, please go ahead." was ambiguous: in 1 of 24 it
  made the bot escalate a Saver case. Both pilot versions are kept in results/pilot/.)
- Cases: 252 = 14 situations x 3 fares x 6 styles (make_cases.py, seed 20261119); dev 126 / test 126. Messages written by
  claude-haiku-5-5 (write_messages.py), checked by code. The test set is not read by us and not shown to the loop agent (E9)
  until the end.
- Ground truth: evalkit.expected_action (policy as code). Code checks: looked_up, right_action, right_amount, one_action,
  no_internal_id, replied; "pass" = all code checks pass (+ the judge where stated).
- Spend guard: the sum of every ledger.jsonl under results/ (usage x the price list read 2026-11-19); hard stop $30.

## Experiments and their measures
- E1 vibe check: the five cases shown "by eye" are fixed now: the first five dev cases in file order whose style is "polite"
  (one per situation S01, S03, S05, S07, S09). We show their run-0 replies. Then: pass rate over all 252 cases, run 0.
- E2 error analysis: we read the failing dev conversations of prompt v1 (run 0 first, then other runs), write the first thing
  that went wrong, and group the notes. Only dev cases are read.
- E3 code checks: pass rate per check, v1, all runs.
- E6 reliability: per case, pass@5 (at least one of 5 runs passes) and pass^5 (all 5 pass), and the mean per-run pass rate.
- E7 prompt v2 (written from E2, on dev only) vs v1: difference in mean per-run pass rate (code checks), with a 95 % interval
  from a case-level bootstrap (10,000 resamples, seed 1). Reported (a) on the first 50 cases of a fixed shuffled order
  (seed 7) and (b) on all 252. Also reported separately on dev and on test.
- E4 judge calibration: 120 replies = 60 real v1 replies that pass all code checks and that we read and label clean, + 60
  copies of other clean replies with one planted policy break each (fixed list of break types, inserted by code). Judges:
  Haiku 4.5 (no effort setting), Haiku 5.5, Sonnet 5.5, Opus 5.5 (effort low). Measures: share of breaks caught (true
  positive rate) and share of clean replies passed (true negative rate), each with a Wilson 95 % interval; and the agreement
  an "always PASS" judge would get at the real failure rate of the bulk run.
- E5 judge bias: 60 pairs of two clean replies to the same case (different runs) + 30 pairs clean vs planted break + 30 pairs
  clean vs the same reply plus a padding paragraph that adds nothing. Each pair in both orders, same 4 judges. Measures: flip
  rate (the judge picks a different reply when the order changes) on the first set; accuracy in both orders on the second;
  share of choices for the padded reply on the third.
- E8 model swap: prompt v2 on claude-haiku-4-5 (2 runs) and claude-sonnet-5-5 (1 run, budget), all 252 cases. Measures:
  pass rate, per-failure-type differences vs Haiku 5.5, cost per 1,000 conversations (from usage x price).
- E9 the loop: Claude Code (claude-sonnet-5-5) in a sandbox, starting from prompt v1, asked to improve the prompt using an
  eval on the dev cases only (run through a helper outside the sandbox; at most 10 evals per run). Then the final prompt is
  run on the hidden test set (5 runs). Measure: dev score vs test score, before and after; and whether the prompt names
  specific bookings, people or cases. 3 runs if the budget allows (2 at least).
- Whatever comes out is reported, including no difference.

## Addendum, 19 November 2026 (after the v1 run and its error analysis, before any eval-v2 run): eval v2
The v1 run (results/main-v1): 1,121 / 1,260 conversations passed the code checks (89.0 %). Error analysis of the dev failures
(62 of 630, read by hand): 56 = the bot said "no refund" correctly, then, after the simulated customer's "Yes, please cancel it
and give me whatever I'm entitled to", handed the case to a human agent because it had no tool to cancel a booking (or to log a
complaint); 5 = Flex fare + bereavement/illness: the bot refunded under rule 3 instead of escalating under rule 6 (the policy text
did not say which rule wins); 1 = escalated a flown bereavement case in turn 1. No wrong amount, no wrong refund kind, no leaked
internal ID. These are kept as the "eval v1" result (the first eval was partly wrong: harness and policy, not the bot).
Eval v2 (fixed now, before running it): policy_v2.md (rule 6 wins over other rules; new rule 8: cancel_booking for cancellations
with nothing to give, issue_refund also cancels; new rule 9: human agents only under rule 6, complaints go to a feedback form) and
the cancel_booking tool. Same cases, same messages, same simulated customer reply, same code checks (cancel_booking is neither a
refund nor an escalation, so it is allowed when the expected action is "none"; on a flown trip it returns an error). The v1 prompt
is re-run under eval v2 as the baseline (results/main-v1-evalv2, 252 x 5). All later experiments (E4-E9) use eval v2.

## Addendum 2, 19 November 2026 (after the eval-v2 baseline, before any run on the hard cases)
Eval-v2 baseline (results/main-v1-evalv2): 1,252 / 1,260 = 99.4 %; pass^5 97.6 %; 6 flaky cases. Dev failures read by hand
(7): 3 = the bot asked a second clarifying question after the single simulated reply and took no action; 3 = Flex +
bereavement refunded directly (breaks rule 6 of policy v2; one case, flaky); 1 = refund plus an unneeded escalation (rule 9).
With 99.4 %, the 252 cases become the REGRESSION suite (Anthropic, "Demystifying evals for AI agents": regression evals "should
have a nearly 100% pass rate"). A CAPABILITY set is added: make_hard_cases.py, 72 cases = 12 hard situations x 3 fares x 2
styles (polite, angry), dev 36 / test 36, written by the same writer (Haiku 5.5) with the same checks; two situations get fixed
text appended (H01 a fake system notice, H12 a fake manager approval code). Ground truth from policy v2 as code (rule 6 now
checked before rule 1, as policy v2 says; this does not change any of the 252 answers, checked by code). Eval v2 throughout.

Revised experiments (replacing E7-E9 above; E1-E6 unchanged):
- E7: prompt v1 on the hard set (72 x 5). Prompt v2 is written ONLY from reading the hard-DEV failures of v1. Primary: v2 - v1
  mean per-run pass rate on the hard-TEST cases (36 x 5 each), 95 % case-bootstrap interval (10,000, seed 1). Secondary: v2 on
  the regression set (252 x 5) vs the v1 baseline (no-regression check), and the "first 50 vs all 252" demonstration there.
- E8 (model / setting swap), prompt v2 on the hard set (72 x 5) and the regression set (252 x 1 unless stated): claude-haiku-4-5
  (hard x5, regression x1), claude-sonnet-5-5 (hard x5 only, budget), claude-haiku-5-5 with effort "low" (hard x5, regression x5).
  Measures: pass rates, cost per 1,000 conversations.
- E9: the loop runs on the HARD set: the agent sees and evaluates on hard-dev only (36 cases, 1 run per eval, max 10 evals);
  the final prompt is then run on hard-test (x5) and on the regression set (x1). Start prompt = prompt v1. 2 loop runs
  (budget), agent budget $2 each.
- E4/E5 unchanged (judges against policy v2), the judge calls sent through the Message Batches API (half price) where possible.
- Budget order if money runs short: E4, E5, E7, E8 (Haiku 4.5, low effort, then Sonnet), E9. Hard stop $30 (spend guard).

## Addendum 3, 19 November 2026 (after prompt v1 on the hard set; before any E8 run)
Prompt v1 on the hard set (results/hard-v1, Haiku 5.5): 353 / 360 = 98.1 %; hard-dev 180 / 180 (100 %), hard-test 96.1 %;
pass^5 94.4 %. With no hard-dev failure, prompt v2 cannot be written from hard-dev failures as planned.
Decision, fixed now:
- E8 runs first, with prompt v1 (there is no v2): claude-haiku-4-5 (hard x5, regression x1); claude-haiku-5-5 effort "low"
  (hard x5, regression x1); claude-sonnet-5-5 (hard x5).
- E7 and E9 then use the setup with the LOWEST hard-dev pass rate in E8 (ties: the cheaper), if that rate is below 95 %.
  E7: prompt v2 is written from that setup's hard-dev failures only; primary = v2 - v1 on hard-test (36 x 5), case bootstrap.
  E9: the loop on that setup, as in addendum 2.
- If no setup is below 95 % on hard-dev: E7 is reported as "no failures to learn from", and E9 runs once on claude-haiku-4-5
  anyway, to see what an agent does to a prompt when there is almost nothing left to fix.

## Addendum 4, 19 November 2026 (after judge v1 on the E4 set; before judge v2)
Judge v1 (results/e45/e4_verdicts.jsonl): all 4 judges caught 60/60 planted breaks; they flagged 9-12 of the 60 hand-labelled clean
replies. Read by hand: 9 clean replies flagged by Haiku 5.5, Sonnet 5.5 and Opus 5.5 all say "an agent will reply within 2
business days" and give a ticket number, which the escalate_to_agent TOOL RESULT returned; the judge prompt showed the tool calls
but not their results (missing context in our judge, not a bot error). Haiku 4.5's other flags are reasoning errors (for example
"75 minutes exceeds the 3-hour threshold"). Labels unchanged.
Judge v2 (fixed now): the same prompt, but <actions_taken> lists each tool call with its result. Same 120 items, same 4 judges,
same measures. E5 (pairs) and any bulk judging use judge v2.

## Addendum 5, 19 November 2026 (after judge v2; before judge v3)
Judge v2 (tool results added): clean replies passed: Haiku 5.5 57/60, Sonnet 5.5 58/60, Opus 5.5 58/60, Haiku 4.5 49/60; all
caught 60/60. Remaining flags read by hand: the judge did not know today's date ("the current date is unknown") and read
kind "cash" as different from "original payment method"; Haiku 4.5's flags are reasoning errors. One Opus flag found a real
misstatement our hand label missed (S12-illness-before-Standard-non_native#2: "only valid if it is handled before the flight
departs"; the policy says "if they ask before"). Labels are NOT changed after the fact; this is reported as a label error the
judge found.
Judge v3 (fixed now): judge v2 + a short context line (today's date and time; what kind "cash"/"credit" mean; the escalation
result is real). Same 120 items, same 4 judges. After v3 we stop iterating on the judge (no more versions on this set).

## Addendum 6, 19 November 2026 (budget; before any Sonnet E8 result and before E7/E9)
Spend so far $10.17 (real usage x price). The remaining plan as written would end near $32, above the $30 hard stop. Following the
pre-registered budget order (E9 last), fixed now: (1) Sonnet 5.5 on the hard set x2 instead of x5. (2) The regression checks for
the Haiku 4.5 setup (E8, E7's v2, E9's final prompt) run on the 126 regression TEST cases x1 instead of all 252. (3) E9: one
loop run, at most 8 evals. Haiku 5.5 low effort: hard x5 (resumed) and regression test x1. Judge v3 is final (60/60 caught for
all four judges; clean passed: Haiku 5.5 60/60, Sonnet 59/60, Opus 59/60, Haiku 4.5 49/60; the two current-model flags are a
real misstatement and an implied "prioritise" promise our labels missed).
E7/E9 setup by the addendum-3 rule: Haiku 4.5 (hard-dev 96/180 = 53 %, the lowest of the setups run so far; Haiku 5.5 low effort and Sonnet are far above it in partial data).

## Addendum 7, 19 November 2026 (prompt v2 written; before any v2 run)
Error analysis of Haiku 4.5, prompt v1, hard-DEV only (84 failures of 180; results/e8-haiku45-hard): boundaries treated loosely
(H03 179 minutes taken as 3 hours; H04 24-hour rule applied though departure is under 7 days after booking; H05 booked 24 h 10 min
ago treated as within 24 hours: full cash refunds the policy does not give); rule 6 stretched (H06 cousin called "immediate
family"; H07 a wife's illness); authority claims (H12 fake manager code escalated "to verify"; H01 fake system notice obeyed
sometimes). Prompt v2 = prompt v1 + a 5-point "How to decide" section written from these patterns only (prompt_v2.txt, sha256
above). No hard-test transcript was read.
E7 runs (Haiku 4.5): v2 on hard-test x5 (primary: v2 - v1 per-case mean pass rate on hard-test, v1 from e8-haiku45-hard, case
bootstrap 10,000, seed 1), v2 on hard-dev x1 (descriptive), v2 on the regression test cases x1 (no-regression check vs
e8-haiku45-regtest).

## Addendum 8, 19 November 2026 (after the loop; before the final checks of its prompt)
E9 loop1 (results/e9-loop1): Claude Code (Sonnet 5.5) used 6 of 8 evals (agent cost estimate $0.15, 4.9 minutes). Dev scores
(1 run each): 32, 31, 35, 32, 35, 31 / 36; evals 2 and 3 were the SAME prompt (31 vs 35: noise); the final prompt is the one
from eval 5 (35/36 once). Reading the final prompt: no booking references, names or amounts, but timestamps copied from dev
cases (for example "booked 11-18 10:10, departs 11-25 10:05"), and "grandparent" added to immediate family (not in the policy,
not tested by any case). Limitation: dev and test share the same 12 hard situations.
Final checks (fixed now; budget $6.89 left of $30): the final prompt on hard-test x5 (primary: vs prompt v1, and vs prompt v2,
on Haiku 4.5), hard-dev x2, regression test x1.

## Addendum 9, 19 November 2026 (results of the final checks; a spend-guard bug)
Loop prompt on Haiku 4.5: hard-test x5 91.7 % (v1 56.1 %, v2 81.1 %; loop - v2 +10.6 points, 95 % interval +3.9 to +17.8);
hard-dev x2 91.7 % (the agent reported 35/36 = 97.2 % from one run); regression test x1 94.4 % (v1 85.7 %, +8.7, interval
+2.4 to +15.9). Without H04 and H05 (whose exact timestamps the agent copied into the prompt and which the test cases share):
loop 91.3 % vs v2 82.0 %. It broke one category: H11 (bereavement + 4-hour move) 15/15 with v1 and v2, 12/15 with the loop prompt.
SPEND-GUARD BUG: the guard summed only files named ledger.jsonl and missed results/e45/ledger-e5.jsonl ($2.31, the E5 batch).
The true total (usage x price) is $30.41, $0.41 above the $30 hard stop. Fixed in evalkit.Ledger (now reads ledger*.jsonl).
No further API calls were made after this.
