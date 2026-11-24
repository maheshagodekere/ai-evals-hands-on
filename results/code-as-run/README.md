# The code as it ran

The experiment's scripts exactly as they were at the end of the study, before they were
reformatted for reading on 21 Nov 2026 and moved into folders. They expect the old flat layout
(everything in one folder); to run anything, use the code at the top of the repo.

`make_cases.py`, `write_messages.py`, `run_bot.py` and `make_hard_cases.py` match the last hash
listed for them in `../preregistration.sha256` (checked by `tests/test_provenance.py`).
`evalkit.py` here includes the spend-guard fix of Addendum 9, made after the last run, so it
matches none of its three listed hashes.
