# Do AI Fact-Checks Say What Their Sources Say? An Independent Evidence Audit of AI-Written Community Notes

**Raj Gupta** · [affiliation] · AI x Epistemics Research Sprint (Apart Research), 13–16 Nov 2026
Code and data: https://github.com/rajkumar0932/Evidence-Audit-of-AI-Written-Community-Notes

## Abstract

AI accounts wrote 61% of the Community Notes on X that reached "Helpful" status in Aug–Oct 2026, mostly six X-run accounts. Published evaluations of these notes, X's own included, measure rater approval; none checks whether a note's cited sources support what it says.

We audit a pre-registered, stratified sample of 804 notes by X's Community Writer, other AI writers and humans, across all three rating statuses. We pin each source to its version at the time of writing and split notes into 3,545 claims. Every "supported" verdict must quote a passage that code verifies; 99% did. An independent judge from another model family agrees on 88% of claims (Cohen's kappa 0.75), and a blind human spot-check confirms 91% of the judge's "unsupported" verdicts.

The platform's signals do not track evidence:

- Raters' "sources do not support note" tag detects unsupported notes no better than chance (AUROC 0.53, 95% CI 0.48–0.58).
- Helpful notes are unsupported about as often as Not Helpful ones (gap 3.8 points, CI −6 to +14).

AI notes are better grounded than human notes: on Helpful notes, 47% of claims by X's writer and 51% by other AI writers are supported by their own sources, against 26% for humans. Yet most notes from every writer contain at least one claim their sources do not establish.

Only 58% of notes could be fully bound to retrievable evidence. The audit costs about $4 of model usage and can be rerun on every public data release.

## 1. Introduction

Community Notes is the largest crowd fact-checking system in use today. A note is shown under a post on X only when raters who usually disagree with each other both rate it helpful. Since September 2025, X has also accepted notes written by AI. In our window (notes created 14 August to 31 October 2026), AI accounts wrote 61% of the notes that reached Helpful status (14,156 of 23,136). Most came from six accounts with near-identical quotas, which match the six accounts that X's open-source Community Writer [1] lists as its own.

**The problem.** Nobody has checked whether these AI fact-checks are backed by their own evidence. Every published evaluation, including one by the engineers who built X's writer, measures whether raters liked the notes [2–4]. None asks whether the cited pages actually say what the notes claim.

**Why it matters.** A fact-check is only as good as its evidence, and these notes reach millions of people. There is also a specific failure mode. The AI writers are tuned to win rater approval, so if ratings ignore evidence, unsupported notes can spread while every platform metric looks healthy. Community Notes is a working example of scalable oversight: AI writes, humans rate, and an algorithm decides what is shown. Whether that human layer checks evidence is a safety question.

**Our main contributions are:**

1. **An evidence audit.** The first claim-level, time-pinned audit of the evidence behind AI-written Community Notes, compared with human notes. It covers 804 notes and 3,545 claims, was pre-registered, and backs every positive verdict with a quote verified in the source.
2. **Platform signals do not track evidence.** Raters' "sources do not support note" tag detects unsupported notes no better than chance (AUROC 0.53), and Helpful status barely tracks support.
3. **AI notes are better sourced, but not well sourced.** AI-written notes are better grounded than human ones, yet most notes from every writer contain an unsupported claim. Only 58% can be fully checked at all. The audit costs about $4 to rerun.

## 2. Related Work

The closest work evaluates AI note writers through platform outcomes:

- Gong and Wu [3] find AI writers' Helpful rates fall between those of expert and lay humans.
- De et al. [2] study human feedback on AI-drafted notes.
- Miller et al. [4], who built X's writer, describe its Grok-based writers and helpfulness filters. They leave open "whether helpfulness ratings track factual accuracy and source quality".

Other work rates the *outlets* notes cite rather than the specific page and claim:

- Cited outlets lean towards high-factuality sources [5].
- Linking a source makes a helpful rating 2.7 times more likely [6].

Methods for checking text against its citations exist (AIS [7], ALCE [8], FActScore [9], SourceCheckup [10], which found 50–90% of LLM medical answers not fully supported). They have been applied to model outputs offline, not to a live system governed by human raters.

