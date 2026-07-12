"""Calibration harness CLI for dsp-2 scoring (master-plan Task 1.1 / ticket 02).

Answers "is dsp-2 scoring defensible on real audio?" from a corpus manifest
(ADR 0002: the owner's shadow-style emulation take must score high, a
deliberate monotone take must score clearly lower). Runs the pure scoring
pipeline per pair — no HTTP, no DB — and prints a table of all four score
components.

  python calibrate.py                 # score table + gate check on the corpus
  python calibrate.py --tune          # grid search + pitch-floor diagnostic
  python calibrate.py --smoke         # synthetic end-to-end run, no manifest
  python calibrate.py --manifest PATH # non-default manifest location

`--tune` grid-searches the scoring constants to maximize the worst-case
emulation-minus-monotone margin subject to every emulation scoring at least
GATE_EMULATION_MIN. Recommended constants are printed for a human to apply to
dsp.py deliberately — this script never edits code. Low-effort takes and the
PITCH_FLOOR_HZ sweep are diagnostics only (Phase 1R finding); they never
constrain the tuner.
"""
import argparse
import itertools
import json
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import dsp

DEFAULT_MANIFEST = Path(__file__).resolve().parent.parent / "native_audio" / "manifest.json"

# Graduation gates (ADR 0002).
GATE_EMULATION_MIN = 75.0
GATE_MARGIN_MIN = 20.0

SCORED_TAKES = ("emulation", "monotone")
DIAGNOSTIC_TAKES = ("low_effort",)

# --tune search space, keyed by the dsp.py constant each axis patches.
TUNE_GRID = {
    "DTW_ENERGY_LAMBDA": (0.25, 0.5, 1.0),
    "SCORE_K_PITCH_SEMITONES": (2.0, 3.0, 4.0, 6.0, 8.0, 12.0),
    # Real takes measure timing_rmse ~1.9 (2026-07-12 corpus run); an axis
    # capped at 0.6 pins every timing score near zero, so it reaches past 2.
    "SCORE_K_TIMING": (0.3, 0.6, 1.2, 2.4),
    "SCORE_K_ENERGY_Z": (0.75, 1.0, 1.5, 2.0, 3.0),
}
# (PITCH_WEIGHT, TIMING_WEIGHT, ENERGY_WEIGHT), each summing to 1.
WEIGHT_GRID = (
    (0.55, 0.25, 0.20),
    (0.60, 0.20, 0.20),
    (0.50, 0.30, 0.20),
    (0.45, 0.30, 0.25),
    (0.40, 0.35, 0.25),
)
PITCH_FLOOR_SWEEP_HZ = (60.0, 65.0, 75.0)  # diagnostic only (Phase 1R creak/octave finding)


@dataclass
class Row:
    practice_id: int
    take: str
    overall: float
    pitch: float
    timing: float
    energy: float
    diagnostic: bool


@contextmanager
def patched(**overrides):
    """Temporarily override module-level dsp constants (they are read at call
    time, so patching is enough to re-run any stage under trial values)."""
    saved = {name: getattr(dsp, name) for name in overrides}
    try:
        for name, value in overrides.items():
            setattr(dsp, name, value)
        yield
    finally:
        for name, value in saved.items():
            setattr(dsp, name, value)


def load_manifest(path: Path) -> list:
    """Parse the corpus manifest into entries of {practice_id, takes: {kind: Path}}.
    WAV paths are relative to the manifest's directory (ticket 02 contract)."""
    path = Path(path)
    base = path.parent
    entries = []
    for item in json.loads(path.read_text()):
        takes = {"reference": base / item["reference"]}
        for kind in SCORED_TAKES + DIAGNOSTIC_TAKES:
            if kind in item:
                takes[kind] = base / item[kind]
        missing = [str(p) for p in takes.values() if not p.exists()]
        if missing:
            raise FileNotFoundError(f"practice {item['practice_id']}: missing {', '.join(missing)}")
        entries.append({"practice_id": item["practice_id"], "takes": takes})
    return entries


def extract_corpus(entries: list) -> dict:
    """(practice_id, kind) -> trimmed ProsodyFeatures for every corpus file."""
    return {
        (entry["practice_id"], kind): dsp.features_for(path)
        for entry in entries
        for kind, path in entry["takes"].items()
    }


def corpus_rows(entries: list, feats: dict = None) -> list:
    """Score every (take vs reference) pair with the current dsp constants."""
    feats = feats if feats is not None else extract_corpus(entries)
    rows = []
    for entry in entries:
        pid = entry["practice_id"]
        for kind in SCORED_TAKES + DIAGNOSTIC_TAKES:
            if kind not in entry["takes"]:
                continue
            aligned = dsp.align(feats[(pid, "reference")], feats[(pid, kind)])
            overall, pitch, timing, energy = dsp.score(aligned)
            rows.append(Row(pid, kind, overall, pitch, timing, energy, kind in DIAGNOSTIC_TAKES))
    return rows


