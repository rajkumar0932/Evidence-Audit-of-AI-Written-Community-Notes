# Do AI Fact-Checks Say What Their Sources Say? An Independent Evidence Audit of AI-Written Community Notes

**Raj Gupta** · [affiliation] · AI x Epistemics Research Sprint (Apart Research), 13–16 Nov 2026
Code and data: https://github.com/rajkumar0932/Evidence-Audit-of-AI-Written-Community-Notes

## Abstract

AI accounts wrote 61% of the Community Notes on X that reached "Helpful" status in Aug–Oct 2026, mostly six accounts that appear to be run by X. Published evaluations of these notes measure rater approval; to our knowledge none checks whether a note's cited sources support what it says.

We audit a pre-registered, stratified sample of 804 notes by X's Community Writer, other AI writers and humans. We pin each source to its version at the time of writing, split notes into claims, and require every "supported" verdict to quote a passage that code verifies. A judge from another model family agrees with ours on 76% of claims across four labels (Cohen's kappa 0.61; 88% for supported vs unsupported), and a 29-claim human spot-check agrees on 69% (kappa 0.40).

Rater signals do not track evidence. Raters' "sources do not support note" tag separates unsupported from supported notes no better than chance (AUROC 0.53, 95% CI 0.48–0.58), although a second judge predicts the same labels well (AUROC 0.90). We could not detect a difference in support between Helpful and Not Helpful notes (gap 3.8 points; gaps up to 14 points not ruled out).

In an exploratory claim-level analysis, claims in AI-written notes were supported by their own sources more often than claims in human notes (47–51% vs 26% on Helpful notes); the pre-registered note-level comparison was not significant. "Unsupported" means not established by the cited source, not false. Only about half of notes could be fully bound to retrievable evidence.

## 1. Introduction

Community Notes is the largest crowd fact-checking system in use today. A note is shown under a post on X only when raters who usually disagree with each other both rate it helpful. Since September 2025, X has also accepted notes written by AI. In our window (notes created 14 August to 31 October 2026), AI accounts wrote 61% of the notes that reached Helpful status (14,156 of 23,136). Most came from six accounts with near-identical quotas. From this volume pattern we infer that they are the six accounts X's open-source Community Writer [1] says it runs; the account mapping is not published.

**The problem.** To our knowledge, nobody has checked whether these AI fact-checks are backed by their own evidence. Published evaluations, including one by the engineers who built X's writer, measure whether raters liked the notes [2–4], and so do field studies comparing AI and human notes on the same posts [12, 13]. None asks whether the cited pages actually say what the notes claim.

**Why it matters.** A fact-check is only as good as its evidence, and these notes reach millions of people. The AI writers are tuned to win rater approval, so if ratings ignore evidence, unsupported notes can spread while every platform metric looks healthy. Community Notes is a working example of scalable oversight: AI writes, humans rate, and an algorithm decides what is shown. Whether that human layer checks evidence is a safety question.

**Our main contributions are:**

1. **An evidence audit.** To our knowledge, the first claim-level, time-pinned audit of the evidence behind AI-written Community Notes, compared with human notes. It covers 804 notes, was pre-registered, and backs every positive verdict with a quote verified in the source.
2. **Rater signals do not track evidence.** Raters' "sources do not support note" tag detects unsupported notes no better than chance (AUROC 0.53), although an independent judge predicts the same labels well (AUROC 0.90).
3. **AI notes are better supported at claim level.** In an exploratory analysis, claims in AI-written notes were supported by their own sources about twice as often as human notes' claims. The pre-registered note-level comparison was not significant. Only about half of notes can be fully checked at all.

## 2. Related Work

Gong and Wu [3] find AI writers' Helpful rates fall between those of expert and lay humans. De et al. [2] study human feedback on AI-drafted notes. Miller et al. [4], who built X's writer, evaluate it by rating outcomes rather than by checking accuracy or sources. Li et al. [12] proposed the design in which AI writes and humans rate, and Li and Bakker [13] compared a live LLM writer with human notes on the same posts, again through ratings.

