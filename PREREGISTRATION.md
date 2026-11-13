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

- *(none yet)*

## 9. Stage 2 amendment (before the main judging run)

- Prompt files and SHA-256: *TBD*
- Pilot observations and prompt changes: *TBD*
