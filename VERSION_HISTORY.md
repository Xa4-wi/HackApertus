# ClaimLens version history

This file records implementation milestones, development experiments and retired approaches. Git records individual changes. The current system and measured limitations belong in the [technical report](track_2a/technical_report.md); the compact [validation record](track_2a/docs/validation.md) identifies the observations supporting that report.

Completed local artifacts live in `archive/track_2a/output/`, retaining original directory names, source snapshots, failures, inputs and measurement identities. These paths are local archival evidence and may be absent from a clean public checkout. They are neither runtime inputs nor final submission contents. Never resume a new implementation into an old measurement directory or relabel an incomplete run as a benchmark.

## V1 — Initial prototype

Established the template's Track 2A layout, official JSONL CLI, original-source quotation checks and browser prototype. Selected OST's multilingual Swiss voting-booklet challenge and Apertus 1.5 8B. Downloaded the pinned OST dataset and a community Q4_K_M text-backbone conversion; configured native llama.cpp with Metal on the local Mac.

The initial interface included prewritten walkthrough examples alongside live inference. They illustrated the interface and were never model accuracy results. The full-source approach rejected overlong contexts rather than silently truncating them. The first committed prototype is `40b8604`.

Preserved artifacts: [initial local smoke](archive/track_2a/output/local-smoke/), [walkthrough predictions](archive/track_2a/output/demo-predictions.jsonl).

## V2 — Booklet library and measured development failures

Added booklet import/cache, URL and upload workflows, OCR for German/French/Italian, original PDF links, structured evidence display and repeatable public-data evaluation. The library reached 60 PDFs. Software, browser and Docker checks verified interface behavior, while live inference exposed classification problems.

| Development measurement | Result |
| --- | --- |
| Initial 27-reference baseline | 19 accepted, 8 failures; 15/27 correct including failures; macro-F1 0.545635 |
| Updated 27-reference run | 27 accepted, zero failures; 18/27 correct; macro-F1 0.555556 |
| Neutral class in updated run | All nine cases misclassified as contradiction |
| Updated time and usage | Mean 24.11 s; 69,932 input / 6,742 output tokens |
| Full-booklet number-change check | Incorrect verdict despite an exact, independently located quotation |
| Software verification | 125 tests passed; local browser and isolated container checks passed with stubbed test inference |

Both reference cohorts are development samples. Fixing structural failures did not solve the neutral-class error. The booklet failure showed why exact text provenance must not be treated as proof of sound reasoning.

Preserved artifacts: [baseline](archive/track_2a/output/v2-evaluation-baseline/), [updated evaluation](archive/track_2a/output/v2-evaluation/), [booklet/browser smoke](archive/track_2a/output/v2-smoke/), [V2 report](archive/track_2a/output/pdf/claimlens-v2-report.pdf). The first completed-prototype commit is `fb8348c`.

## V3 — Local live interface

Reworked the frontend for clearer source selection, model readiness, review results and evidence. Removed walkthrough mode and bundled example answers; legacy demo requests are rejected. Browser inference uses the configured local Apertus model, while the official CLI retains organizer-endpoint support.

An actual synthetic French-source/German-claim browser request returned expected entailment in 11.47 seconds with 734 input / 125 output tokens. Desktop/mobile checks verified import, upload/download, JSON export, stale-result invalidation and layout. The 125 Python tests and frontend contract checks passed. This was one protocol/UI observation, not a quality benchmark.

Preserved artifacts: [V3 UI verification and screenshots](archive/track_2a/output/v3-ui/).

## V4 — Evaluation contract and reference classification

Aligned optional input metadata and required output fields with the challenge, hardened environment precedence, measured usage across retries, retained partial batches on failure and added independent exact-page audits. A compact explanation-first response and source-relation vocabulary targeted neutral/contradiction confusion. Long booklets used segmented extraction, bounded evidence reduction and a joint verdict.