Work on sources rates the *outlets* notes cite, not whether a specific page supports a specific claim: cited outlets lean towards high-factuality sources [5], and linking a source makes a helpful rating 2.7 times more likely [6]. On accuracy, a JAMA letter rated 97% of 205 COVID-19 vaccine notes accurate [15], while reporting by the Tow Center found inaccurate AI-written notes [16]. We measure something different from accuracy: whether the cited source establishes the claim.

Methods for checking text against its citations include AIS [7], ALCE [8], FActScore [9] and SourceCheckup [10]. The closest design to ours is Liu, Zhang and Liang's audit of generative search engines [14], where only 51.5% of sentences were fully supported by their citations, a benchmark for our claim-level rates. Such methods have been applied to model outputs offline, not to a live system governed by human raters.

**When to use this method, and what it adds.** It checks, from public data alone and independently of the platform's metrics, whether a deployed fact-checking or citation system is backed by its own evidence, with every positive verdict checkable by string matching. It provides the first evidence on whether a live crowd-rating system's source signals track evidence support, and the first comparison of AI and human writers on that measure.

## 3. Methods

**Data and sample.** We used X's public Community Notes data of 12 November 2026 [11], covering the 286,940 notes created between 14 August and 31 October 2026. X's writer (`cw`) is the six highest-volume accounts enrolled through the AI Note Writer API, other AI is the remaining API accounts, and human is everyone else; some "human" accounts may paste AI-written text. From each group we drew a seeded random sample of 110 Currently Rated Helpful (CRH), 78 Currently Rated Not Helpful (CRNH) and 80 Needs More Ratings (NMR) notes, 804 notes in all. 78 is every CRNH note from X's writer, and 110 balances cost and precision. Collaborative and deleted notes were excluded.

**Pipeline and design choices.**

- **Time-pinned evidence.** Each source was retrieved as it looked when the note was written: the Wikipedia revision from that moment, or the last Internet Archive snapshot before it. Failing that, we used a snapshot up to 7 days after, then the live page, flagged.
- **Claims.** An LLM split each note into standalone claims, keeping numbers, qualifiers and language, as in FActScore [9].
- **Blind, quote-anchored verdicts.** A judge model saw only the claims and the source texts, never the author or rating. It labelled each claim *supported*; *partly supported* (the core is there but a detail such as a number, date or scope is missing or differs); *not in source*; or *contradicted*. Every verdict except *not in source* had to quote the deciding passage word for word. Our code confirmed each quote appears in the source; a failed quote was re-asked once, then marked unverified.

  For example, "Similar videos showing a toddler running across a parade ground to hug a soldier score over 99% on AI detection tools" was judged *partly supported*: its source says only that "a detection tool flagged the video with a 99.7% probability".
- **A deliberately small judge.** We used Claude Haiku 5.5, run through Claude Code's headless mode with tools off. One run costs about $4 at API prices, excluding validation runs. It was checked against Gemini 3.5 Flash-Lite (another company's model), against Claude Opus 5.5 (a much stronger model), and by a blind human spot-check.

**Analysis.** A note is *unsupported* if any of its checkable claims is *not in source* or *contradicted*. The pre-registered hypotheses are:

- **H1:** X's writer and humans differ among CRH notes.
- **H2:** CRNH notes are unsupported more often than CRH notes, within groups.
- **H3:** raters' "sources do not support note" tag, from 12.5 million public ratings, detects unsupported notes poorly (AUROC below 0.65).

Claim-level support was a pre-registered secondary outcome, but its test was not pre-registered, so we report it as exploratory. Bootstraps resample *notes*, not claims; p-values come from permutation tests, Holm-corrected across H1–H3.

**Deviations and what did not work.** We switched the judge from Claude Opus 5.5 to Claude Haiku 5.5 because we had no API budget. The pre-registered 90-claim human validation could not be finished, so we replaced it with the two model judges and a 30-claim spot-check. Our first prompts treated a post being debunked as evidence against the note and dropped qualifiers; three pilot rounds on 40 separate notes fixed this. Appendix C dates every change and Appendix F gives method details. All code, prompts, the sample and verdicts are public, and `verify.py` recomputes the headline numbers.

## 4. Results

The pipeline judged 621 of the 804 notes: 177 had no retrievable source and 6 had no checkable claim. Of the 3,545 extracted claims, 2,643 were judged (1,122 *supported*, 561 *partly supported*, 871 *not in source*, 72 *contradicted*, 17 *unverified*). The other 902 were 351 claims about the post itself, which are out of scope, and 551 claims in notes without a retrievable source. 99% of the judge's quotes were found verbatim in the source.

