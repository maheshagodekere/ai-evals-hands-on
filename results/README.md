# results/

Every saved run. Folder names follow the experiments of `preregistration.md` (E1-E9).
A conversation passes when all six code checks pass. Replay any of them with `replay.py`.

| Folder | Model | Prompt | Policy | Eval | Cases | Split | Cases run | Runs each | Conversations | Pass |
|---|---|---|---|---|---|---|---|---|---|---|
| `e7-haiku45-v2-harddev` | haiku-4-5 | prompt_v2.txt | policy_v2.md | v2 | hard-cases.jsonl | dev | 36 | 1 | 36 | 80.6 % |
| `e7-haiku45-v2-hardtest` | haiku-4-5 | prompt_v2.txt | policy_v2.md | v2 | hard-cases.jsonl | test | 36 | 5 | 180 | 81.1 % |
| `e7-haiku45-v2-regtest` | haiku-4-5 | prompt_v2.txt | policy_v2.md | v2 | cases.jsonl | test | 126 | 1 | 126 | 88.9 % |
| `e8-haiku45-hard` | haiku-4-5 | prompt_v1.txt | policy_v2.md | v2 | hard-cases.jsonl | all | 72 | 5 | 360 | 54.7 % |
| `e8-haiku45-regtest` | haiku-4-5 | prompt_v1.txt | policy_v2.md | v2 | cases.jsonl | test | 126 | 1 | 126 | 85.7 % |
| `e8-haiku55low-hard` | haiku-5-5 (low effort) | prompt_v1.txt | policy_v2.md | v2 | hard-cases.jsonl | all | 72 | 5 | 360 | 98.1 % |
| `e8-haiku55low-regtest` | haiku-5-5 (low effort) | prompt_v1.txt | policy_v2.md | v2 | cases.jsonl | test | 126 | 1 | 126 | 100.0 % |
| `e8-sonnet55-hard` | sonnet-5-5 | prompt_v1.txt | policy_v2.md | v2 | hard-cases.jsonl | all | 72 | 2 | 144 | 96.5 % |
| `e9-loop1-final-harddev` | haiku-4-5 | final_prompt_for_bot.txt | policy_v2.md | v2 | hard-cases.jsonl | dev | 36 | 2 | 72 | 91.7 % |
| `e9-loop1-final-hardtest` | haiku-4-5 | final_prompt_for_bot.txt | policy_v2.md | v2 | hard-cases.jsonl | test | 36 | 5 | 180 | 91.7 % |
| `e9-loop1-final-regtest` | haiku-4-5 | final_prompt_for_bot.txt | policy_v2.md | v2 | cases.jsonl | test | 126 | 1 | 126 | 94.4 % |
| `hard-v1` | haiku-5-5 | prompt_v1.txt | policy_v2.md | v2 | hard-cases.jsonl | all | 72 | 5 | 360 | 98.1 % |
| `main-v1` | haiku-5-5 | prompt_v1.txt | policy.md | v1 | cases.jsonl | all | 252 | 5 | 1,260 | 89.0 % |
| `main-v1-evalv2` | haiku-5-5 | prompt_v1.txt | policy_v2.md | v2 | cases.jsonl | all | 252 | 5 | 1,260 | 99.4 % |
| `pilot/bot-v1` | haiku-5-5 | prompt_v1.txt | policy.md | v1 | cases.jsonl | all | 12 | 2 | 24 | 95.8 % |
| `pilot/bot-v1-no-followup` | haiku-5-5 | prompt_v1.txt | policy.md | v1 | cases.jsonl | all | 12 | 2 | 24 | 75.0 % |

## Other files

| File | What it is |
|---|---|
| `cases-grid.jsonl` | the 252 regression cases before the customers' messages were written (make_cases.py) |
| `cases.jsonl` | the 252 regression cases with the customers' messages (write_messages.py) |
| `hard-grid.jsonl` | the 72 hard cases before their messages were written (make_hard_cases.py) |
| `hard-cases.jsonl` | the 72 hard cases with their messages |
| `preregistration.md` | the plan, written before the main runs, and its dated addenda |
| `preregistration.sha256` | the SHA-256 of the code before each run |
| `code-as-run/` | the scripts exactly as they ran (see its README) |
| `pilot/` | the first small runs, before the preregistration |
| `e4-candidates.json, e4-clean-labels.txt, e4-excluded.json` | E4: the replies read and labelled by hand |
| `e45/` | E4 judge calibration and E5 judge bias (judges.py): the items, the pairs and every verdict |
| `e7-small-eval-simulation.json` | E7: what an eval of 5, 10, 20 or 36 cases can tell (a simulation) |
| `e9-loop1/` | E9: the loop (run_loop.py): the agent's stream, its evals and the final prompt |
| `e9-smoke1/, e9-smoke2/` | two short test runs of the loop and its sandbox |
| `ledger.jsonl` | the cost of every call made outside a run folder (the customers' messages) |
| `*.log` | the console output of each run |