Prepared public-data cohorts grouped by ballot date, with deduplication and separate inference inputs/gold. Development dates were excluded from final-cohort dates. Reserved cohorts remained public training data and could contain related or translated claims; they were not the organizer's private benchmark.

| Recorded cohort | Classification | Mean case time |
| --- | --- | --- |
| Development, 27 references | 25/27 correct; macro-F1 0.927451; all nine neutral cases correct | 17.8 s |
| Primary Task B, 27 references | 26/27 correct; macro-F1 0.9628; zero failures | 15.55 s |
| Extension Task B, 27 references | 24/27 correct; macro-F1 0.8866; zero failures | 16.15 s |
| Combined Task B, 54 references | 50/54 correct; macro-F1 0.9247219356; zero failures | 15.85 s |

Combined Task B usage was 119,486 input / 7,069 output tokens; p95 was 27.74 seconds. All 18 neutral cases were correct, and independent audits verified 34 returned reference quotations. Combined F1 was recomputed from all predictions, not averaged from cohort F1 values. These measurements retain their original source/runtime identities and have not been rerun on V5.

The first full-booklet attempt failed on context capacity and remains preserved. A bounded-reduction repair prevented repeated full analysis for fixed capacity failures. The nine-case Task A rerun was stopped at the user's request after one accepted, **unscored** case took **458.53 seconds**, 62,050 input / 661 output tokens, six model calls and one reduction round. The next in-flight case was interrupted with incomplete usage. No Task A F1 or overall readiness result exists for that run.

Native timing analysis attributed 380.37 seconds, about 83% of the completed case, to prompt processing; generation consumed 44.09 seconds. This motivated reducing repeated full-source input. GPU offload, Q4 weights and disabled reasoning were already in use; the data did not establish swapping or a cache-specific speed effect.

Interrupted prompt/API attempts and source snapshots remain in their cohort directories and must not be merged into completed runs. A local generic JSON reference check passed without testing the authenticated organizer proxy.

Preserved artifacts: [V4 readiness](archive/track_2a/output/v4-readiness/), [combined Task B](archive/track_2a/output/v4-readiness/final-b-combined/), [incomplete Task A](archive/track_2a/output/v4-readiness/final-a/), [timing profile](archive/track_2a/output/v4-readiness/latency-analysis/), [stopped technical report](archive/track_2a/output/v4-readiness/technical-report-v4-stopped.md), [V4 PDF](archive/track_2a/output/pdf/claimlens-v4-report.pdf). Contract-work commit: `6887f10`.

## V5 — Multilingual retrieval and lower latency

Made local retrieval the default for booklet cases. Apertus expands multilingual queries, a cached lexical index selects exact source spans with neighboring context, and one final Apertus call produces the verdict. Short sources use one complete-source call. Task B keeps full-reference processing. Added a 5,000-token final prompt budget, a shared 120-second fast-case deadline, at most four transport attempts and UI disclosure of selected-source coverage. The runtime cache limit changed from its implicit 8,192 MiB to 1,024 MiB.

Three frozen development cases were repeatedly used to diagnose evidence and response formats: German→French entailment, French→Italian neutral and Italian→German contradiction. Their PDFs have 32, 72 and 40 pages. These cases exclude reserved final dates and do not provide independent validation after tuning.

| Experiment | Labels | Mean time | Decision |
| --- | --- | --- | --- |
| Initial retrieval with short quotations | 3/3; macro-F1 1.0 | 39.15 s | Replaced: footer-only AHV quote and truncated biodiversity fragment did not substantiate verdicts |
| Contextual quotations | 3/3; macro-F1 1.0 | 54.97 s | Selected implementation |
| Citation-ID output optimization | 2/3; macro-F1 0.5556 | 48.93 s | Rejected after classification regressed |

Initial short quotations passed exact-page checks despite poor semantic support. The selected version retains body context, expands only uniquely identifiable exact anchors for ordinary JSON and discloses expansions. Native generation returns full source quotations; the rejected citation-ID optimization is not shipped.