### 4.1 How much of the evidence can be checked?

Of 1,548 cited links, 15% point to X posts and 5% to video or social media; neither can be checked as text. Of the 1,240 fetchable links, 91% were retrieved: 72% from a version dated before the note (a median of 30 days older than the note), 5% from a snapshot up to 7 days after, and 14% from the live page (Appendix F).

92% of notes by X's writer, but only 61% of human notes, cite at least one retrievable source (Figure 1). Weighted to the platform, only 52% of notes have *every* source retrievable (58% in our sample). Much of the evidence behind live fact-checks cannot be audited from outside X.

![](figures/fig_checkability.png){width=46%}

*Figure 1. Share of sampled notes (unweighted) whose cited evidence can be retrieved as text, retrieved in full, and retrieved in full and pinned to the time of writing, by writer.*

### 4.2 Are notes supported by their own sources? (H1)

**Observation.** Under the primary judge, 56–81% of checkable notes contain at least one claim their own sources do not establish (Figure 2). This level depends on the judge (Section 4.5). "Unsupported" is not "false": we test whether the cited source establishes a claim, not whether the claim is true. Among Helpful notes, human-written notes were unsupported more often, and AI writers had a much higher share of supported claims (Table 1).

| Writer | Helpful notes with an unsupported claim | Claims supported (mean per note) |
|---|---|---|
| X's Community Writer | 64.6% (CI 54.5–73.7) | 47.1% (CI 40.5–53.7) |
| Other AI writers | 56.0% (CI 46.2–65.9) | 51.3% (CI 45.0–57.8) |
| Human writers | 74.6% (CI 63.5–85.7) | 25.8% (CI 17.7–34.5) |

*Table 1. Helpful notes containing at least one claim their sources do not support, and the mean per-note share of claims supported, by writer.*

**Is it significant?**

- **Note level:** no. The pre-registered H1 gap is -10.0 points (CI -24.1 to +4.3, p = .22, Holm p = .44). With this spread, the design could reliably detect only gaps of about 20 points.
- **Claim level** (exploratory): X's writer's claims were supported 21 points more often than humans' (CI 10–32, p < .001), and other AI writers' 26 points more (CI 15–36).
- **Claim counts:** AI notes contain more claims per judged note (4.3–4.8 vs 3.4), which makes the any-claim outcome harder for them, not easier.

**Is it robust?** The direction holds in every check:

- **Notes with all sources retrieved:** a 19.2-point gap. The bootstrap CI (-37.2 to -0.5) and permutation p (.06) disagree at the margin.
- **Pre-registered sensitivity analyses:** gaps of 3–13 points.
- **Leaving out any one of X's six accounts:** its rate stays at 63–67%.
- **Gemini as judge:** an 8.8-point gap.

**Interpretation.** One possible reason is that X's writer is instructed to open and confirm each link. But other AI writers, whose pipelines we cannot see, did at least as well, so we cannot attribute the difference to that design.

![](figures/fig_unsupported.png){width=46%}

*Figure 2. Share of checkable notes with at least one claim that the note's own sources do not support, by writer and rating status, with 95% bootstrap CIs (primary judge).*

### 4.3 Does Helpful status track evidence? (H2)

We could not detect a difference. Within groups, CRNH notes were unsupported 3.8 points more often than CRH notes (CI -6.2 to +13.8, p = .23), so gaps of up to 14 points are not ruled out. The gap did not differ between X's writer and humans.

### 4.4 Do raters notice unsupported notes? (H3)

For notes with at least five ratings (n = 567), the share of raters tagging "sources do not support note" separated unsupported from supported notes no better than chance: AUROC 0.53 (CI 0.48–0.58), below the pre-registered 0.65 (Holm p = .0015).

This is not label noise or a quirk of the measure:

- **The labels are predictable.** On 251 shared notes, the second judge's share of unsupported claims predicts the primary judge's labels with AUROC 0.90.
- **Ties do not explain it.** 219 notes (39%) carry no such tag at all, creating ties; excluding them gives 0.51.
- **A gentler outcome agrees.** Against the share of unsupported claims, Spearman rho is 0.05 (p = .20).
- **The other tags agree.** They score 0.48–0.54, and every writer group shows the same pattern (Figure 3, Appendix D).