**(a) When would someone use our method?** To check, from public data alone, whether a deployed fact-checking or citation system is backed by its own evidence, independently of the platform's metrics. Evidence is pinned to the time of writing, and every positive verdict can be checked by string matching.

**(b) What new insight does it give?** A live crowd-rating system does not reward evidence, and AI writers beat humans on grounding.

## 3. Methods

**Data and sample.** We used X's public Community Notes data of 12 November 2026 [11], covering the 286,940 notes created between 14 August and 31 October 2026. We labelled the six highest-volume accounts enrolled through the AI Note Writer API as X's Community Writer (`cw`), the remaining API accounts as other AI, and everyone else as human. From each group we drew a seeded random sample of 110 Helpful, 78 Not Helpful and 80 Needs-More-Ratings notes, 804 notes in all. That gives about 80% power for a 15-point difference. Collaborative and deleted notes were excluded.

**Pipeline and design choices.**

- **Time-pinned evidence.** Each cited source was retrieved as it looked when the note was written: the Wikipedia revision from that moment, or the last Internet Archive snapshot before it, with live pages as a flagged fallback. Pages change, and judging a note against a later version would be unfair.
- **Claims.** An LLM split each note into standalone claims, keeping numbers, qualifiers and the original language, as in FActScore [9].
- **Blind, quote-anchored verdicts.** A judge model saw only the claims and the source texts, never the author or rating. It labelled each claim *supported*, *partly supported*, *not in source* or *contradicted*, and had to quote the deciding passage word for word. Our code confirmed each quote appears in the source; a failed quote was re-asked once, then marked unverified. Blinding prevents bias towards one kind of writer, and the quote check stops the judge inventing support.
- **A deliberately small judge.** We used Claude Haiku 5.5, run through Claude Code's headless mode with tools off, so a full run costs about $4 and could be repeated monthly. Its verdicts were checked against Gemini 3.5 Flash-Lite (another company's model), against Claude Opus 5.5 (a much stronger model), and by a blind human spot-check.

**Analysis.** A note is *unsupported* if any of its checkable claims is not in the source or is contradicted. We pre-registered three hypotheses:

- **H1:** X's writer and humans differ among Helpful notes.
- **H2:** Not-Helpful notes are unsupported more often than Helpful ones.
- **H3:** raters' "sources do not support note" tag detects unsupported notes poorly (AUROC below 0.65), using 12.5 million public ratings.

We report bootstrap confidence intervals and permutation tests, with Holm correction across the three hypotheses.

**What did not work.**

- **Our first prompts.** The judge counted the parody post a note was debunking as contradicting the note, and claims lost qualifiers such as "not officially announced". Three pilot rounds on 40 separate notes fixed both.
- **Source retrieval.** It stalled on slow archive lookups and on a page that trickled data for 1.8 hours, until we added hard time limits.
- **Models.** A paid API was beyond our budget, so we used Claude Code's headless mode. The free Gemini Flash quota of 20 requests a day was too small, so we used Flash-Lite.
- **Human validation.** The pre-registered 90-claim human validation could not be finished in time. All changes are dated in Appendix C.

**Reproducibility.** The pre-registration was committed before any evidence was collected. All code, the frozen prompts (Appendix B), the sample and every verdict are public, and `verify.py` recomputes each headline number.

## 4. Results

The pipeline judged 621 of the 804 notes. The other 183 had no retrievable source (164) or no checkable claim (19). The 2,643 claim verdicts break down as follows:

| Verdict | Claims |
|---|---|
| Supported | 1,122 |
| Partly supported | 561 |
| Not in source | 871 |
| Contradicted | 72 |
| Unverified | 17 |

99% of the judge's quotes were found word for word in the source.

### 4.1 How much of the evidence can be checked?

Of 1,548 cited links, 15% point to X posts and 5% to video or social media; neither can be checked as text. 92% of notes by X's writer, but only 61% of human notes, cite at least one checkable source (Figure 1). Only 58% of all notes have *every* source retrievable, and 44% have every source retrieved and pinned to the time of writing. Much of the evidence behind live fact-checks cannot be audited from outside X.