The selected run used **12,819 input / 1,632 output tokens**, two calls per case and warm lexical indexes, with PDF extraction repeated. Times were 70.63, 38.68 and 55.60 seconds; p95 is merely the largest of three observations. Official evidence overlap was **0.50 (1/2 non-neutral cases)**. All three quotes verified on their physical pages. Manual review found substantive support for both non-neutral decisions, while identifying an unnecessary AHV background quote and a compound biodiversity claim refuted through its spending clause. AHV alignment remained below the official fuzzy threshold. These limitations remain visible in the final report.

A separate timing-only repeat of the earlier slow booklet took **56.11 seconds**, 4,363 input / 526 output tokens and two calls: **8.17× faster** with **92.97% fewer input tokens** than the 458.53-second observation. It was not scored for correctness. Same hardware/model/context, a changed runtime cache allowance and a warm index make this a comparison of the combined configuration, not an isolated causal test.

A subsequent generic JSON check exposed missing translated proposal hints. A repair requires all three claim phrases but reuses the original proposal title for missing/blank optional hints. It adds no retry and leaves native constrained payloads unchanged. Scored booklet cases were not repeated afterward. A synthetic French fee source and German claim then returned expected entailment with an exact page-2 quote in **13.82 seconds**, using 1,225 input / 187 output tokens across two calls. This local check did not establish organizer access or general accuracy.

The selected source passed **241 tests locally and 241 inside the CPU `linux/amd64` image**, with network disabled, read-only root and temporary storage; frontend and two submission-contract checks also passed. The five-page V5 report was rendered and visually reviewed. Model, local server and container runtime were stopped after checks. The base inference implementation was committed as `6680127`; later compatibility changes are identified by the saved source manifests.

Preserved artifacts: [initial retrieval](archive/track_2a/output/v5-latency/), [selected contextual run](archive/track_2a/output/v5-latency-context/), [same-case comparison](archive/track_2a/output/v5-latency-context/same-case-comparison/), [citation review](archive/track_2a/output/v5-latency-context/verification/citation-review.md), [compatibility provenance](archive/track_2a/output/v5-latency-context/verification/final-source.json), [rejected citation-ID experiment](archive/track_2a/output/v5-fast-final/), [historical V5 report](archive/track_2a/output/pdf/claimlens-v5-report.pdf). The directory name `v5-fast-final` is historical and does not identify the selected implementation.

## Repository and final-report organization

Development chronology now lives here. The active [technical report](track_2a/technical_report.md) follows the original template's Summary, Architecture, Use of Apertus, Data, Evaluation, Limitations, Reproducibility and Next steps sections, then License and References. At that milestone, the PDF was generated under `submission/`; the former export is now preserved in `archive/legacy-submission/`. The current PDF lives beside its source in `track_2a/`. This organization changes documentation and packaging, not the recorded model measurements.

The repository cleanup added explicit handoff staging, archived-cohort path checks and source/report hash verification. At that milestone, 252 software tests passed; the recorded model measurements were unchanged.

## V6 — Bounded token-efficiency experiments and rejected promotion

Added optional source-language query generation and native exact-prefix citation output, with an experiment harness that separates tuning from confirmation. Production remains on **multilingual queries, full native quotations and a 5,000-token final prompt budget**. The faster candidate was rejected after a confirmation regression; experimental flags remain off by default.

Nine previously unexercised exact requests were frozen from the pinned public OST development dates before inference, one per language pair and three per label. Six requests were used for tuning and three were held for confirmation after a source/configuration lock. Reserved final dates and previously exercised exact requests were excluded; related or translated claim families and model pretraining exposure are not ruled out. This is a small public-development comparison, not the organizer's private benchmark.

The harness preserves the imported source snapshot, runner/settings identities, frozen input/PDF hashes, separate gold, stage usage, wall time, failures and accepted predictions. Inference reads no gold. Baseline code came from the verified prior handoff; candidate variants used separate snapshots. Gold scoring uses the unchanged pinned official evaluator, and independent audits check exact physical-page provenance.

