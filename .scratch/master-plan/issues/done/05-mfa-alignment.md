# 05 — MFA environment + word-alignment script

**What to build:** Every ingested native clip gets a word-timing JSON produced by Montreal Forced Aligner. Install Miniconda user-scope (owner-approved 2026-07-11), create the quarantined `mfa` conda env with the French models — never pip-install MFA into the project venv. A script reads practices that have native audio, builds a temp MFA corpus (audio + normalized transcript: lowercase, punctuation stripped except apostrophes/hyphens, digits spelled out), shells out to MFA, parses the output TextGrids with a small pure-Python parser, and writes one alignment JSON per practice through the storage seam.

Alignment JSON contract (fixed — hand-authored files must be drop-in identical; times are seconds on the native clip's timeline):

```json
{"practice_id": 7, "source": "mfa", "model": "french_mfa",
 "words": [{"word": "on", "start": 0.31, "end": 0.42}]}
```

**Blocked by:** None — can start immediately.

**Status:** done (commit `c917ca4`, 2026-07-20)

- [x] Conda env exists; MFA aligns a real practice clip on this machine (`french_mfa` acoustic+dictionary; MFA 3.4.1 aligned practice 7 in ~50s)
- [x] Alignment JSON produced for every practice with native audio; words sorted, non-overlapping (only practice 7 has a native clip; `alignments/7.json`, 10 words)
- [x] Word count matches the normalized transcript (10 = 10, incl. "j'ai" as one word and English "Ridley Scott" via G2P); timings structurally validated (sorted, non-overlapping) — by-ear spot-check deferred to the owner
- [x] Setup documented so the env can be rebuilt from scratch (`scripts/README_MFA.md`)
- [x] If MFA misbehaves on short clips: hand-authored JSON (`"source": "manual"`) is a sanctioned drop-in (not needed for p7; documented in the README)
