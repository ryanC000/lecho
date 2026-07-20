# Montreal Forced Aligner (MFA) — word alignment setup

MFA produces the per-word timings that drive word-anchored feedback (PRD 8.4). It is
**quarantined in its own conda env** — never pip-install it into `backend/.venv` (the
Python 3.14 venv has no MFA wheels, and MFA's Kaldi dependency is conda-only on Windows).

The app itself never imports MFA. `scripts/align_natives.py` shells out to the env with
`conda run -n mfa`, and the backend only ever reads the JSON files that were produced.

## One-time setup (rebuildable from scratch)

Requires conda (Miniconda or Anaconda). Envs land under `%USERPROFILE%\.conda\envs`, so
no admin rights are needed.

```sh
conda create -n mfa -c conda-forge montreal-forced-aligner -y
conda run -n mfa mfa model download acoustic french_mfa
conda run -n mfa mfa model download dictionary french_mfa
```

Verify: `conda run -n mfa mfa version`.

## Running the aligner

From the repo root, with **any** Python (it imports the backend but calls the mfa env
itself — it does not run inside it):

```sh
python scripts/align_natives.py                 # align every practice with a native clip
python scripts/align_natives.py --practice-id 7 # align just one
```

Each run writes `backend/storage/alignments/{practice_id}.json` through the storage seam.

## The JSON contract (single source of truth)

Times are seconds on the native clip's timeline; `words` sorted by `start`, non-overlapping:

```json
{"practice_id": 7, "source": "mfa", "model": "french_mfa",
 "words": [{"word": "on", "start": 0.31, "end": 0.42}]}
```

## Manual fallback

MFA can misbehave on short conversational clips (e.g. English proper nouns like
"Ridley Scott" are out-of-vocabulary in `french_mfa` and get G2P-guessed or dropped).
Every downstream consumer is coupled to the contract above, not to MFA — so a
**hand-authored** `alignments/{id}.json` with `"source": "manual"`, timed by ear, is a
sanctioned drop-in substitute. Keep words sorted and non-overlapping.
