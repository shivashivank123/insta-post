# insta-post

Scheduled runner. Twice an hour (:35 and :50 IST, 06–23 IST) `runner.py` runs each configured channel's own posting script and pushes
the result back to that channel's repo; once a week it refreshes the tokens. Configuration lives in the
`RUNNER_CONFIG` secret.

Run by hand: Actions → run → Run workflow (mode, force, channel number).