def gate_report(rows: list) -> list:
    """Per practice: (practice_id, emulation, monotone, margin, passes_both_gates)."""
    by_pid = {}
    for row in rows:
        by_pid.setdefault(row.practice_id, {})[row.take] = row.overall
    report = []
    for pid, takes in sorted(by_pid.items()):
        emu, mono = takes["emulation"], takes["monotone"]
        margin = emu - mono
        passed = emu >= GATE_EMULATION_MIN and margin >= GATE_MARGIN_MIN
        report.append((pid, emu, mono, margin, passed))
    return report


def print_table(rows: list) -> None:
    print(f"{'practice':>8}  {'take':<12} {'overall':>7} {'pitch':>7} {'timing':>7} {'energy':>7}")
    for r in rows:
        take = r.take + (" *" if r.diagnostic else "")
        print(f"{r.practice_id:>8}  {take:<12} {r.overall:>7.1f} {r.pitch:>7.1f} {r.timing:>7.1f} {r.energy:>7.1f}")
    if any(r.diagnostic for r in rows):
        print("  (* diagnostic row - never constrains tuning)")


def print_gates(rows: list) -> bool:
    all_pass = True
    for pid, emu, mono, margin, passed in gate_report(rows):
        print(
            f"practice {pid}: emulation {emu:.1f} (gate >= {GATE_EMULATION_MIN:.0f}), "
            f"margin {margin:.1f} (gate >= {GATE_MARGIN_MIN:.0f}) -> {'PASS' if passed else 'FAIL'}"
        )
        all_pass = all_pass and passed
    print(f"graduation gates: {'PASS' if all_pass else 'FAIL'}")
    return all_pass


# ---------------------------------------------------------------------------
# --tune: grid search over the scoring constants
# ---------------------------------------------------------------------------

def tune(entries: list, feats: dict) -> dict:
    """Best constants per the ADR 0002 objective: maximize the worst-case
    emulation-minus-monotone margin subject to every emulation >= the gate
    (tie-break: higher worst-case emulation). Returns the best combo whether
    or not it is feasible; 'feasible' says if the gate held."""
    # Features don't depend on any tuned constant; alignments depend only on
    # DTW_ENERGY_LAMBDA. Cache Aligned per lambda, then sweeping the score
    # constants is pure arithmetic.
    best = None
    for lam in TUNE_GRID["DTW_ENERGY_LAMBDA"]:
        with patched(DTW_ENERGY_LAMBDA=lam):
            aligned = {
                (entry["practice_id"], kind): dsp.align(
                    feats[(entry["practice_id"], "reference")],
                    feats[(entry["practice_id"], kind)],
                )
                for entry in entries
                for kind in SCORED_TAKES
            }
        for k_pitch, k_timing, k_energy in itertools.product(
            TUNE_GRID["SCORE_K_PITCH_SEMITONES"],
            TUNE_GRID["SCORE_K_TIMING"],
            TUNE_GRID["SCORE_K_ENERGY_Z"],
        ):
            for w_pitch, w_timing, w_energy in WEIGHT_GRID:
                with patched(
                    SCORE_K_PITCH_SEMITONES=k_pitch,
                    SCORE_K_TIMING=k_timing,
                    SCORE_K_ENERGY_Z=k_energy,
                    PITCH_WEIGHT=w_pitch,
                    TIMING_WEIGHT=w_timing,
                    ENERGY_WEIGHT=w_energy,
                ):
                    overalls = {key: dsp.score(a)[0] for key, a in aligned.items()}
                min_emu = min(
                    overalls[(e["practice_id"], "emulation")] for e in entries
                )
                min_margin = min(
                    overalls[(e["practice_id"], "emulation")]
                    - overalls[(e["practice_id"], "monotone")]
                    for e in entries
                )
                candidate = {
                    "constants": {
                        "DTW_ENERGY_LAMBDA": lam,
                        "SCORE_K_PITCH_SEMITONES": k_pitch,
                        "SCORE_K_TIMING": k_timing,
                        "SCORE_K_ENERGY_Z": k_energy,
                        "PITCH_WEIGHT": w_pitch,
                        "TIMING_WEIGHT": w_timing,
                        "ENERGY_WEIGHT": w_energy,
                    },
                    "min_emulation": min_emu,
                    "min_margin": min_margin,
                    "feasible": min_emu >= GATE_EMULATION_MIN,
                }
                if best is None or _beats(candidate, best):
                    best = candidate
    return best


