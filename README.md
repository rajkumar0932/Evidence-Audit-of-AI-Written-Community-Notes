# Do AI Fact-Checks Say What Their Sources Say?
### An Independent Evidence Audit of AI-Written Community Notes

AI now writes most of the Community Notes that X shows its users. This repository audits whether the sources a note cites actually support what the note claims, and whether the platform's signals track that support: Helpful status, and raters' own source tags.

Everything here was written during the Apart Research **AI x Epistemics Research Sprint** (13–16 Nov 2026). No code or data predates the sprint. The study was **pre-registered** before any evidence was retrieved (`PREREGISTRATION.md`; the git history shows the order of work).

## Findings (804 notes; 3,545 claims; Aug–Oct 2026)

- **Platform signals are blind to evidence.** Raters' "sources do not support note" tag detects unsupported notes at chance level (AUROC 0.53, 95% CI 0.48–0.58). Helpful and Not Helpful notes are unsupported at similar rates.
- **AI notes are better grounded than human notes.** On Helpful notes, 47% of claims by X's Community Writer and 51% by other AI writers are supported by their own sources, against 26% for human writers.
- **Unsupported claims are nevertheless the norm.** 56–81% of checkable notes in every group contain at least one claim their sources do not establish.
- **Much of the evidence cannot be checked.** Only 58% of notes have all their cited sources retrievable as text.
- **The findings do not depend on the judge.** An independent judge from another model family (Gemini) agrees with the primary judge (Claude) on 88% of claims (κ 0.75) and reproduces the findings.

The submitted report is `paper/report_apart.pdf` (Apart template; source `paper/report.md`), and its figures are in `paper/figures/`.

## Method in one paragraph

We take a stratified sample of notes by X's Community Writer, by other AI writers and by humans, across Helpful, Not Helpful and Needs-More-Ratings statuses. Each cited source is retrieved as it was when the note was written: the Wikipedia revision at that time, or the last Wayback Machine snapshot before it. Notes are split into claims. A judge labels each claim `SUPPORTED`, `PARTIAL`, `NOT_IN_SOURCE` or `CONTRADICTED`, and must quote the deciding passage verbatim; code then confirms the quote is in the source. The judge never sees who wrote the note or how it was rated.

## Reproduce

```bash
uv sync
# 1. Download the 2026-11-12 public Community Notes files listed in data/raw/2026-11-12/SHA256SUMS
uv run python scripts/01_build_frame.py        # sampling frame
uv run python scripts/02_sample.py             # seeded stratified sample
uv run python scripts/03_stream_ratings.py     # rater tags, streamed from the public ratings file
uv run python scripts/04_fetch_sources.py      # time-pinned source retrieval (resumable)
# 2. Judge. Use EITHER your own Anthropic API key (ANTHROPIC_API_KEY in .env) ...
uv run python scripts/05_judge.py submit decompose   # then: collect decompose / submit judge / collect judge
#    ... OR your own Claude Code login (no API key; runs `claude -p`):
uv run python scripts/05b_judge_cli.py run decompose
uv run python scripts/05b_judge_cli.py run judge
#    Optional second judge (your own GEMINI_API_KEY in .env, free tier):
uv run python scripts/05c_judge_gemini.py --model gemini-3.5-flash-lite
# 3. Analyse
uv run python scripts/07_analysis.py           # pre-registered tests -> data/release/results.json
uv run python scripts/12_judge_agreement.py    # judge agreement -> data/release/judge_agreement.json
uv run python scripts/10_figures.py            # figures -> paper/figures/
python verify.py                               # recompute headline numbers (standard library only)
```

No credentials are stored in this repository; `.env` is git-ignored.

## Files

| Path | Contents |
|---|---|
| `PREREGISTRATION.md` | Hypotheses, sample and analysis plan, plus dated deviations |
| `prompts/` | The frozen claim-splitting and judge prompts |
| `data/release/sample_ids.csv` | The 804 + 40 sampled note IDs and their strata |
| `data/release/verdicts_claude-haiku-5-5.csv` | Every claim with its verdict, verified quote and source |
| `data/release/note_outcomes.csv` | Per-note outcomes and rater-tag shares |
| `data/release/results.json` | Pre-registered tests |
| `data/release/judge_agreement.json` | Judge agreement and robustness |
| `data/release/validation_items.csv` | The 90-claim validation set, ready for human labelling |
| `data/release/retrieval_funnel.csv`, `rater_tags_population.csv` | Checkability and rater behaviour |

## Data

The data comes from X's public Community Notes download. Participant IDs are pseudonymous. We release note IDs, claims, verdicts and code, but not the note text, which can be rebuilt from the public data.