Raters' source tags appear to reflect something other than whether the cited text supports the note.

### 4.5 Can the judge be trusted?

| Check | Four labels | Supported vs unsupported |
|---|---|---|
| Gemini (another company), 1,024 claims | 76%, kappa 0.61 | 88%, kappa 0.75 |
| Claude Opus (stronger model), 355 claims | 75%, kappa 0.63 | 89%, kappa 0.74 |
| Human spot-check (one author), 29 claims | n/a | 69%, kappa 0.40; precision 0.91, recall 0.63 |

*Table 2. Agreement between the primary judge (Claude Haiku) and three independent checks. Gemini scored the Helpful and validation notes only.*

The comparisons hold under each judge; under Gemini, for example, the H3 AUROC is also 0.53. Only the *level* of unsupported notes varies. Opus is more lenient (58% vs 70% on shared notes), while Gemini (76% vs 64%) and the human labeller are stricter, so absolute rates are best read as a range. Appendices D and E give details.

## 5. Discussion and Limitations

**Implications for AI safety.** In a real deployment, raters' source signals do not track whether cited sources support a note, and nothing in the platform's metrics shows this. Writers optimised for ratings therefore face no rating pressure towards better evidence. The AI writers we studied nonetheless cite better-supporting sources than humans, for reasons we cannot determine.

**Possible mitigations, which we did not test:**