| Six-case tuning variant | Correct / macro-F1 | Mean time | Input / output tokens | Official evidence overlap |
| --- | --- | ---: | ---: | ---: |
| Baseline: multilingual, full, 5,000 | 4/6; 0.655556 | 48.84 s | 24,592 / 2,938 | 0.25 |
| Compact: source queries, prefixes, 5,000 | 3/6; 0.444444 | 29.46 s | 24,126 / 859 | 0.25 |
| Prefix-only: multilingual, prefixes, 5,000 | 4/6; 0.655556 | 39.42 s | 24,592 / 1,782 | 0.25 |
| Prefix-only: multilingual, prefixes, 3,500 | 4/6; 0.655556 | 37.30 s | 21,812 / 1,805 | 0.25 |
| Minimum-context prefixes: multilingual, 3,500 | 4/6; 0.655556 | 35.32 s | 21,812 / 1,801 | 0.50 |

Source-language query mode skips expansion when source and claim languages explicitly match, otherwise generates only the source-language phrases; missing/mixed source metadata retains multilingual expansion. The compact combination regressed biodiversity classification and was rejected. Native prefix mode changes quote enums without changing the NLI prompt, source payload, explanation-first order or reference-task behavior. Registered unique exact prefixes expand to original complete contextual quotations; unregistered or ambiguous aliases fail with measured usage retained. Generic JSON behavior remains separate.

Prefix-only at 5,000 preserved all six labels, per-case input-token counts and selected-page lists. It reduced output but changed retirement evidence selection: the footer remained while useful partial support and unrelated background were dropped. The 3,500-token budget corrected fighter financing but regressed biodiversity, so equal 4/6 tuning accuracy did not mean identical case quality.

The final tuning candidate additionally excludes very short citation candidates, under 200 characters or 25 words, when substantial contextual alternatives exist; all-short sources fall back. This restored the actual retirement international-comparison paragraph, with the committee's attribution and all decisive ages/countries. It did not solve chart-only or wrong-speaker citations. Citation length is not a relevance classifier.

The final candidate `body-prefix-3500` was locked after tuning. Confirmation then exposed a further regression:

| Three-case confirmation | Baseline | Locked candidate |
| --- | ---: | ---: |
| Correct labels | 3/3 | 2/3 |
| Macro-F1 | 1.000000 | 0.555556 |
| Mean case time | 41.52 s | 32.83 s |
| Input / output tokens | 11,931 / 1,103 | 10,932 / 740 |
| Official evidence overlap | 0/2 | 0/2 |

Both versions correctly refuted a 2% stamp-duty claim using source text specifying 1%, and correctly returned neutral for a pension claim attached to the SSR proposal. On the subletting recommendation, baseline returned entailment with a page-31 quotation explicitly recommending acceptance of the amendment; the locked candidate returned neutral and no evidence. No implementation was promoted or further tuned on those confirmation outcomes.

Across all nine unique requests, baseline achieved **7/9, macro-F1 0.774603**, compared with **6/9, macro-F1 0.638889** for the rejected candidate. These combined figures include tuning cases. Mean time was **46.400 → 34.493 seconds**, input usage **36,523 → 32,744**, output usage **4,041 → 2,541**, and official evidence overlap **1/6 → 2/6**. All **nine baseline and five candidate quotations** verified on their physical pages. The candidate was faster but failed the confirmation quality check.

Manual reviews retain the material semantic defects. A correct retirement verdict initially cited a footer instead of the decisive comparison. Both configurations inverted a cost-brake claim despite quoting supportive text. The baseline biodiversity verdict used a different speaker's paragraph; the smaller-budget candidate instead returned neutral. The candidate's fighter-financing chart did not establish the full claim. Exact quotation provenance and fuzzy gold overlap do not establish sound reasoning or substantive citation support.

