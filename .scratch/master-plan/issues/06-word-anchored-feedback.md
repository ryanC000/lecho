# 06 — Serve alignments + word-anchor the feedback segments

**What to build:** Feedback becomes linguistic instead of numeric: a segment card reads "on **les amis**" with timestamps demoted to secondary text. A public alignment endpoint serves each practice's word timings (404 when absent, like the native-audio route). After segment generation, the worker attaches to each segment the words whose intervals overlap it (`word.start < seg.end and word.end > seg.start`); segments with no overlapping words, and jobs on practices without alignments, keep rendering exactly as today.

**Blocked by:** 05 (alignment JSONs exist).

**Status:** ready-for-agent

- [ ] Alignment endpoint serves the contract JSON; 404 when no alignment exists
- [ ] New jobs on an aligned practice produce segments carrying words; the job payload exposes them
- [ ] Old jobs and unaligned practices render unchanged (null words)
- [ ] Segment cards show words prominently, timestamps secondary
