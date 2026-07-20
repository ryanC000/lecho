# 06 — Serve alignments + word-anchor the feedback segments

**What to build:** Feedback becomes linguistic instead of numeric: a segment card reads "on **les amis**" with timestamps demoted to secondary text. A public alignment endpoint serves each practice's word timings (404 when absent, like the native-audio route). After segment generation, the worker attaches to each segment the words whose intervals overlap it (`word.start < seg.end and word.end > seg.start`); segments with no overlapping words, and jobs on practices without alignments, keep rendering exactly as today.

**Blocked by:** 05 (alignment JSONs exist).

**Status:** done (commit `8e78e64`, 2026-07-20)

- [x] Alignment endpoint serves the contract JSON; 404 when no alignment exists (`test_alignment_endpoint_404_then_serves_contract`)
- [x] New jobs on an aligned practice produce segments carrying words; the job payload exposes them (`test_aligned_job_attaches_overlapping_words`; `segments[].words` in `GET /jobs/{id}`)
- [x] Old jobs and unaligned practices render unchanged (null words) (`test_unaligned_job_segments_have_null_words`)
- [x] Segment cards show words prominently, timestamps secondary (`.feedback-words` headline + demoted `.feedback-time-secondary`; `Results.test.jsx` asserts the rendered words)
