"""Calibration harness CLI for dsp-2 scoring (master-plan Task 1.1 / ticket 02).

Answers "is the scoring defensible on real audio?" from a corpus manifest
(ADR 0002: the owner's shadow-style emulation take must score high, a
deliberate bad take must score clearly lower). The bad take is per-entry
(ADR 0003): monotone for an expressive native clip, low_effort for a flat one
— French natives are typically flat, and against a flat reference an
articulate, rhythm-correct monotone IS a faithful imitation, so it cannot be
the discrimination target there. Runs the pure scoring pipeline per pair — no
HTTP, no DB — and prints a table of all four score components.

  python calibrate.py                 # score table + gate check on the corpus
  python calibrate.py --tune          # grid search + pitch-floor diagnostic
  python calibrate.py --smoke         # synthetic end-to-end run, no manifest
  python calibrate.py --manifest PATH # non-default manifest location

`--tune` grid-searches the scoring constants to maximize the worst-case
margin slack (emulation minus its entry's bad take, minus that entry's margin
gate) subject to every emulation scoring at least GATE_EMULATION_MIN.
Recommended constants are printed for a human to apply to dsp.py deliberately
— this script never edits code. Takes that are not an entry's bad take and
the PITCH_FLOOR_HZ sweep are diagnostics only; they never constrain the tuner.
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

# Graduation gates (ADR 0003; supersedes ADR 0002's aspirational 75/20).
# Set from the measured 2026-07-13 frontier: on the single-voice corpus the
# max achievable worst-case margin is ~4-5 points at ANY constants (pushing
# emulation >= 75 squeezes it to ~3.3), so the gates encode achieved reality
# — emulation >= 70 with a >= 3 point margin — not a hoped-for separation.
GATE_EMULATION_MIN = 70.0
GATE_MARGIN_MIN = 3.0        # expressive native: emulation vs monotone
GATE_MARGIN_FLAT_MIN = 3.0   # flat native: emulation vs low_effort
# Below this semitone std (voiced frames of the native clip) a deliberate
# monotone genuinely resembles the reference (2026-07-12 finding: practice 7
# at 2.1 st anti-discriminates, practice 2 at 3.8 st orders correctly), so
# the meaningful bad take becomes low_effort (ADR 0003).
FLAT_NATIVE_ST_STD = 3.0

TAKE_KINDS = ("emulation", "monotone", "low_effort")

# --tune search space, keyed by the dsp.py constant each axis patches.
TUNE_GRID = {
    "DTW_ENERGY_LAMBDA": (0.25, 0.5, 1.0),
    "SCORE_K_PITCH_SEMITONES": (2.0, 3.0, 4.0, 6.0, 8.0, 12.0),
    # Real emulation takes measure timing_rmse ~1.2-1.5 after the
    # SLOPE_WINDOW_S fix (2026-07-13 corpus run; was ~1.9 at the 0.15 window).
    "SCORE_K_TIMING": (1.2, 1.8, 2.4, 3.0, 4.0),
    "SCORE_K_ENERGY_Z": (0.75, 1.0, 1.5, 2.0, 3.0),
}
# (PITCH_WEIGHT, TIMING_WEIGHT, ENERGY_WEIGHT), each summing to 1.
WEIGHT_GRID = (
    (0.55, 0.25, 0.20),
    (0.60, 0.20, 0.20),
    (0.50, 0.30, 0.20),
    (0.45, 0.30, 0.25),
    (0.40, 0.35, 0.25),
    # Low-pitch-weight vectors for flat-language content (ADR 0003): timing
    # is the discriminating axis when the native contour is near-flat.
    (0.35, 0.40, 0.25),
    (0.30, 0.40, 0.30),
    (0.20, 0.60, 0.20),
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
        for kind in TAKE_KINDS:
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


def native_st_stds(entries: list, feats: dict) -> dict:
    """practice_id -> semitone std over the native clip's voiced frames (the
    ADR 0003 flat/expressive discriminator)."""
    import numpy as np

    return {
        entry["practice_id"]: float(
            np.std(
                feats[(entry["practice_id"], "reference")].f0_semitone[
                    feats[(entry["practice_id"], "reference")].voiced
                ]
            )
        )
        for entry in entries
    }


def bad_take_kind(st_std: float) -> str:
    """ADR 0003: which take an entry's discrimination margin is measured against."""
    return "monotone" if st_std >= FLAT_NATIVE_ST_STD else "low_effort"


def margin_gate(st_std: float) -> float:
    return GATE_MARGIN_MIN if st_std >= FLAT_NATIVE_ST_STD else GATE_MARGIN_FLAT_MIN


def corpus_rows(entries: list, feats: dict = None) -> list:
    """Score every (take vs reference) pair with the current dsp constants."""
    feats = feats if feats is not None else extract_corpus(entries)
    stds = native_st_stds(entries, feats)
    rows = []
    for entry in entries:
        pid = entry["practice_id"]
        gated = ("emulation", bad_take_kind(stds[pid]))
        for kind in TAKE_KINDS:
            if kind not in entry["takes"]:
                continue
            aligned = dsp.align(feats[(pid, "reference")], feats[(pid, kind)])
            overall, pitch, timing, energy = dsp.score(aligned)
            rows.append(Row(pid, kind, overall, pitch, timing, energy, kind not in gated))
    return rows