![](figures/fig_checkability.png){width=52%}

*Figure 1. Share of sampled notes whose cited evidence can be retrieved as text (left), retrieved in full (middle), and retrieved in full and pinned to the time of writing (right), by writer.*

### 4.2 Are notes supported by their own sources? (H1)

**Observation.** Most notes from every writer contain at least one claim their own sources do not establish: 56–81% of checkable notes (Figure 2). Among Helpful notes, human-written notes were unsupported more often than AI-written ones. The difference is clearest at claim level, where about half of AI writers' claims were fully supported, against a quarter of humans' (Table 1).

| Writer | Helpful notes with an unsupported claim | Claims fully supported |
|---|---|---|
| X's Community Writer | 64.6% (CI 54.5–73.7) | 47.1% (CI 40.5–53.7) |
| Other AI writers | 56.0% (CI 46.2–65.9) | 51.3% |
| Human writers | 74.6% (CI 63.5–85.7) | 25.8% (CI 17.7–34.5) |

*Table 1. Helpful notes containing at least one claim their sources do not support, and the share of claims fully supported, by writer.*

**Interpretation.** AI notes are better sourced than human ones, most likely because X's writer is built to open and confirm every link before posting.

**Is it significant?** At note level, not on its own: X's writer is 10.0 points below humans (CI −24.1 to +4.3, p = .22, Holm p = .44). The claim-level confidence intervals, however, do not overlap.

**Is it robust?** The direction holds in every check we ran:

- **Notes whose sources were all retrieved:** a 19.2-point gap (CI −37.2 to −0.5, p = .06).
- **Each pre-registered sensitivity analysis:** gaps of 3–13 points.
- **Dropping any one of X's six accounts:** its rate stays at 63–67%.
- **With Gemini as the judge:** an 8.8-point gap.

![](figures/fig_unsupported.png){width=52%}

*Figure 2. Share of checkable notes with at least one claim that the note's own sources do not support, by writer and rating status, with 95% bootstrap confidence intervals.*

### 4.3 Does Helpful status track evidence? (H2)

Within each group, notes rated Not Helpful were unsupported only 3.8 points more often than Helpful ones (CI −6.2 to +13.8, p = .23). The gap was the same for X's writer and for humans. Helpful status, which every earlier evaluation relies on, says almost nothing about whether a note is backed by its sources.

### 4.4 Do raters notice unsupported notes? (H3)

For notes with at least five ratings (n = 567), the share of raters tagging "sources do not support note" separated unsupported from supported notes no better than chance: AUROC 0.53 (CI 0.48–0.58). That is well below the pre-registered 0.65 (Holm p = .0015).

The other source tags scored 0.48–0.54, and the pattern held for every writer (Figure 3). Raters ticked "cites high-quality sources" on 54% of ratings of Helpful notes, for AI and human notes alike. We read this as raters judging how sources look, not what they say.

![](figures/fig_roc.png){width=37%}

*Figure 3. ROC curves for the share of raters tagging "sources do not support note" as a predictor of verified unsupported notes, by writer. The diagonal is chance.*

### 4.5 Can the judge be trusted?

| Check | Result |
|---|---|
| Gemini (another company), 1,024 claims | 88% agreement, κ 0.75 (AI-written 0.76, human 0.67) |
| Claude Opus (stronger model), 355 claims | 89% agreement, κ 0.74; precision 0.87, recall 0.88 |
| Human spot-check (one author), 29 claims | 69% agreement, κ 0.40; 12 of 13 "unsupported" confirmed |

*Table 2. Agreement between the primary judge (Claude Haiku) and three independent checks.*

The conclusions hold under each judge; under Gemini the H3 AUROC is also 0.53. Only the *level* of unsupported notes varies: Opus is more lenient (58% vs 70%), while Gemini (76% vs 64%) and the human labeller are stricter, so absolute rates are best read as a range. Appendices D and E give details and the kinds of claims that go unsupported.

## 5. Discussion and Limitations

