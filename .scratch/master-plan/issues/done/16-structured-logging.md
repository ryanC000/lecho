# 16 — Structured logging

**What to build:** The job pipeline becomes observable from the console: standard-library logging with a consistent `job=` prefix covering job creation (job, practice, mode, duration), every status transition, every failure with its reason, DSP wall-clock timings (extract/align/score), upload validation rejections, and bleed detections. JSON log formatting is explicitly deferred to Phase 3.

**Blocked by:** None — can start immediately. (Bleed-detection log point activates when ticket 08 lands.)

**Status:** done — 86850c2, 2026-08-08

- [x] A full job run reads as a coherent story in the console with a grep-able `job=` prefix — `test_successful_job_reads_as_one_story` asserts every `api.routes.jobs`/`worker.core` line for the run starts with `job=<id> `; the run reads: created (status/practice/mode/client_duration/user) → scoring started → content gate → dsp timings → `status=PENDING -> SUCCESS` with the axis scores.
- [x] Failures log the reason before the status flips — `fail_job` logs `job=… status=<old> -> FAILED reason=…` before mutating, so the reason survives a failed commit; `test_fail_job_logs_reason_before_status_flips` captures the job's status at emit time and pins it to `PENDING`. SUCCESS is deliberately the mirror image (logged *after* the commit) so the console can't claim a success that never landed.
- [x] DSP stage timings visible per job — one `job=… dsp extract=…s align=…s score=…s` line per job (`time.perf_counter`); `score=` covers `dsp.score` + `blend_content` only, with segment/archive construction moved after the log so the label stays honest.
- [x] No new logging dependency — stdlib `logging` only, `requirements.txt` untouched; `infra/logs.py` is a single `logging.basicConfig` (level + line format) called from the API lifespan.

## Notes

- Upload validation rejections are logged for both post-creation gates (the `ClipRejectedError` size/format/duration path and the server-derived per-mode duration gate), each with the job id. The three pre-job-creation 400/404s (invalid mode, practice not found, client-reported duration gate) are **not** logged: no job exists yet, so a line there would carry no `job=` prefix, and uvicorn's access log already records the status.
- One log point beyond the ticket's list: the content-gate outcome (`assessed`/`passed`/`wer`). It explains both a rejection's measurement and the gate's fail-open behaviour, which is otherwise silent.
- JSON formatting stays deferred to Phase 3 as specified — `infra/logs.py` is where that swap lands.