def _beats(a: dict, b: dict) -> bool:
    """Feasible beats infeasible; then larger worst-case margin; then larger
    worst-case emulation (infeasible combos rank by emulation first, so the
    'least bad' one is reported when nothing passes the gate)."""
    if a["feasible"] != b["feasible"]:
        return a["feasible"]
    if a["feasible"]:
        key_a = (a["min_margin"], a["min_emulation"])
        key_b = (b["min_margin"], b["min_emulation"])
    else:
        key_a = (a["min_emulation"], a["min_margin"])
        key_b = (b["min_emulation"], b["min_margin"])
    return key_a > key_b


def pitch_floor_sweep(entries: list) -> None:
    """Diagnostic only (Phase 1R): re-extract at each candidate floor and
    re-score with the current constants, plus median voiced F0 per take so
    octave/creak artifacts near the floor are visible."""
    import numpy as np

    for floor in PITCH_FLOOR_SWEEP_HZ:
        with patched(PITCH_FLOOR_HZ=floor):
            feats = extract_corpus(entries)
            rows = corpus_rows(entries, feats)
        print(f"\nPITCH_FLOOR_HZ = {floor:.0f} (diagnostic)")
        print_table(rows)
        for (pid, kind), feat in sorted(feats.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            med_f0 = float(np.median(feat.f0_hz[feat.voiced]))
            print(f"  practice {pid} {kind}: median F0 {med_f0:.0f} Hz, voiced {feat.voiced.mean():.0%}")
        print_gates(rows)


# ---------------------------------------------------------------------------
# --smoke: synthetic corpus so the harness runs before any recording exists
# ---------------------------------------------------------------------------

def build_smoke_corpus(dirpath) -> list:
    """Two synthetic entries mirroring the corpus shape: emulation = the
    native contour reproduced exactly (the pipeline check is that this ranks
    clearly above the flat monotone; a merely similar chirp makes DTW zig-zag
    and craters the timing score), monotone = flat tone at the same mean Hz."""
    from test_dsp import _write_sine_wav  # reuse (master plan Task 1.1)

    dirpath = Path(dirpath)

    def wav(name, f0, dur, f1=None):
        path = dirpath / name
        _write_sine_wav(path, freq_hz=f0, duration_s=dur, freq_end_hz=f1)
        return path

    return [
        {
            "practice_id": 901,
            "takes": {
                "reference": wav("s901_native.wav", 130.0, 1.5, 170.0),
                "emulation": wav("s901_emulation.wav", 130.0, 1.5, 170.0),
                "monotone": wav("s901_monotone.wav", 150.0, 1.5),
                "low_effort": wav("s901_low_effort.wav", 150.0, 1.9, 140.0),
            },
        },
        {
            "practice_id": 902,
            "takes": {
                "reference": wav("s902_native.wav", 170.0, 2.0, 120.0),
                "emulation": wav("s902_emulation.wav", 170.0, 2.0, 120.0),
                "monotone": wav("s902_monotone.wav", 145.0, 2.0),
            },
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--tune", action="store_true", help="grid-search the scoring constants")
    parser.add_argument("--smoke", action="store_true", help="run on synthetic WAVs (no manifest needed)")
    args = parser.parse_args()

    if args.smoke:
        with tempfile.TemporaryDirectory() as tmp:
            _run(build_smoke_corpus(tmp), args.tune)
            return 0  # smoke succeeds by running; gates only bind on the real corpus
    if not args.manifest.exists():
        parser.error(f"manifest not found: {args.manifest} (record the corpus per ticket 03, or use --smoke)")
    return _run(load_manifest(args.manifest), args.tune)


def _run(entries: list, do_tune: bool) -> int:
    feats = extract_corpus(entries)
    rows = corpus_rows(entries, feats)
    print("Scores with current dsp.py constants:")
    print_table(rows)
    all_pass = print_gates(rows)

    if do_tune:
        best = tune(entries, feats)
        print("\n--tune result (objective: max worst-case emulation-monotone margin,")
        print(f"subject to every emulation >= {GATE_EMULATION_MIN:.0f}; ADR 0002):")
        print(f"  feasible: {best['feasible']}")
        print(f"  worst-case emulation: {best['min_emulation']:.1f}")
        print(f"  worst-case margin:    {best['min_margin']:.1f}")
        print("  recommended constants (apply to dsp.py manually):")
        for name, value in best["constants"].items():
            print(f"    {name} = {value}")
        with patched(**best["constants"]):
            print("\nScores with recommended constants:")
            tuned_rows = corpus_rows(entries, feats)
            print_table(tuned_rows)
            all_pass = print_gates(tuned_rows)
        pitch_floor_sweep(entries)

    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