**Implications for AI safety.** We see a quiet failure of human oversight in a real deployment. The people meant to check AI-written content cannot tell supported notes from unsupported ones, yet every metric the platform tracks looks healthy. AI writers trained to win those ratings have no reason to cite better evidence; the ones we studied are better sourced only because that was designed into X's writer.

Four fixes follow: show raters the passage that supports each claim; require writers to attach a quote to each claim (we could check 99% of them automatically); check evidence with a model from a different family from the writer; and archive every cited page when the note is written.

### Limitations

Our results rest on four assumptions:

1. **The judge's labels are close to correct.** Three checks support this, but human agreement was only moderate (κ 0.40, 29 claims). If the judge erred mainly towards "unsupported", absolute rates would fall. The AI-versus-human and rater findings repeat under every judge, so they would not.
2. **Retrieved pages show what the writer saw.** 279 sources are live copies that may have changed; using archived sources only gives the same direction.
3. **Sources we could not open would not change the picture.** X posts and videos may support some claims, but restricting to fully retrieved notes widens the AI–human gap.
4. **The six high-volume accounts are X's writer.** If not, the comparison becomes "high-volume AI writers versus humans", and the findings still hold for AI notes.

Appendix A covers further limitations: one platform, an 11-week window, and a strict note-level outcome.

### Future Work

Next: full human validation of the released 90-claim set, a test of showing raters quoted evidence, and extending the audit to Meta's and TikTok's crowd notes.

## 6. Conclusion

AI now writes most of the fact-checks that X shows its users. Judged against their own sources, these notes hold up better than human-written ones. But most notes from every writer contain a claim their sources do not support, and the human rating system cannot tell the difference. Evaluations that stop at "rated helpful" miss what matters most in a fact-check. Checking evidence costs about $4 for 800 notes and should be done routinely.

## Code and Data

- **Code repository:** https://github.com/rajkumar0932/Evidence-Audit-of-AI-Written-Community-Notes
- **Data/Datasets:** X's public Community Notes data, 12 November 2026 release [11]. Our verdicts, labels, pre-registration, prompts and `verify.py` are in the repository.

## References

1. xai-org (2026). community-writer: the Community Writer for Community Notes. GitHub repository, Apache-2.0. https://github.com/xai-org/community-writer
2. De, S., Slaughter, I., Guo, J., Cheng, Q.-Y., Yan, J., Banerjee, S., Saveski, M. (2026). How Human Feedback Shapes AI-generated Community Notes. arXiv:2606.30905. https://arxiv.org/abs/2606.30905
3. Gong, Y., Wu, S. (2026). Characterizing AI Fact-Checkers and Their Contributions on Community Notes. arXiv:2605.16566. https://arxiv.org/abs/2605.16566
4. Miller, B., Baxter, J., Chao, J., Coleman, K., Hilgard, S., Ortiz, D. (2026). Community-Driven API and AI Writer Design for Openly Scaling Community Notes. arXiv:2609.40067. https://arxiv.org/abs/2609.40067
5. Kangur, U., Chakraborty, R., Sharma, R. (2024). Who Checks the Checkers? Exploring Source Credibility in Twitter's Community Notes. arXiv:2406.12444. https://arxiv.org/abs/2406.12444
6. Solovev, K., Pröllochs, N. (2025). References to unbiased sources increase the helpfulness of community fact-checks. arXiv:2503.10560. https://arxiv.org/abs/2503.10560
7. Rashkin, H., Nikolaev, V., Lamm, M., Aroyo, L., Collins, M., Das, D., Petrov, S., Tomar, G. S., Turc, I., Reitter, D. (2023). Measuring Attribution in Natural Language Generation Models. Computational Linguistics 49(4), 777–840. https://arxiv.org/abs/2112.12870
8. Gao, T., Yen, H., Yu, J., Chen, D. (2023). Enabling Large Language Models to Generate Text with Citations. EMNLP 2023. https://arxiv.org/abs/2305.14627
9. Min, S., Krishna, K., Lyu, X., Lewis, M., Yih, W., Koh, P. W., Iyyer, M., Zettlemoyer, L., Hajishirzi, H. (2023). FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation. EMNLP 2023. https://arxiv.org/abs/2305.14251
10. Wu, K., et al. (2025). An automated framework for assessing how well LLMs cite relevant medical references. Nature Communications 16, 3615. https://doi.org/10.1038/s41467-025-58551-6
11. X Community Notes (2026). Downloading data: public notes, ratings, status history and enrollment files. https://github.com/twitter/communitynotes/blob/main/documentation/under-the-hood/download-data.md