Measurements used the Apple M4/16 GiB machine, verified pinned Q4_K_M artifact, native llama.cpp Metal build 11429 (`d81235049`), 16K context, one slot, 1,024 MiB prompt-cache allowance, temperature zero and reasoning off. The model was loaded before timing. Variants ran sequentially with uncontrolled prompt/index caches and thermal state; baseline scoring briefly overlapped the first compact case. These conditions limit causal interpretation of elapsed-time differences. No authenticated organizer endpoint was tested.

The measured baseline source digest is `3036f8e41b71724fb86798a9f8dfe72f1d13361775a2012536935c13ce2b9e89`; the locked candidate digest is `01d3cafadb1ae7b4ea086c424a697f0fb00ef4ab7b0b4e6541f40d1304973355`. Delivery manifests separately identify the final code, including disabled experimental branches; they are not additional model-quality measurements.

Final verification passed **313 local tests** in 6.533 seconds. Docker ran 313 tests in 13.864 seconds: **312 passed and one host-only Makefile forwarding test was skipped**, because Make is absent from the minimal image. Frontend checks passed, as did both Task A/B container contracts in 7.249 seconds. Eight mocked native/generic query/completion scenarios verified default request parity with baseline. The pinned model artifact passed verification and the model was stopped after inference. These software and protocol checks do not establish model accuracy.

The next independent comparison should isolate minimum-context prefix output at the retained 5,000-token multilingual settings on newly frozen, unseen claims. The opened confirmation cases must not be reused as independent validation.

Preserved artifacts: [V6 efficiency experiment](archive/track_2a/output/v6-efficiency/), [paired complete comparison](archive/track_2a/output/v6-efficiency/review/paired-complete/comparison.md), [tuning citation review](archive/track_2a/output/v6-efficiency/review/tuning-evidence.md), [confirmation citation review](archive/track_2a/output/v6-efficiency/review/confirmation-evidence.md), [candidate lock](archive/track_2a/output/v6-efficiency/candidate-lock.json), [rejection decision](archive/track_2a/output/v6-efficiency/selection-decision.json) and [runtime provenance](archive/track_2a/output/v6-efficiency/runtime.json).

## V7 — Full-context citation comparison and two-minute presentation package

Kept multilingual queries and the complete 5,000-token assessment budget while testing native short quotation prefixes against full quotations. The protocol, two identical source snapshots and a single candidate were fixed before selecting nine new exact public-development requests, excluding earlier tuning/confirmation requests and reserved final dates. Six tuning cases and three locked confirmation cases cover all nine language pairs. No adaptive variants were introduced.

Added opt-in complete prompt/source/raw-response traces to the efficiency harness. Trace privacy, hashing, resume integrity and the candidate lock have automated checks. All nine query responses, assessment messages and source-passage arrays match exactly between variants. Gold remains outside inference; both confirmation runs finished before scoring or semantic review.

| Current paired result | Full-quotation baseline | Prefix candidate |
| --- | ---: | ---: |
| Tuning / confirmation correct | 5/6 / 2/3 | 5/6 / 2/3 |
| Combined correct / macro-F1 | 7/9 / 0.750000 | 7/9 / 0.750000 |
| Mean case time | 47.417 s | 40.449 s |
| Input / output tokens | 37,244 / 4,148 | 37,244 / 2,900 |
| Official evidence overlap | 3/6 | 3/6 |
| Exact physical-page quotations | 6/6 verified | 4/4 verified |

All 18 predictions and 36 model transport calls completed with full usage. The candidate saved 14.70% mean time and 30.09% output, with no input reduction. Single serial observations, uncontrolled cache/thermal conditions and only one case per language pair limit interpretation. Five neutral cases had identical output counts and slightly longer candidate times.