def gate_report(rows: list, stds: dict) -> list:
    """Per practice: (pid, emulation, bad_kind, bad_overall, margin, gate, passed)."""
    by_pid = {}
    for row in rows:
        by_pid.setdefault(row.practice_id, {})[row.take] = row.overall
    report = []
    for pid, takes in sorted(by_pid.items()):
        kind = bad_take_kind(stds[pid])
        if kind not in takes:
            raise ValueError(
                f"practice {pid}: flat native (semitone std {stds[pid]:.1f} < "
                f"{FLAT_NATIVE_ST_STD}) needs a {kind} take (ADR 0003)"
            )
        emu, bad = takes["emulation"], takes[kind]
        margin = emu - bad
        gate = margin_gate(stds[pid])
        passed = emu >= GATE_EMULATION_MIN and margin >= gate
        report.append((pid, emu, kind, bad, margin, gate, passed))
    return report


def print_table(rows: list) -> None:
    print(f"{'practice':>8}  {'take':<12} {'overall':>7} {'pitch':>7} {'timing':>7} {'energy':>7}")
    for r in rows:
        take = r.take + (" *" if r.diagnostic else "")
        print(f"{r.practice_id:>8}  {take:<12} {r.overall:>7.1f} {r.pitch:>7.1f} {r.timing:>7.1f} {r.energy:>7.1f}")
    if any(r.diagnostic for r in rows):
        print("  (* diagnostic row - never constrains tuning)")


def print_gates(rows: list, stds: dict) -> bool:
    all_pass = True
    for pid, emu, kind, bad, margin, gate, passed in gate_report(rows, stds):
        flat = " flat," if stds[pid] < FLAT_NATIVE_ST_STD else ""
        print(
            f"practice {pid} (native std {stds[pid]:.1f} st,{flat} bad take = {kind}): "
            f"emulation {emu:.1f} (gate >= {GATE_EMULATION_MIN:.0f}), "
            f"margin {margin:.1f} (gate >= {gate:.0f}) -> {'PASS' if passed else 'FAIL'}"
        )
        all_pass = all_pass and passed
    print(f"graduation gates: {'PASS' if all_pass else 'FAIL'}")
    return all_pass


# ---------------------------------------------------------------------------
# --tune: grid search over the scoring constants
# ---------------------------------------------------------------------------