## Appendix A. Limitations and Dual-Use / Ethical Considerations

**Limitations.**

- **Observational design.** We measure association, not why notes are unsupported.
- **Limited human validation.** The pre-registered 90-claim blind human validation could not be completed. It was replaced by agreement with a cross-family judge and a stronger reference model, which cannot rule out errors that models share, and by a single-author spot-check of 30 claims (29 decided).
  - The spot-check shows moderate agreement (κ 0.40) and high precision of the judge's "unsupported" (0.91).
  - Its labels may be noisy: they were made quickly, by one person, from a key-word view. Quote verification removes hallucinated support but not mistaken "not in source" verdicts. Human labelling of the released 90-claim validation set is the most important next step.
- **Missing sources.** A claim may be supported by a source we could not retrieve (an X post, a video). Hence the all-sources-retrieved analysis, in which the AI–human gap widens.
- **Time pinning.** 59 sources come from snapshots after the note was written and 279 are live copies; these may differ from what the writer saw.
- **Deleted notes** are invisible in the public data, and X's writer deletes drafts predicted to fail.
- **Account mapping.** The `cw` label rests on volume patterns that match X's published account list.
- **Strict outcome.** The note-level outcome counts a single unsupported claim; claim-level rates are reported alongside.
- **Scope.** Statuses change over time, and the study covers one platform in one 11-week window.
- **Model families.** The judges come from model families other than the writer's (Claude and Gemini judging Grok-written notes). That is deliberate, since it avoids a model checking its own work. Authorship-specific bias is tested by κ split by authorship.

**Dual use and ethics.**

- **Data.** All data is public. Participant IDs are pseudonymous. We report no statistics for individual human writers and do not re-host note text; we release IDs, verdicts, labels and code. The AI accounts belong to an organisation and are publicly documented.
- **Gaming.** A catalogue of "unsupported but rated Helpful" notes could help someone write notes that pass raters without support. We report categories, not templates.
- **Misuse of the findings.** Results could be used to discredit crowd fact-checking as a whole. We report the human baseline alongside the AI groups, and the main recommendations strengthen the system rather than replace it. We will share the findings with the Community Notes team.

## Appendix B. Prompts

The frozen prompts are `prompts/decompose.md` (SHA-256 `24c9df9a…`) and `prompts/judge.md` (SHA-256 `08d3b5a2…`) in the repository.

## Appendix C. Pre-registration timeline and deviations

| When (IST) | Event |
|---|---|
| 13 Nov, 23:57 | Stage 1 committed: question, data, sample, outcomes, hypotheses, analysis plan |
| 14 Nov, before any judging | Added the all-sources-retrieved sensitivity analysis; specified how `UNVERIFIED` verdicts count; defined H2a as a within-group gap (a synthetic dry run showed the pooled version confounded) |
| 15 Nov, 21:48 | Stage 2 committed before the main run: prompts frozen after three pilot rounds; switch from `claude-opus-5-5` to `claude-haiku-5-5` via Claude Code headless mode, for cost reasons |
| 15 Nov, 22:35 | Human validation reduced from 150 to 90 claims (time), before any label was collected |
| 15 Nov, ~22:55 | Human validation not completed; replaced by a cross-family judge (Gemini) and a stronger reference judge (Claude Opus 5.5), after the primary run (§3.5) |
| 16 Nov, ~09:00 | Quick blind human spot-check of 30 claims (binary question) registered before any label; two labelling passes, 29 decided labels in the second (§4.5) |

All entries are in the repository's git history.

## Appendix D. Judge validation details