**Promotion was rejected after tuning.** The French-to-Italian lease claim retained its correct label but lost useful quotations on pages 9 and 36, leaving only background on page 8. The decisive paragraph was present in both model inputs, and all baseline quotations remained eligible in the candidate grammar. Confirmation added no regression and could not reverse this already failed evidence gate. Full quotations, multilingual queries and 5,000 tokens remain the production defaults. Both versions retain cash/climate interpretation errors and incomplete bodily-integrity/restaurant evidence; equal labels and exact quotations do not establish adequate support.

The final prediction Python package matches both measured snapshots: `0064cb2247b3ae06f72533063c0accbd9cac39c7a119898e84d278264805796e`, using the sorted relative-path-to-file-SHA JSON digest. The local model artifact was verified again. Two old regression requests were prepared but not run after rejection; they do not enter the results.

Prepared a 225-word English narration and contiguous 120-second shot list. The real HTTP application rehearsal used the German 13 February 2022 booklet and an Italian 2% stamp-duty claim. It returned contradiction with the original 1% statement on physical page 38 in 32.004 seconds, using 3,485 input and 297 output tokens across two calls. This known presentation case is separate from fresh evaluation. The script discloses any removed wait and requires the actual recording's own values.

Fixed the frontend coverage denominator to use physical booklet pages, including blank pages, instead of only text-bearing pages; the example displays 8/64 rather than 8/63. A DOM regression fixture covers the distinction. Browser automation was unavailable, so live HTTP and DOM checks were completed without claiming visual browser review. Human framing and video recording remain outstanding.

Verification: **316 local tests passed** in 6.816 seconds. Docker ran 316 tests in 14.085 seconds: **315 passed and one host-Make test skipped**. Frontend checks passed after the page-count correction. Active Task A/B contracts passed in 7.477 seconds; the independent clean handoff build and both contracts passed in 7.291 seconds. The five-page technical report was rendered and all pages visually reviewed. The clean handoff includes 88 source files, the presentation docs and a separate final PDF; no model, dataset, gold, `.env` or development archive is delivered. Native model/application and the verification runtime are stopped after checks.

Preserved artifacts: [V7 fixed comparison](archive/track_2a/output/v7-final/), [paired results](archive/track_2a/output/v7-final/review/paired-complete/comparison.md), [tuning evidence review](archive/track_2a/output/v7-final/review/tuning-evidence.md), [confirmation evidence review](archive/track_2a/output/v7-final/review/confirmation-evidence.md), [promotion decision](archive/track_2a/output/v7-final/promotion-decision.json), [actual rehearsal](archive/track_2a/output/v7-final/presentation/rehearsal.json). Final recording instructions: [walkthrough](track_2a/docs/presentation-walkthrough.md), [two-minute script](track_2a/docs/video-script.md).

## Template layout and dependency cleanup

Restored a single active template project in `track_2a/`, with `technical_report.md` and `technical_report.pdf` directly visible together. The root `submission/` directory was moved intact to `archive/legacy-submission/`; all 100 existing files were hash-verified during relocation. Retired the duplicate-source export command, allowlist and eight export-only tests under `archive/track_2a/`. Docker targets `make submission` and `make verify-submission` remain the evaluator image commands and create no repository submission folder.

`make report` now writes the final PDF into `track_2a/`. Build provenance, rendered QA pages and visual-review metadata live in ignored `track_2a/output/report/`. The final PDF is intentionally eligible for version control. Updated setup, delivery and video instructions to use the active project directly.

Simplified dependencies to `requirements.txt` for the two runtime packages and `requirements-dev.txt` for runtime plus dataset preparation, evaluation and report generation. The three older optional manifests were preserved under `archive/track_2a/dependencies/`. All eight existing version pins are unchanged; installed-version verification and `pip check` passed, without installs or upgrades.

After cleanup, **308 current software tests passed in 6.539 seconds**, and frontend DOM checks passed. The reduction from 316 accounts exactly for the eight tests of the now-archived export tool. Prediction code and recorded inference results are unchanged. This layout-only work did not start the local Apertus model, application server or Colima.