- show raters the passage that supports each claim;
- ask writers to attach a quote per claim (our judge's quotes were mechanically verifiable 99% of the time, so this looks feasible);
- check evidence with a model from another family;
- archive cited pages when the note is written.

### Limitations

1. **Judge accuracy.** Model judges agree substantially, but human agreement was moderate (kappa 0.40, 29 claims). Absolute rates depend on the judge; the comparisons repeat under each judge.
2. **Steps before the judge.** All judges read the same claims and extracted text, so splitting or extraction errors are not caught. The quote check protects only positive verdicts, while 871 of 943 unsupported verdicts are *not in source*.
3. **Time pinning and missing sources.** 169 sources are live copies and 59 are snapshots from after the note. X posts and video may support some claims, but restricting to fully retrieved notes widens the AI–human gap.
4. **Comparison.** AI and human notes mostly cover different posts [3], and the six-account mapping is inferred from volume.

Further limitations are in Appendix A.

### Future Work

The next steps are full human validation of the released 90-claim set, including a check of *not in source* verdicts against the page, and a truth check of unsupported Helpful notes. After that we would run a matched comparison on posts with both AI and human notes, and a test of showing raters quoted evidence.

## 6. Conclusion

AI now writes most of the fact-checks that X shows its users. In an exploratory claim-level analysis, AI-written notes had more of their claims supported by their own sources than human notes did; the pre-registered note-level comparison was not significant. Many notes from every writer contain a claim their sources do not establish, and raters' source signals did not distinguish supported from unsupported notes. Evaluations that stop at "rated helpful" miss whether a fact-check is backed by its evidence, and that is cheap to measure.

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
12. Li, H., De, S., Revel, M., Haupt, A., Miller, B., Coleman, K., Baxter, J., Saveski, M., Bakker, M. A. (2025). Scaling Human Judgment in Community Notes with LLMs. arXiv:2506.24118. https://arxiv.org/abs/2506.24118
13. Li, H., Bakker, M. A. (2026). AI Fact-Checking in the Wild: A Field Evaluation of LLM-Written Community Notes on X. arXiv:2604.02592. https://arxiv.org/abs/2604.02592
14. Liu, N. F., Zhang, T., Liang, P. (2023). Evaluating Verifiability in Generative Search Engines. Findings of EMNLP 2023. https://arxiv.org/abs/2304.09848
15. Allen, M., Desai, N., Namazi, A., Leas, E., Dredze, M., Smith, D., Ayers, J. (2024). Characteristics of X (Formerly Twitter) Community Notes Addressing COVID-19 Vaccine Misinformation. JAMA 331(19), 1670. https://doi.org/10.1001/jama.2024.4800
16. Columbia Journalism Review, Tow Center (2025, 6 November). [Analysis of AI-written Community Notes on X.] https://www.cjr.org/analysis/x-twitter-ai-fact-checkers-community-notes-misinformation-bots.php

## Appendix A. Limitations and Dual-Use / Ethical Considerations

**Limitations.**

- **Observational design.** We measure association, not why notes are unsupported.
- **Limited human validation.** The pre-registered 90-claim blind human validation could not be completed. It was replaced by agreement with a cross-family judge and a stronger reference model, which cannot rule out errors that models share, and by a single-author spot-check of 30 claims (29 decided).
  - The spot-check shows moderate agreement (kappa 0.40) and high precision of the judge's "unsupported" (0.91).
  - Its labels may be noisy: they were made quickly, by one person, from a key-word view. Quote verification removes hallucinated support but not mistaken "not in source" verdicts. Human labelling of the released 90-claim validation set is the most important next step.
- **Missing sources.** A claim may be supported by a source we could not retrieve (an X post, a video). Hence the all-sources-retrieved analysis, in which the AI–human gap widens.
- **Time pinning.** 59 retrieved sources come from snapshots after the note was written and 169 are live copies; pre-note snapshots are a median of 30 days older than the note (90th percentile 385 days). Any of these may differ from what the writer saw.
- **Deleted notes** are invisible in the public data, and X's writer deletes drafts predicted to fail.
- **Account mapping.** The `cw` label is inferred from volume patterns. X publishes the six account aliases but not their participant IDs, so the mapping is not verified.
- **Strict outcome.** The note-level outcome counts a single unsupported claim; claim-level rates are reported alongside.
- **Scope.** Statuses change over time, and the study covers one platform in one 11-week window.
- **Model families.** The judges come from model families other than the writer's (Claude and Gemini judging Grok-written notes). That is deliberate, since it avoids a model checking its own work. Authorship-specific bias is tested by kappa split by authorship.

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
| 15 Nov, ~22:55 | Human validation not completed; replaced by a cross-family judge (Gemini) and a stronger reference judge (Claude Opus 5.5), after the primary run (Section 3) |
| 16 Nov, ~09:00 | Quick blind human spot-check of 30 claims (binary question) registered before any label; two labelling passes, 29 decided labels in the second (Section 4.5) |

All entries are in the repository's git history.

## Appendix D. Judge validation details

![](figures/fig_roc.png){width=34%}

*Figure 3. ROC curves for the share of raters tagging "sources do not support note" as a predictor of verified unsupported notes, by writer. The diagonal is chance.*

**Cross-family agreement.** On 1,024 claims scored by both the primary judge (Claude Haiku 5.5) and Gemini 3.5 Flash-Lite:

| Comparison | Agreement | Cohen's kappa |
|---|---|---|
| Supported vs unsupported | 87.9% | 0.75 |
| All four labels | 75.6% | 0.61 |
| Note-level UNSUPPORTED (251 notes) | 86.9% | 0.69 |

- **No authorship bias:** agreement is similar for AI-written notes (kappa 0.76, supported vs unsupported) and human-written notes (kappa 0.67).
- **Where they disagree:** mostly the `PARTIAL`/`SUPPORTED` boundary (112 claims the primary judge called `PARTIAL` were `SUPPORTED` for Gemini) and `PARTIAL`/`NOT_IN_SOURCE` (79).
- **Gemini is stricter, not more lenient.** It marks 76% of notes unsupported, against the primary judge's 64%. The high unsupported rates are not an artefact of the primary judge.

**Findings under each judge.** Recomputed with Gemini's verdicts, the conclusions are unchanged:

- **H1:** X's writer is 8.8 points below humans among Helpful notes (CI -21.4 to +4.0), against 10.0 points with the primary judge.
- **H3:** the rater-tag AUROC is 0.53 under both judges.

**Stronger reference.** Claude Opus 5.5 re-judged 60 of the 86 validation notes before a usage limit stopped it, covering 79 of the 90 stratified validation claims and 355 claims in all.

| Comparison with Opus | Result |
|---|---|
| Supported vs unsupported, all 355 shared claims | 88.7% agreement, kappa = 0.74 |
| Same, AI-written notes | kappa = 0.77 |
| Same, human-written notes | kappa = 0.63 |
| Primary judge's "unsupported" on the 79 validation claims (weighted) | precision 0.87, recall 0.88 |

By label, the reference confirms:

- **almost every `SUPPORTED`** (100% of validation claims) **and `NOT_IN_SOURCE`** (89%);
- **few `CONTRADICTED` verdicts.** It mostly downgrades them to `PARTIAL` or `NOT_IN_SOURCE`. The rare contradicted label should be read as "not supported", not as a confirmed contradiction.

**The *level* of unsupported notes depends on the judge; the comparisons do not.**

- On the 76 notes it shares with the primary judge, Opus marks 58% unsupported, against the primary judge's 70%.
- On its 251 notes, Gemini marks 76%, against the primary judge's 64%.

The absolute rates in Section 4.2 should therefore be read as a range across judges. The AI–human gap (Section 4.2) and the null rater signal (Section 4.4) hold under both judges that scored the full Helpful sample (Claude Haiku and Gemini).

**Human spot-check.** One author blindly labelled 30 of the validation claims (10 per group) with a single question: does the source support at least the main point? To save time, the labelling view showed the passages around the claim's key words by default, with the full text one click away.

- **Two passes.** A first pass decided 7 claims. A second pass, using the full text, decided 29 (9 supported, 20 not supported, 1 can't tell). The 7 first-pass labels were unchanged.
- **Agreement on the 29 decided claims:**

| Judge | Agreement with the author | kappa | Weighted precision of "unsupported" | Weighted recall |
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

![](figures/fig_claim_types.png){width=60%}

*Figure 4. Claim types among each group's unsupported claims (primary judge).*

## Appendix F. Method details

**Sample.** 110 notes per Helpful cell was planned for about 80% power against a 25% vs 10% difference at alpha = .05. At the observed rates (65–75%), the note-level H1 comparison has a standard error near 7 points, so 80% power requires a gap of about 20 points; power for the 10-point gap we observed is below 30%. The 78 CRNH notes per group equal every CRNH note from X's writer in the window. In the window, 41 accounts were enrolled as AI writers, 28 of them active. Notes with no status row are 12.7% of every creation week, consistent with deleted notes rather than publication lag.

**Retrieval.** Wikipedia revisions come from the MediaWiki API. Web pages come from Internet Archive snapshots found through the availability API and time-bounded CDX queries. Main text is extracted with trafilatura, keeping the full visible text as a fallback; PDF text uses pypdf. Archived payloads still compressed with zstd, gzip or brotli are decompressed first.

Of 1,240 fetchable URLs, 1,123 (91%) were retrieved as text and 117 failed (dead, blocked or too little text). Successful retrievals by route:

| Retrieval route | URLs |
|---|---|
| Archive snapshot before the note | 790 |
| Wikipedia revision at writing time | 102 |
| Archived copy cited by the note itself | 3 |
| Archive snapshot up to 7 days after the note | 59 |
| Live page, not time-pinned | 169 |

895 sources (72% of fetchable URLs) are therefore pinned strictly before the note. Pre-note snapshots are a median of 30 days older than the note; 22% are within one day of it.

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

- **CRH, CRNH, NMR** are the platform statuses Currently Rated Helpful, Currently Rated Not Helpful and Needs More Ratings. **H2** was pre-registered in two parts. **H2a** is the weighted average of within-group gaps (weights: each group's CRH + CRNH population), tested by permuting status within groups.
- **H2b** is the status × group interaction in a logistic regression that controls for the number of URLs and the log of note length.
- **Sensitivity analyses:**
  - `PARTIAL` counted as unsupported;
  - `UNVERIFIED` counted as unsupported;
  - notes with all sources retrieved;
  - time-pinned sources only;
  - excluding notes that cite Wikipedia;
  - leaving out each `cw` account in turn.

## LLM Usage Statement

We used Claude (Anthropic), through Claude Code, as an AI assistant during this project: to brainstorm and scope the research question, to write and debug the analysis code, and to draft and edit text. The authors directed the project, approved its design, carried out the human spot-check, and reviewed the final report. Language models are also part of the method itself (Section 3). All reported numbers are produced by the released code and can be recomputed with `verify.py`. References were checked against the original sources.
