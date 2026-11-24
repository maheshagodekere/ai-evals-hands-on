You are improving the system prompt of "Skye", an AI customer-support bot for an airline (Northwind Air). Skye handles
cancellation and refund requests with four tools: lookup_booking, issue_refund, cancel_booking and escalate_to_agent.

- prompt.md is Skye's system prompt. Edit it to make Skye handle more cases correctly. The airline's refund policy (policy.md)
  is added after your prompt automatically; you cannot change the policy.
- dev_cases.jsonl has the evaluation cases: each customer's message, their booking record and the correct outcome.
- Run `python3 run_eval.py` to score the current prompt.md on all the dev cases. It prints the pass rate and every failing case.
  Each eval takes a few minutes and you may run it at most 8 times, so make each one count.
- Only edit prompt.md. Do not edit any other file.

Goal: the highest pass rate you can reach. When you are done, say so and summarize what you changed.