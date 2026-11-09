# Tidelight protocol redaction, November 9, 2026

A private personal name was removed from Tidelight's `PROTOCOL.md` on
November 9, 2026. It appeared twice. Both places now give the owner's public
name, Adem:

- line 9: "…distinguish our visual judgment from Adem's acceptance."
- line 45: "Show the finished results to Adem before preparing any public
  artifact."

No other byte of the protocol changed.

`FREEZE.json` binds the protocol by its SHA-256. Its `PROTOCOL.md` entry now
records the redacted file:

    298a586e631fda540efbecd2efb1558e3878bd6252cb8ffea318d7a565a6a5db

No other field of `FREEZE.json` changed. Nothing else changed either: no
setting, threshold, code, target, label or result. In the GitHub repository,
`scripts/verify_sources.py` passes.

The repository's history was rewritten so that its original commit carries the
redacted protocol. That commit's identifier changed; its author, date and
message did not. The `PROTOCOL.md` download on arkhē.org and the copies of
`PROTOCOL.md` and `FREEZE.json` in `tidelight-reproduction.zip` carry the same
change.

Withheld: the pre-redaction SHA-256 of `PROTOCOL.md` and the original commit
identifier. Together with the redacted text, that hash would let anyone confirm
a guess of the removed name. The owner keeps the original file, its hash and
the original history privately, and can show them to a reviewer.
