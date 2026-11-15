# Do AI Fact-Checks Say What Their Sources Say? An Independent Evidence Audit of AI-Written Community Notes

**Raj Gupta** · [affiliation] · AI x Epistemics Research Sprint (Apart Research), 13–16 Nov 2026
Code and data: https://github.com/rajkumar0932/Evidence-Audit-of-AI-Written-Community-Notes

*Draft. Bracketed **[TBD]** items are filled in from `data/release/results.json` once the judging run completes.*

## Abstract

AI accounts wrote 61% of the Community Notes on X that reached "Helpful" status in Aug–Oct 2026, most of them six accounts run by X's own Community Writer. Every published evaluation of these notes, X's own included, measures rater approval; none checks whether a note's cited sources support what it says. We audit a stratified sample of 804 notes written by X's Community Writer, by other AI writers and by humans, rated Helpful, Not Helpful or Needs More Ratings. We pin each cited source to its version when the note was written, split notes into claims, and require every "supported" verdict to quote a passage that we then verify mechanically. A blind human audit validates the judge (κ = [TBD]). [Headline 1: share of Helpful notes with at least one claim their own sources do not support, by writer, with CIs.] [Headline 2: whether Helpful status tracks support.] [Headline 3: how well raters' "sources do not support note" tag detects unsupported notes, AUROC.] Only 58% of sampled notes could be fully bound to retrievable evidence, and 44% to evidence pinned to the time of writing. Evidence hosted on X cannot be audited without platform access. The study was pre-registered before any evidence was retrieved. We release the sample, verdicts, quote-verification code and a re-runnable audit. *(target 150–250 words)*

## 1. Introduction

Community Notes is the largest crowd fact-checking system in deployment. A note is shown to users only when raters who usually disagree with each other both rate it helpful. Since September 2025, X has also accepted notes written by AI through its AI Note Writer API. In our window (notes created 14 Aug–31 Oct 2026), AI accounts wrote **61%** of the notes that reached Helpful status: 14,156 of 23,136. Six accounts with near-identical monthly quotas wrote 87.5% of all AI notes. Their volumes match the six accounts that X's open-source Community Writer lists as its own (§3.1).

Three 2026 studies evaluate these AI notes, including one by the X engineers who built the Community Writer. All three measure quality as a platform outcome: whether the note reached Helpful status, how quickly, and with how many ratings [Gong & Wu 2026; De et al. 2026; Miller et al. 2026]. None checks whether the sources a note cites actually establish what it claims. Miller et al. name "whether helpfulness ratings track factual accuracy and source quality" as an open question. Gong & Wu list evidence-grounding assessment as future work.

The gap matters for three reasons:

- **The AI writers are optimised against the proxy.** The Community Writer's quality gates are LLM predictions of what raters will find helpful. It also has a model that deletes drafts predicted to fail before they are rated. In its own pipeline the same model family drafts the note and checks its sources: Grok is told to "confirm that the content of the URL supports" each note.
- **It is a deployed instance of scalable oversight.** AI writes, humans rate, and an algorithm decides what millions of users see. Whether the human layer actually checks evidence is an empirical question.
- **What can be checked decides what can be trusted.** It matters what fraction of a live fact-checking system's evidence an outsider can bind to retrievable text.

**Contributions.**

1. The first claim-level, time-pinned audit of the evidence behind AI-written Community Notes, compared with human-written notes.
2. Pre-registered tests of whether Helpful status and raters' own source tags track verified evidence support.
3. A checkability funnel: the share of a live fact-checking system's cited evidence that can be retrieved and pinned to the time of writing.
4. An open, re-runnable audit, with quote-anchored verdicts that anyone can check by string match.

## 2. Background and related work

**Community Notes and AI writers.** Notes reach "Currently Rated Helpful" (CRH) status through a matrix-factorisation model that requires agreement across raters who usually disagree. Notes that fail reach "Currently Rated Not Helpful" (CRNH), and most notes stay at "Needs More Ratings" (NMR). Since the AI Note Writer API opened, AI accounts have grown quickly:

- **Gong & Wu (2026)** studied 20 AI writers up to May 2026. They found AI writers to be fast and prolific, with mean CRH rates (12.1%) between those of experts and laypeople. Their measure of veracity is platform status.
- **De et al. (2026)** studied human feedback on AI-drafted collaborative notes.
- **Miller et al. (2026)**, X engineers, describe the Community Writer. It runs two Grok-based writers with web, URL and X search tools, plus several rejectors: a helpfulness predictor, a screenshot checker, a recent-context check and a revision check. Its writer instructions require confirming that each URL supports the note.
- **Journalism:** Indicator (16 Oct 2026) reported that six X-run accounts wrote more than 90% of AI notes in September 2026.

**Sources in Community Notes.** Earlier work rates the *outlets* that notes cite, not whether a cited page supports the specific claim:

- Kangur et al. (2024) found cited sources skew towards high-factuality, left-leaning outlets.
- Solovev & Pröllochs (2025) found that linking external sources raises the odds of a note being rated helpful (2.7×), and that high-bias sources lower it.

**Checking claims against cited sources.** Several methods test whether generated text is supported by its sources:

- AIS (Rashkin et al. 2023) formalises "attributable to identified sources".
- ALCE (Gao et al. 2023) scores citation precision and recall.
- FActScore (Min et al. 2023) splits text into atomic facts and checks each one.
- SourceCheckup (Wu et al. 2025) found that 50–90% of LLM medical answers were not fully supported by the sources they cited. About 30% of individual statements were unsupported even with web search.

We apply this family of methods to a live, rater-governed deployment. We add two things: sources pinned to the time of writing, and quotes verified mechanically.

## 3. Data and methods

The study was **pre-registered** in `PREREGISTRATION.md`, committed on 13 Nov 2026 at 23:57 IST, before any source was retrieved or any note judged. Changes made later, all before judging, are listed with dates in Appendix C.

### 3.1 Data and groups

We use X's public Community Notes dump of 12 Nov 2026 (notes, status history, user enrollment and ratings; checksums are in the repository).

- **Window:** notes created 14 Aug–31 Oct 2026, which leaves at least 12 days for statuses to settle. That is 286,940 notes.
- **AI writers:** accounts with `enrollmentState = apiEarnedIn` (41 accounts; 28 active in the window).
- **X's Community Writer (`cw`):** we label the six highest-volume API accounts as `cw`. Their monthly volumes are near-identical (Aug 3,779–3,857; Sep 7,374–7,510; Oct 8,688–8,825), consistent with fixed quotas and with the six accounts listed in the Community Writer's `ACCOUNTS.md`. We verified this mapping by hand [TBD: n notes checked].
- **Other groups:** `ai_other` is the remaining API accounts; `human` is everyone else.
- **Exclusions:**
  - collaborative notes;
  - notes with no status row (12.7%). That share is stable across creation weeks, consistent with deleted notes rather than publication lag. The Community Writer deletes drafts predicted to fail, so deleted notes are a known blind spot (Appendix A).

### 3.2 Sample

We drew a seeded stratified sample of notes containing at least one URL:

- **Strata:** 3 groups × 3 statuses. That is 110 CRH, 78 CRNH and 80 NMR notes per group, **804 notes** in total.
- **Census cell:** `cw` has exactly 78 CRNH notes in the window, so that cell is a census.
- **Pilot:** a disjoint pilot of 40 notes from 1–9 Nov was used only to develop prompts.
- **Weights:** population sizes for each cell are released for weighting.
- **Power:** 110 notes per CRH cell gives about 80% power to detect a difference of 25% vs 10% at α = .05.

### 3.3 Time-pinned source retrieval

Each cited URL is classified as an X post, other X page, non-text media (video or social), Wikipedia, or web page.

- **Wikipedia:** we retrieve the exact revision that was live when the note was written, using the MediaWiki API.
- **Web pages:** we retrieve the last Internet Archive snapshot before the note's creation time. Failing that, we use the first snapshot within 7 days after. Failing both, we fetch the live page and flag it as unpinned.
- **Text extraction:** main text with trafilatura, keeping the full visible text as a fallback; PDF text via pypdf. Archived payloads that are still compressed (zstd, gzip or brotli) are decompressed first.
- **Not retrieved:** X posts and non-text media. They count towards checkability, not towards support.

### 3.4 Claim decomposition

An LLM (`claude-haiku-5-5`, effort medium; prompt in Appendix B) splits each note into small, standalone claims, keeping numbers, names and quotes verbatim. Each claim is typed as number/date, attribution/quote, causal, characterisation, event, or about-the-post. Claims that only describe the post itself are out of scope, because they cannot be checked against outside sources.

### 3.5 Quote-anchored verdicts

For each note, a judge (`claude-haiku-5-5`, effort high) receives only the in-scope claims and the retrieved source texts.

We deliberately use a small, inexpensive model, run through Claude Code's headless mode with tools, plugins and settings disabled. The whole 804-note audit costs about $2 at API prices, so a platform or researcher could repeat it every month. Its accuracy is established empirically by the blind human audit (§3.6), not assumed. Prompts were developed on a disjoint 40-note pilot over three rounds and frozen before the main run (Appendix C). It never sees the note's author, group or status. For each claim it returns one of:

- `SUPPORTED`: a source states or directly entails the claim, including every specific detail;
- `PARTIAL`: the core is supported but a detail is missing or differs;
- `NOT_IN_SOURCE`: no source establishes it, even if it is true;
- `CONTRADICTED`: a source says something incompatible.

Every verdict except `NOT_IN_SOURCE` must quote the deciding passage verbatim. Code then checks the quote against the retrieved text, after normalising Unicode, quote marks, dashes and whitespace. Long quotes may differ in no more than 10% of six-word shingles. A verdict whose quote is not found is re-asked once, and otherwise coded `UNVERIFIED`. This makes every positive verdict auditable by string match. A secondary judge (`claude-sonnet-5-5`) scores the same claims [TBD if run].

### 3.6 Blind human validation

150 claims, stratified by judge label and group, were labelled by a human against the same source texts with the same rubric. The labelling page hides the group, status and the judge's verdict. We report Cohen's κ overall and separately for AI-written and human-written notes, which tests whether the judge's agreement differs by authorship. We also report weighted precision and recall of `UNSUPPORTED`.

### 3.7 Ratings linkage

From the ratings dump (12.5 M ratings on notes in the window) we compute, for each note, the share of ratings that use each source-related tag: "cites high-quality sources", "sources do not support note", "sources missing or unreliable", and "incorrect". Rater IDs are discarded.

### 3.8 Outcomes and analysis (pre-registered)

- **Primary outcome:** a note is **UNSUPPORTED** if at least one of its checkable claims is `NOT_IN_SOURCE` or `CONTRADICTED`. A claim is checkable if it is in scope and at least one of the note's sources was retrieved. `UNVERIFIED` verdicts are excluded here and counted as unsupported in a sensitivity analysis.
- **H1:** UNSUPPORTED differs between `cw` and `human` among CRH notes (two-sided permutation test).
- **H2a:** within groups, CRNH notes are more often UNSUPPORTED than CRH notes. The estimand is the population-weighted mean of the within-group differences, tested by permuting status within groups.
- **H2b:** the CRNH − CRH gap is smaller for `cw` than for `human` (interaction in a logistic regression).
- **H3:** the share of raters tagging "sources do not support note" detects UNSUPPORTED notes poorly (AUROC < 0.65; notes with at least 5 ratings).
- **Statistics:** CIs are 10,000-resample bootstraps within cells, and H1, H2a and H3 are Holm-corrected.
- **Sensitivity analyses:** `PARTIAL` or `UNVERIFIED` counted as unsupported; notes with every source retrieved; time-pinned sources only; excluding notes that cite Wikipedia; leaving out each `cw` account in turn; the second judge.

## 4. Results

### 4.1 Raters describe all writers' sources alike

Across the whole window (not only the sample), raters treat the three groups' sources almost identically (Table 1):

- On CRH notes, 54% of ratings tick "cites high-quality sources" for every group: 54.1% `cw`, 53.7% `ai_other`, 53.9% `human`.
- Among critical ratings (not helpful or somewhat helpful), 38–40% name a source problem.

So human raters do not visibly distinguish AI-sourced notes from human-sourced ones. Whether either kind is actually supported is the question of §4.3–4.5.

*Table 1 (`data/release/rater_tags_population.csv`): notes, median ratings and source-tag shares by group × status.*

### 4.2 How much of the evidence can be checked

Of the 1,548 URLs cited by sampled notes, 15% are X posts or pages and 5% are video or social media, so neither can be checked against text. Of the 1,240 fetchable URLs, we retrieved text for 91% and time-pinned text for 77% (Wayback before the note 790; Wikipedia revision 109; Wayback after 59; cited archive copies 3; live and unpinned 279).

At the note level (Table 2):

- **Any retrievable source:** 92% of `cw` notes have at least one, against 81% of `ai_other` notes and 61% of `human` notes.
- **Every cited source retrievable:** only **58%** of notes, falling to **49%** for `cw`. X's writer often pairs a web source with an X post or video.
- **Every cited source retrievable and pinned:** 44% of notes (`cw` 33%).

The evidence for a large share of live fact-checks cannot be independently bound to text, and evidence hosted on X is the least auditable from outside the platform.

*Table 2 (`data/release/retrieval_funnel.csv`): checkability funnel by group.*

### 4.3 Are notes supported by their own sources? (H1)

[TBD: Figure 3, UNSUPPORTED by group × status with 95% CIs; H1 estimate, CI and p. Repeat for the all-sources-retrieved subset.]

### 4.4 Does Helpful status track support? (H2)

[TBD: H2a within-group gap; H2b interaction.]

### 4.5 Do raters notice? (H3)

[TBD: AUROC of the "sources do not support note" tag share; secondary tags; CRH only.]

### 4.6 Judge validation

[TBD: κ overall and by authorship; confusion matrix; precision and recall of UNSUPPORTED; quote verification and re-ask rates.]

### 4.7 What unsupported claims look like

[TBD: claim-type mix of unsupported claims (numbers/dates, attributions, …), with two short examples.]

## 5. Discussion

[TBD after results. Points to cover:]

- **What the headline means for the claim that helpfulness tracks accuracy.** Goodhart-style concerns about writers optimised against rater approval.
- **Oversight.** What it means that raters' source tags are similar across writers, and how well they detect unsupported notes.
- **Recommendations:**
  - show raters the quoted evidence passage, so that checking is cheap;
  - require AI writers to bind each claim to a quoted passage;
  - add an independent evidence check that does not share a model family with the writer;
  - publish note-time archive links.
- **Checkability as infrastructure.** X-hosted evidence cannot be audited from outside, and 42% of notes cannot be fully bound to retrievable text.
- **A re-runnable audit.** The dump refreshes daily, so the audit can be repeated monthly and cannot go stale.

## 6. Conclusion

[TBD]

## References

- De, S., Slaughter, I., Guo, J., Cheng, Q.-Y., Yan, J., Banerjee, S., Saveski, M. (2026). How Human Feedback Shapes AI-generated Community Notes. arXiv:2606.30905.
- Gao, T., Yen, H., Yu, J., Chen, D. (2023). Enabling Large Language Models to Generate Text with Citations. EMNLP 2023.
- Gong, Y., Wu, S. (2026). Characterizing AI Fact-Checkers and Their Contributions on Community Notes. arXiv:2605.16566.
- Indicator (2026, Oct 16). Briefing: X handed fact-checking to the crowd. Then it became the crowd. indicator.media.
- Kangur, U., Chakraborty, R., Sharma, R. (2024). Who Checks the Checkers? Exploring Source Credibility in Twitter's Community Notes. arXiv:2406.12444.
- Miller, B., Baxter, J., Chao, J., Coleman, K., Hilgard, S., Ortiz, D. (2026). Community-Driven API and AI Writer Design for Openly Scaling Community Notes. arXiv:2609.40067.
- Min, S., Krishna, K., Lyu, X., Lewis, M., Yih, W., Koh, P. W., Iyyer, M., Zettlemoyer, L., Hajishirzi, H. (2023). FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation. EMNLP 2023.
- Rashkin, H., et al. (2023). Measuring Attribution in Natural Language Generation Models. Computational Linguistics 49(4), 777–840.
- Solovev, K., Pröllochs, N. (2025). References to unbiased sources increase the helpfulness of community fact-checks. arXiv:2503.10560.
- Wu, K., et al. (2025). An automated framework for assessing how well LLMs cite relevant medical references. Nature Communications 16, 3615.
- xai-org/community-writer (2026). GitHub repository, Apache-2.0.

*(Before submitting, check the author lists of Gao et al. and Min et al. against the papers.)*

## Appendix A. Limitations and Dual-Use / Ethical Considerations

**Limitations.**

- **Observational design.** We measure association, not why notes are unsupported.
- **Judge error.** The judge is an LLM. Quote verification removes hallucinated support but not mistaken "not in source" verdicts. The human audit estimates both error types (§4.6).
- **Missing sources.** A claim may be supported by a source we could not retrieve, such as an X post or video. Hence the all-sources-retrieved analysis.
- **Time pinning.** Snapshots after the note was written (59 of them) and live copies (279) may differ from what the writer saw.
- **Deleted notes** are invisible in the public data, and X's writer deletes drafts predicted to fail.
- **Account mapping.** The `cw` label rests on volume patterns and a manual check.
- **Statuses change** over time.
- **One platform, one window.** The findings may not transfer elsewhere.
- **The judge comes from a different model family** from the writer (Claude judging Grok-written notes). That is deliberate, since it avoids a model checking its own work. Any family-specific bias is tested by κ split by authorship.

**Dual use and ethics.**

- **Data.** All data is public. Participant IDs are pseudonymous. We report no statistics for individual human writers and do not re-host note text; we release IDs, labels and code. The AI accounts belong to an organisation and are publicly documented.
- **Gaming.** A catalogue of "unsupported but rated Helpful" notes could help someone write notes that pass raters without support. We report categories, not templates.
- **Misuse of the findings.** Results could be used to discredit crowd fact-checking as a whole. We report the human baseline alongside the AI groups, and frame the work as an audit for improvement. We will share the findings with the Community Notes team.

## Appendix B. Prompts

[Insert `prompts/decompose.md` and `prompts/judge.md`, with their SHA-256 hashes.]

## Appendix C. Pre-registration deviations

[Copy the dated list from `PREREGISTRATION.md` §8.]
