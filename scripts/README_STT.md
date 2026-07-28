# Speech-to-text (STT) — content-gate recognizer setup

The content gate (`backend/content_gate.py`, ticket 22) rejects unintelligible takes
before prosody scoring by **recognizing the words** and comparing them to the practice
transcript (word-error rate). Prosody alone can't tell gibberish from a genuine take.

The recognizer is **faster-whisper `base`**, quarantined in its own `stt` conda env —
never pip-install it into `backend/.venv` (no cp314 wheel for `ctranslate2`; the wheel
rule keeps it out of the venv). The app never imports faster-whisper: `content_gate.assess`
shells out with `conda run -n stt python stt_runner.py <wav>` and reads the recognized
text from stdout. A broken/missing env **fails open** (the take is scored anyway).

## One-time setup (rebuildable from scratch)

Requires conda (Miniconda or Anaconda). The env lands under `%USERPROFILE%\.conda\envs`,
so no admin rights are needed.

```sh
conda create -n stt python=3.11 -y
conda run -n stt pip install faster-whisper
# Warm the model once (downloads ~140MB to the HF cache on first use):
conda run -n stt python -c "from faster_whisper import WhisperModel; WhisperModel('base')"
```

Verify: `conda run -n stt python backend/stt_runner.py native_audio/napoleon_emulation.wav`
should print a near-transcription of "Hier soir, j'ai vu le film Napoléon de Ridley Scott."

## Calibrating the reject threshold

`CONTENT_GATE_MAX_WER` (in `content_gate.py`) is the max WER still judged intelligible.
Measure a single take's WER with the standalone CLI:

```sh
python backend/content_gate.py path/to/take.wav "Hier soir, j'ai vu le film..."
```

Graduated 2026-07-28 on the owner's calibration set (six correct takes + `gibberish{1..4}`):
correct WER 0.13–0.60, gibberish WER 1.00–1.40 → `CONTENT_GATE_MAX_WER = 0.80` (mid-gap,
biased high to protect real accented learners). See the Decision log in
`master_implementation_plan.md`.
