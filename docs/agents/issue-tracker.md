# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01` — never a single combined tickets file
- Triage state is recorded as a `Status:` line near the top of each issue file (canonical roles: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`)
- Comments and conversation history append to the bottom of the file under a `## Comments` heading
- Blocking edges are a `Blocked by:` line near the top; a ticket is workable when every ticket it lists is done

Chosen by the owner on 2026-07-11 (during `/to-tickets` on the master implementation plan).