**Cross-family agreement.** On 1,024 claims scored by both the primary judge (Claude Haiku 5.5) and Gemini 3.5 Flash-Lite:

| Comparison | Agreement | Cohen's κ |
|---|---|---|
| Supported vs unsupported | 87.9% | 0.75 |
| All four labels | 75.6% | 0.61 |
| Note-level UNSUPPORTED (251 notes) | 86.9% | 0.69 |

- **No authorship bias:** agreement is similar for AI-written notes (κ 0.76, supported vs unsupported) and human-written notes (κ 0.67).
- **Where they disagree:** mostly the `PARTIAL`/`SUPPORTED` boundary (112 claims the primary judge called `PARTIAL` were `SUPPORTED` for Gemini) and `PARTIAL`/`NOT_IN_SOURCE` (79).
- **Gemini is stricter, not more lenient.** It marks 76% of notes unsupported, against the primary judge's 64%. The high unsupported rates are not an artefact of the primary judge.

**Findings under each judge.** Recomputed with Gemini's verdicts, the conclusions are unchanged:

- **H1:** X's writer is 8.8 points below humans among Helpful notes (CI −21.4 to +4.0), against 10.0 points with the primary judge.
- **H3:** the rater-tag AUROC is 0.53 under both judges.

**Stronger reference.** Claude Opus 5.5 re-judged 60 of the 86 validation notes before a usage limit stopped it, covering 79 of the 90 stratified validation claims and 355 claims in all.

| Comparison with Opus | Result |
|---|---|
| Supported vs unsupported, all 355 shared claims | 88.7% agreement, κ = 0.74 |
| Same, AI-written notes | κ = 0.77 |
| Same, human-written notes | κ = 0.63 |
| Primary judge's "unsupported" on the 79 validation claims (weighted) | precision 0.87, recall 0.88 |

By label, the reference confirms:

- **almost every `SUPPORTED`** (100% of validation claims) **and `NOT_IN_SOURCE`** (89%);
- **few `CONTRADICTED` verdicts.** It mostly downgrades them to `PARTIAL` or `NOT_IN_SOURCE`. The rare contradicted label should be read as "not supported", not as a confirmed contradiction.

**The *level* of unsupported notes depends on the judge; the comparisons do not.**

- On the 76 notes it shares with the primary judge, Opus marks 58% unsupported, against the primary judge's 70%.
- On its 251 notes, Gemini marks 76%, against the primary judge's 64%.

The absolute rates in §4.2 should therefore be read as a range across judges. The AI–human gap (§4.2) and the null rater signal (§4.4) hold under both judges that scored the full Helpful sample (Claude Haiku and Gemini).

**Human spot-check.** One author blindly labelled 30 of the validation claims (10 per group) with a single question: does the source support at least the main point? To save time, the labelling view showed the passages around the claim's key words by default, with the full text one click away.