def tune(entries: list, feats: dict) -> dict:
    """Best constants per the ADR 0002/0003 objective: maximize the worst-case
    margin slack — (emulation minus the entry's bad take) minus the entry's
    margin gate — subject to every emulation >= the gate (tie-break: higher
    worst-case emulation). Slack, not raw margin, because flat and expressive
    entries gate at different values and the worst case must be comparable.
    Returns the best combo whether or not it is feasible; 'feasible' says if
    the emulation gate held."""
    # Features don't depend on any tuned constant; alignments depend only on
    # DTW_ENERGY_LAMBDA. Cache Aligned per lambda, then sweeping the score
    # constants is pure arithmetic.
    stds = native_st_stds(entries, feats)
    gated = {
        entry["practice_id"]: ("emulation", bad_take_kind(stds[entry["practice_id"]]))
        for entry in entries
    }
    best = None
    for lam in TUNE_GRID["DTW_ENERGY_LAMBDA"]:
        with patched(DTW_ENERGY_LAMBDA=lam):
            aligned = {
                (entry["practice_id"], kind): dsp.align(
                    feats[(entry["practice_id"], "reference")],
                    feats[(entry["practice_id"], kind)],
                )
                for entry in entries
                for kind in gated[entry["practice_id"]]
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
                min_margin_slack = min(
                    overalls[(e["practice_id"], "emulation")]
                    - overalls[(e["practice_id"], gated[e["practice_id"]][1])]
                    - margin_gate(stds[e["practice_id"]])
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
                    "min_margin_slack": min_margin_slack,
                    "feasible": min_emu >= GATE_EMULATION_MIN,
                }
                if best is None or _beats(candidate, best):
                    best = candidate
    return best


def _beats(a: dict, b: dict) -> bool:
    """Feasible beats infeasible; then larger worst-case margin slack; then
    larger worst-case emulation (infeasible combos rank by emulation first, so
    the 'least bad' one is reported when nothing passes the gate)."""
    if a["feasible"] != b["feasible"]:
        return a["feasible"]
    if a["feasible"]:
        key_a = (a["min_margin_slack"], a["min_emulation"])
        key_b = (b["min_margin_slack"], b["min_emulation"])
    else:
        key_a = (a["min_emulation"], a["min_margin_slack"])
        key_b = (b["min_emulation"], b["min_margin_slack"])
    return key_a > key_b


def probe_mfcc(entries: list, feats: dict) -> None:
    """Diagnostic only (ADR 0003): would a segmental (MFCC) axis discriminate
    take quality? Per-take MFCC RMSE vs the reference, projected through the
    same DTW path the scorer uses. Go/no-go criterion: integrate an MFCC axis
    only if min over practices of (bad_take_rmse - emulation_rmse) >= 0.15.
    2026-07-13 verdict: NO-GO — the cross-speaker spectral floor dwarfs the
    take-level spread; all takes articulate the same words.
    """
    import numpy as np

    def mfcc_z(path, feat):
        """12 CMVN'd MFCCs (c0 dropped) on the take's trimmed frame grid."""
        snd = dsp.load_mono_16k(path)
        mfcc = snd.to_mfcc(number_of_coefficients=12, window_length=0.025, time_step=dsp.FRAME_HOP_S)
        arr = mfcc.to_array()[1:]  # row 0 is c0 (loudness), not spectral shape
        grid = mfcc.xs()
        rows = np.vstack([np.interp(feat.times, grid, row) for row in arr])
        mean = rows.mean(axis=1, keepdims=True)
        std = np.maximum(rows.std(axis=1, keepdims=True), 1e-12)
        return (rows - mean) / std

    print("\nMFCC probe (diagnostic - segmental axis go/no-go, ADR 0003):")
    print(f"{'practice':>8}  {'take':<12} {'mfcc_rmse':>9} {'gap_vs_emu':>10}")
    for entry in entries:
        pid = entry["practice_id"]
        ref_feat = feats[(pid, "reference")]
        ref_mfcc = mfcc_z(entry["takes"]["reference"], ref_feat)
        rmses = {}
        for kind in TAKE_KINDS:
            if kind not in entry["takes"]:
                continue
            take_feat = feats[(pid, kind)]
            aligned = dsp.align(ref_feat, take_feat)
            take_mfcc = mfcc_z(entry["takes"][kind], take_feat)
            on_native = np.vstack(
                [dsp._apply_path_mean(aligned.path, len(ref_feat), row) for row in take_mfcc]
            )
            rmses[kind] = float(np.sqrt(np.mean((ref_mfcc - on_native) ** 2)))
        for kind, rmse in rmses.items():
            gap = rmse - rmses["emulation"]
            print(f"{pid:>8}  {kind:<12} {rmse:>9.3f} {gap:>+10.3f}")
    print("  (integrate MFCC only if every bad-take gap_vs_emu >= 0.15)")


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
        print_gates(rows, native_st_stds(entries, feats))


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
                # A linear chirp's semitone std is well under FLAT_NATIVE_ST_STD,
                # so ADR 0003 classifies both smoke entries as flat and gates
                # them on low_effort — every entry needs one.
                "low_effort": wav("s902_low_effort.wav", 145.0, 2.4, 135.0),
            },
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--tune", action="store_true", help="grid-search the scoring constants")
    parser.add_argument("--smoke", action="store_true", help="run on synthetic WAVs (no manifest needed)")
    parser.add_argument("--only", type=int, default=None, help="restrict to one practice_id")
    parser.add_argument("--probe-mfcc", action="store_true", help="diagnostic: would a segmental (MFCC) axis discriminate?")
    args = parser.parse_args()

    if args.smoke:
        with tempfile.TemporaryDirectory() as tmp:
            _run(build_smoke_corpus(tmp), args.tune, args.probe_mfcc)
            return 0  # smoke succeeds by running; gates only bind on the real corpus
    if not args.manifest.exists():
        parser.error(f"manifest not found: {args.manifest} (record the corpus per ticket 03, or use --smoke)")
    entries = load_manifest(args.manifest)
    if args.only is not None:
        entries = [e for e in entries if e["practice_id"] == args.only]
        if not entries:
            parser.error(f"practice {args.only} not in manifest")
    return _run(entries, args.tune, args.probe_mfcc)


def _run(entries: list, do_tune: bool, do_probe_mfcc: bool = False) -> int:
    feats = extract_corpus(entries)
    stds = native_st_stds(entries, feats)
    rows = corpus_rows(entries, feats)
    print("Scores with current dsp.py constants:")
    print_table(rows)
    all_pass = print_gates(rows, stds)

    if do_tune:
        best = tune(entries, feats)
        print("\n--tune result (objective: max worst-case margin slack vs each")
        print("entry's bad take and margin gate, subject to every emulation")
        print(f">= {GATE_EMULATION_MIN:.0f}; ADR 0002/0003):")
        print(f"  feasible: {best['feasible']}")
        print(f"  worst-case emulation:    {best['min_emulation']:.1f}")
        print(f"  worst-case margin slack: {best['min_margin_slack']:.1f}")
        print("  recommended constants (apply to dsp.py manually):")
        for name, value in best["constants"].items():
            print(f"    {name} = {value}")
        with patched(**best["constants"]):
            print("\nScores with recommended constants:")
            tuned_rows = corpus_rows(entries, feats)
            print_table(tuned_rows)
            all_pass = print_gates(tuned_rows, stds)
        pitch_floor_sweep(entries)

    if do_probe_mfcc:
        probe_mfcc(entries, feats)

    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
