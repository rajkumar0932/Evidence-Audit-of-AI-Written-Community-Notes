# Pre-registration: Evidence audit of AI-written Community Notes

**Stage 1 registered:** 13 Nov 2026 (IST). At this point no source had been fetched and no note in the sample had been judged; the only things inspected were population counts. This stage covers the question, data, sample, outcomes, hypotheses and analysis plan.
**Stage 2 amendment:** to be added *before* the main judging run. It will contain the frozen prompts with their SHA-256 hashes, and any changes made after the pilot.

## 1. Question

Do the sources that Community Notes cite actually support what the notes claim? Does that differ between notes written by X's Community Writer, by other AI writers, and by humans? And do the platform's signals (Helpful status, raters' source-related tags) track verified support?

## 2. Data

- **Source:** the public Community Notes dump of 2026-11-12 (`ton.twimg.com/birdwatch-public-data/2026/11/12/`). File hashes are in `data/raw/2026-11-12/SHA256SUMS`.
- **Main window:** notes created from 2026-08-14 00:00 UTC through 2026-10-31 23:59 UTC. This is at least 12 days before the dump.
- **Pilot window:** 2026-11-01 to 2026-11-09. Used for prompt development only and never analysed.

## 3. Groups

- **`cw`:** the six API accounts with the highest main-window volume. Their monthly volumes are near-identical (`data/release/ai_accounts.csv`), which is consistent with the six Community Writer accounts listed in `ACCOUNTS.md` of `xai-org/community-writer`. The mapping is checked by hand (`data/release/cw_mapping_check.csv`). If the check fails, `cw` and `ai_other` are pooled as "AI" and this is reported as a deviation.
- **`ai_other`:** the remaining accounts with `enrollmentState = apiEarnedIn`.
- **`human`:** all other authors.
- **Excluded:** collaborative notes (`isCollaborativeNote = 1`) and notes with no status row. The latter make up about 12–13% of every creation week, which is consistent with deleted notes rather than publication lag.

## 4. Sample (`scripts/02_sample.py`, seed 20261113)

- **Eligible notes:** main-window notes with at least 1 URL in the note text and a status row.
- **Strata:** 3 groups × {Currently Rated Helpful (CRH) 110, Currently Rated Not Helpful (CRNH) 78, Needs More Ratings (NMR) 80} = **804 notes**. `cw|CRNH` is a census, since exactly 78 such notes exist.
- **Sample IDs:** `data/release/sample_ids.csv`, sha256 `5339db3d9447362ddcefa1cd04f60f65f6ff6ef45e3a3f0ede1c56f6df01485b` (this file also lists the 40 pilot notes).
- **Population sizes and weights:** `data/release/strata_sizes.csv`.

## 5. Measurement

1. **Source retrieval.** Each URL is classified as `x_post`, `x_other`, `wiki`, `nontext` (video or social media) or `web`.
   - **Wikipedia:** the revision that was live when the note was created, via the MediaWiki API.
   - **Web:** the Wayback Machine snapshot closest *before* the note's creation time; failing that, one within 7 days after. Failing both, a live fetch, flagged as *unpinned*.
   - **Text extraction:** main text via trafilatura; PDFs via pypdf.
   - X posts and non-text media are not retrieved. They count towards checkability, not support.
2. **Claim decomposition.** An LLM splits each note into small, separately checkable claims, each typed as number/date, attribution/quote, event, causal, characterisation, or about-the-post. Claims about the post itself are out of scope and counted.
3. **Support verdict.** Each in-scope claim is judged against the retrieved text of the note's own sources as `SUPPORTED`, `PARTIAL`, `NOT_IN_SOURCE` or `CONTRADICTED`.
   - Every verdict must include a verbatim quote from the source.
   - A `SUPPORTED` verdict whose quote cannot be found in the retrieved text (after whitespace, case and quote-mark normalisation) is re-asked once, and otherwise coded `UNVERIFIED`.
   - The judge never sees the author group or the status.
4. **Judges.** Primary: `claude-opus-5-5`. Secondary, for robustness: a model from another family if one is available, otherwise `claude-sonnet-5-5`.
5. **Definitions.**
   - A claim is **checkable** if it is in scope and at least one of the note's cited sources was retrieved as text.
   - **Primary outcome (per note):** `UNSUPPORTED` = the note has at least one checkable claim labelled `NOT_IN_SOURCE` or `CONTRADICTED`. Notes with no checkable claim are excluded from this outcome and counted in the checkability analysis.
   - **Secondary outcomes:** claim-level support rate; `CONTRADICTED` rate; share of notes in which every in-scope claim is checkable.

## 6. Hypotheses

Each prior is our probability, before seeing data, that the hypothesis is true.

| # | Hypothesis | Test | Prior |
|---|---|---|---|
| H1 (primary) | Among CRH notes, the `UNSUPPORTED` rate differs between `cw` and `human`. | Two-sided permutation test, α = .05. The prior is for "`cw` higher". | 0.45 |
| H2a | Ratings track evidence: across groups (weighted), the `UNSUPPORTED` rate is higher for CRNH notes than for CRH notes. | One-sided, α = .05 | 0.65 |
| H2b | The CRNH − CRH gap is smaller for `cw` than for `human`. | Interaction term in the logistic regression (§7) | 0.50 |
| H3 | Among sampled notes with at least 5 ratings, the share of raters choosing *"Sources do not support note"* (`notHelpfulIrrelevantSources`) predicts `UNSUPPORTED` poorly. | AUROC < 0.65, judged from the point estimate and its 95% CI | 0.70 |
| D1 | Share of fully checkable notes per group. | Descriptive, no test | — |

## 7. Analysis

- **Cell estimates:** 95% bootstrap CIs (10,000 resamples of notes within each cell). Group contrasts are differences in proportions with bootstrap CIs and two-sided permutation p-values. Pooled estimates use the stratum weights.
- **Multiple comparisons:** Holm correction across H1, H2a and H3.
- **Regression for H2b:** `UNSUPPORTED ~ status × group + n_urls + note length + misleading-reason flags`.
- **Judge validation:**
  - 150 claim–source pairs, stratified by judge label and group, are labelled blind by a human.
  - Report Cohen's κ overall and split by AI vs human authorship, plus precision and recall for `UNSUPPORTED`.
  - **If κ < 0.60:** the headline results are reported on the human-labelled subset, and the judge-based results become secondary.
- **Sensitivity analyses:**
  - count `PARTIAL` as unsupported;
  - secondary judge only;
  - sources pinned via Wikipedia revision or Wayback only;
  - exclude Wikipedia;
  - leave out each `cw` account in turn;
  - human-labelled subset only.

## 8. Deviations

Any change after this commit is listed here with its date and reason.

- **2026-11-14, before any judging. Added an all-sources-retrieved sensitivity analysis.** It re-estimates every outcome on the notes whose cited sources were *all* retrieved as text. Reason: a note can cite a source that cannot be retrieved (for example an X post) alongside one that can. A claim backed only by the missing source would then be judged `NOT_IN_SOURCE` against the retrieved one, inflating `UNSUPPORTED`. Because missing sources are more common in human notes, this analysis is reported next to every primary estimate, not only in the appendix.
- **2026-11-14, procedure detail.** Claims are produced once, by the primary model at effort `medium`. Every judge then scores the same claims, at effort `high`.
- **2026-11-14, before any judging. How `UNVERIFIED` and `MISSING` verdicts count.** This was left unspecified in stage 1.
  - `UNVERIFIED`: support was claimed but no verifiable quote was given, even after the re-ask.
  - `MISSING`: no verdict was returned.
  - **Primary analysis:** both are excluded from a note's checkable claims.
  - **Sensitivity analysis:** `UNVERIFIED` is counted as unsupported.
- **2026-11-14, before any judging. H2a estimand made precise.** "Across groups (weighted)" now means the weighted average of the *within-group* differences, UNSUPPORTED(CRNH) − UNSUPPORTED(CRH). Each group is weighted by its CRH + CRNH population, and the test permutes status within groups. Reason: a dry run on synthetic data showed that pooling CRNH notes and CRH notes separately confounds the gap with group composition (`cw` has 12,668 CRH notes but only 78 CRNH notes).

## 9. Stage 2 amendment (15 Nov 2026, ~21:50 IST, before any main-sample note was judged)

**Model and runtime (deviation from §5.4).** We use `claude-haiku-5-5` as the primary model for both claim decomposition and verdicts. We do not use `claude-opus-5-5`.

- **How it runs:** through Claude Code's headless mode (`claude -p`) on the author's existing subscription, not through the paid Messages API.
- **Settings:** tools, MCP servers, skills and settings are disabled, and calls run from an empty working directory. Structured output uses `--json-schema`. Effort is `medium` for decomposition and `high` for verdicts.
- **Reason:** the sprint had no budget for paid API usage. The full audit costs about $2 at Haiku API-equivalent prices, against about $40–80 with Opus.
- **What does not change:** the prompts, schemas, quote verification, re-ask rule and outcomes.
- **Validation carries more weight:** judge accuracy is established by the blind human validation (§7), which matters more with a smaller model.
- **Second judge:** run on a subset if subscription usage allows.

**Frozen prompts:**

- `prompts/decompose.md`: SHA-256 `24c9df9a6b355d5331b2f55d4d2f1eeb0ead87d3285a14f73c6c80fbd888acf1`
- `prompts/judge.md`: SHA-256 `08d3b5a250b6d231ed4003691ba21ece4be29ca127e18dfcef46ef420f4fcecb`

**Pilot (40 notes from 1–9 Nov; never analysed).** Three rounds of prompts:

- **v0 to v1:**
  - The judge counted a source that merely repeats the corrected claim (a parody post) as contradicting the note. Added judge rule 4.
  - The decomposer attributed every listed finding to every listed piece of evidence. Added decomposition rule 3.
- **v1 to v2:** `CONTRADICTED` was over-used (6 of 154 verdicts, about half of them wrong). The causes were dropped qualifiers ("not announced", "just introduced") and a translation slip in an Arabic note. Added decomposition rule 4 (keep qualifiers; keep the note's language) and a qualifier clause in the `CONTRADICTED` definition.
- **v2, frozen:** 139 verdicts. 62 `SUPPORTED`, 25 `PARTIAL`, 50 `NOT_IN_SOURCE`, 2 `CONTRADICTED`. 89 of 89 quotes verified verbatim. One residual error was observed: a claim that lost its "in this case" qualifier.