- **Two passes.** A first pass decided 7 claims. A second pass, using the full text, decided 29 (9 supported, 20 not supported, 1 can't tell). The 7 first-pass labels were unchanged.
- **Agreement on the 29 decided claims:**

| Judge | Agreement with the author | κ | Weighted precision of "unsupported" | Weighted recall |
|---|---|---|---|---|
| Primary (Claude Haiku) | 69% | 0.40 | **0.91** | 0.63 |
| Claude Opus | 63% | 0.32 | 0.90 | 0.59 |
| Gemini (14 claims) | 64% | 0.31 | 0.81 | 0.74 |

- **Where they disagree.** The author was stricter than every judge: 69% of claims not supported. When the primary judge said "unsupported", the author agreed in 12 of 13 cases. 8 of the 9 disagreements are claims the judge called `SUPPORTED` or `PARTIAL` and the author did not.
- **All 8 of those judge quotes are verified verbatim in the source, and 7 of the 8 were visible in the default labelling view.** These disagreements therefore reflect a stricter standard on the author's part, labelling error, or judge leniency. A check this small cannot separate those explanations.

The spot-check gives no sign that the judge over-flags unsupported claims. Relative to this labeller, judge-based unsupported rates are conservative. With 29 claims and one labeller, it is not a substitute for full validation.

## Appendix E. What unsupported claims look like

Characterisations are the largest share of unsupported claims for X's writer (43%) and humans (41%), followed by event claims (Figure 4). Typical characterisations are "the images are AI-generated" or "the account is a parody". Other AI writers' unsupported claims are more often specific numbers and dates (23%).

The pilot showed two recurring patterns:

- **Unsourced labels.** A note asserts a label (fabricated, AI-generated) and cites a page that only shows where the content came from.
- **Over-specified details.** A note states a precise figure, date or causal detail (for example an "uncontrolled" dive) that its source gives only partly.

![Figure 4](figures/fig_claim_types.png)
*Figure 4. Claim types among each group's unsupported claims.*

## Appendix F. Method details

**Sample.** 110 notes per Helpful cell gives about 80% power to detect a 25% vs 10% difference at α = .05. In the window, 41 accounts were enrolled as AI writers, 28 of them active. Notes with no status row are 12.7% of every creation week, consistent with deleted notes rather than publication lag.

**Retrieval.** Wikipedia revisions come from the MediaWiki API. Web pages come from Internet Archive snapshots found through the availability API and time-bounded CDX queries. Main text is extracted with trafilatura, keeping the full visible text as a fallback; PDF text uses pypdf. Archived payloads still compressed with zstd, gzip or brotli are decompressed first.

Of 1,240 fetchable URLs, we retrieved text for 91% and time-pinned text for 77%:

| Retrieval route | URLs |
|---|---|
| Archive snapshot before the note | 790 |
| Wikipedia revision at writing time | 109 |
| Archive snapshot after the note | 59 |
| Archived copy cited by the note itself | 3 |
| Live page, not time-pinned | 279 |

**Claims.** Claims are typed as number/date, attribution/quote, causal, characterisation, event, or about-the-post (out of scope; 9.9% of the 3,545 claims).

**Quote verification.** Quotes are matched after normalising Unicode, quote marks, dashes and whitespace. A quote of 8 or more words may differ in at most 10% of its six-word shingles.

**Models and cost.**

- **Primary model:** `claude-haiku-5-5`, run through Claude Code's headless mode (`claude -p`) with tools, MCP servers, skills and settings disabled, from an empty working directory.
- **Effort:** medium for claim splitting, high for verdicts.
- **Cost:** about $4.20 at API prices (claims $0.73, verdicts $3.50).
- **Other judges:** the second judge is `gemini-3.5-flash-lite` on the free tier; the reference judge is `claude-opus-5-5`.

**Pilot.** Three prompt rounds on 40 disjoint notes fixed two failure modes:

1. A source that merely repeats the claim being corrected (for example, a parody post) was counted as contradicting the note.
2. Qualifiers such as "not officially announced" were dropped, and one claim was mistranslated.

The `CONTRADICTED` label fell from 6 to 2 of the pilot's verdicts, and every pilot quote was verified.

**Statistics.**

- **H2a** is the weighted average of within-group gaps (weights: each group's CRH + CRNH population), tested by permuting status within groups.
- **H2b** is the status × group interaction in a logistic regression that controls for the number of URLs and the log of note length.
- **Sensitivity analyses:**
  - `PARTIAL` counted as unsupported;
  - `UNVERIFIED` counted as unsupported;
  - notes with all sources retrieved;
  - time-pinned sources only;
  - excluding notes that cite Wikipedia;
  - leaving out each `cw` account in turn.

## LLM Usage Statement

This project was carried out with extensive help from Claude (Anthropic), used through Claude Code. Claude helped choose and scope the research question, wrote most of the data-processing, retrieval, judging and analysis code, ran the pipeline, and drafted large parts of this report. The authors directed the work, chose among the options proposed, carried out the human spot-check, and reviewed and edited the final report.

Language models are also part of the method itself (Section 3): Claude Haiku 5.5 is the primary judge, Claude Opus 5.5 the reference judge, and Gemini 3.5 Flash-Lite the second judge. All numbers in the report are produced by the released code from public data and can be recomputed with `verify.py`. References were checked against their sources.
