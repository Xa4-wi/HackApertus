# Current validation record

The delivered configuration retains **multilingual retrieval queries, a 5,000-token assessment input budget and full contextual quotations**. The fixed exact-prefix candidate preserved all nine predicted labels and reduced measured output and time, but lost useful supporting evidence for one tuning claim. It therefore failed the per-case evidence gate and was rejected for normal use. No default latency improvement is claimed. This page records the current validation on 8 October 2026; development history belongs in the workspace's root `VERSION_HISTORY.md`.

```dotenv
RETRIEVAL_QUERY_MODE=multilingual
RETRIEVAL_CITATION_MODE=full
RETRIEVAL_PROMPT_TOKENS=5000
```

## Recorded checks

| Check | Current result | Scope |
| --- | --- | --- |
| Current local Python tests | 308 passed in 6.539 s after layout/dependency cleanup | Eight tests for the retired export tool moved into the archive; prediction and interface coverage retained |
| Frontend DOM simulation | Passed again after layout cleanup | Live-only requests, model gating, library/imports, evidence/PDF links and physical-page coverage including a blank-page fixture |
| Actual browser visual check | Not performed in this run | Browser-control plugin unavailable; DOM simulation does not verify rendered appearance |
| Previously recorded Docker Python tests | 316 run: 315 passed, 1 host-Make test skipped; 14.085 s | Network disabled and read-only filesystem; minimal runtime has no host `make` |
| Previously recorded submission interface checks | 2 passed in 7.477 s | Task A and Task B container contracts |
| Archived source export checks | Prior independent build and both interface checks passed in 7.291 s | Historical 88-file export preserved in `archive/legacy-submission/`; current delivery uses `track_2a/` directly |
| Final technical report | All 5 rendered PDF pages visually reviewed; passed | PDF beside its Markdown source in `track_2a/`; build/review records in `output/report/` |
| Live presentation rehearsal | Label 2; 32.004 s analysis time; 3,485 input / 297 output tokens; two calls | Actual local HTTP application API; known demonstration case excluded from benchmark denominators |
| Task A paired inference | 18/18 accepted predictions; 36 model transport calls | Baseline and candidate each process the same nine frozen booklet cases; no failed or missing cases |
| Retained baseline labels | 7/9 correct; macro-F1 0.750000 | Six tuning and three locked confirmation cases; combined result is descriptive |
| Retained baseline latency and usage | Mean 47.417 s; 37,244 input / 4,148 output tokens | Complete provider usage; model loading excluded |
| Baseline official evidence overlap | 0.500000, or 3/6 non-neutral gold cases | Unmodified official fuzzy-overlap scorer |
| Baseline quotation/page audit | 6/6 emitted quotations verified | Exact wording and physical PDF page; semantic relevance reviewed separately |
| Organizer endpoint / private benchmark | Not tested | Authenticated organizer access and private evaluation remain outstanding |

The measured model was the pinned Q4_K_M text conversion of Apertus v1.5 8B on an Apple M4 Mac with 16 GiB RAM, Metal, a 16,384-token context, one inference slot and a 1,024 MiB launcher prompt-cache limit. Model artifact verification passed after inference. Cases ran serially through the production CLI with a 120-second budget and at most four transport attempts. PDF parsing checks deadlines cooperatively between operations. See [local-model.md](local-model.md) for artifact and runtime configuration. Software tests and the presentation rehearsal are separate from model-quality measurements.

The presentation rehearsal returned a page-38 quotation specifying 1%, directly contradicting its known 2% claim. HTTP wall time was 32.014 s. The UI now uses the library's physical PDF page count for its coverage denominator: this booklet has 64 physical pages but 63 text-bearing pages. A DOM test checks that a blank page does not reduce that denominator. This frontend correction does not change the measured Python prediction pipeline. The local model and application server were stopped after live checks. Colima was stopped after container verification; final checks found no listeners on ports 8000/8081 and confirmed the profile was stopped.

The layout cleanup consolidated optional tooling into `requirements-dev.txt`, which includes the lightweight `requirements.txt`. All eight installed versions match the unchanged pins, and `pip check` passed. No dependencies were installed or upgraded. The model and application were not started for this cleanup, and Docker checks above retain their original measurement dates. Current local test output is kept in `track_2a/output/layout-cleanup/local-tests.log`.

## Fixed comparison and rejection decision

The two-variant protocol and identical source snapshots were fixed before selecting nine new exact public-development requests. Selection excluded every archived prior exact request, including earlier confirmation inputs, and all reserved final ballot dates. Cases cover all nine German/French/Italian source-to-claim combinations and three examples per label. Six tuning cases contain two examples per label; the three reserved cross-language confirmation cases contain one per label.

Both configurations use multilingual queries and the full 5,000-token input budget. `baseline` requests full contextual quotations. `body-prefix-5000` changes native retrieved response grammar to short registered quotation prefixes, applies the existing substantial-body candidate filter and expands selected prefixes into their complete exact source passages locally. There were no adaptive variants or source changes during this experiment. The candidate was rejected after tuning; the locked confirmation comparison completed the predeclared protocol and could not reverse that observed evidence regression. Both confirmation inference runs finished before either confirmation score/gold review.

| Cohort | Baseline → candidate correct | Baseline → candidate macro-F1 | Baseline → candidate mean time | Input tokens, each | Baseline → candidate output tokens |
| --- | --- | --- | --- | ---: | ---: |
| Six tuning cases | 5/6 → 5/6 | 0.822222 → 0.822222 | 49.781 → 41.092 s | 25,113 | 2,966 → 1,930 |
| Three locked confirmation cases | 2/3 → 2/3 | 0.555556 → 0.555556 | 42.689 → 39.162 s | 12,131 | 1,182 → 970 |
| Combined nine, descriptive | 7/9 → 7/9 | 0.750000 → 0.750000 | 47.417 → 40.449 s | 37,244 | 4,148 → 2,900 |

All nine individual predicted labels match, with no classification or acceptance regressions. Exact generated query JSON, assessment messages and supplied source-passage arrays also match in **9/9 pairs**. Input tokens are identical. Across the nine cases, candidate mean time is **14.70% lower** and output tokens **30.09% lower**; these are experimental measurements, not gains in the delivered defaults. Tuning alone measured 17.45% less time and 34.93% less output.

The deciding regression is `efficiency-dev-000469-A`, a French booklet with an Italian claim about easier lease termination for personal need. Both labels are correct. Baseline supplies quotations on physical pages 8, 9 and 36: its page-8 quote is background, while pages 9 and 36 add useful support about easier establishment of personal need and the changed urgency criterion. Candidate keeps only that same page-8 background quotation and drops both useful passages. Its explanation still describes the changed condition, but its displayed evidence no longer supports those decisive facts.

The exact decisive summary paragraph is present in both saved assessment inputs. All baseline quotations also remain eligible under the candidate's body filter. This observed loss is therefore in citation selection/output; neither a reduced input budget nor prefix expansion removed those facts. Equal labels, exact quotation provenance and unchanged fuzzy overlap did not justify accepting weaker evidence. Both experimental query mode `source` and citation mode `prefix` remain disabled by default.

Two previously known regression requests were prepared for possible follow-up but were not run after the candidate failed the tuning gate. They are excluded from all prediction, transport and accuracy counts.

## Time, tokens and comparison limits

| Stage, nine cases | Baseline → candidate total time | Input tokens, each | Baseline → candidate output tokens |
| --- | ---: | ---: | ---: |
| Multilingual query generation | 95.641 → 96.249 s | 2,041 | 1,792 → 1,792 |
| Final assessment | 311.856 → 247.648 s | 35,203 | 2,356 → 1,108 |
| Work outside model transport | 19.259 → 20.143 s | — | — |

Model transport accounts for about 95.49% of baseline case time. The final assessment is the largest measured cost. All candidate output-token reduction occurs in that assessment; query-generation tokens are unchanged. Work outside transport combines extraction, retrieval, token planning and other local work; lexical search alone was not timed separately. These records do not separate model prefill from decoding time.

Four cases are faster with prefixes; five are slightly slower and generate unchanged output-token counts. The lease case contributes the largest saving while also losing substantive evidence. Baseline indexes were already cached for 5/9 cases; candidate indexes were cached for 9/9. Runtime prompt state may also be reused. These are single serial observations per case and variant, with model startup excluded, so the comparison does not isolate cache/order effects or establish timing variance.

## Evidence and quality limits

All six baseline quotations and all four candidate quotations were found verbatim on the stated physical PDF pages. Official evidence overlap is 0.50 for both variants: 2/4 non-neutral tuning cases and 1/2 non-neutral confirmation cases. Exact quotation checks, semantic support and fuzzy overlap measure different properties; unchanged scores did not detect the lease-evidence loss.

The retained baseline also has substantive shortcomings. In tuning case `efficiency-dev-001238-A`, both models receive complete passages explicitly denying new tasks or additional costs, describe that negation in their explanations, and incorrectly choose neutral instead of contradiction. This is a relation-selection error despite supplied decisive evidence. In `efficiency-dev-001098-A`, both labels correctly contradict the committee-trust claim, but both cite background about bodily integrity rather than the supplied committee-distrust statements. A correct label and exact quote can still form an inadequately supported answer. The tobacco-advertising answer has decisive evidence for its correct label but an unnecessary incorrect aside about the counterproposal in its explanation.

Confirmation introduces no additional label or citation regression, but preserves two baseline defects. In `efficiency-dev-001455-A`, both versions return neutral on a claim attributing a rejection recommendation to the Federal Council. Retrieval misses the strongest detailed climate-proposal passages, yet both supplied inputs still include the explicit Yes recommendation and a statement opposing the claimed fossil-fuel ban. The error therefore combines incomplete retrieval and misinterpretation of relevant supplied facts. In `efficiency-dev-000184-A`, both versions correctly classify the restaurant-service claim but quote neighboring examples beginning after the decisive restaurant sentence, despite receiving that complete sentence in their inputs. Official fuzzy overlap accepts the neighboring material. The emitted quotation is unchanged by prefix expansion and remains weaker than the source evidence available to the model.

Retrieval can miss facts, qualifications or counter-evidence. Neutrality is especially difficult to establish from selected passages, and OCR can introduce transcription errors. The UI exposes extraction and selected-coverage warnings. Nine requests demonstrate live exercise of all nine language pairs, not dependable quality for each pair. The candidate was fixed before selection, but all cases still come from public development dates, and related claims/proposals or translation families may overlap prior work. Training exposure is unknown. Report confirmation separately; the combined nine-case numbers are descriptive, not a private or general accuracy estimate.

## Trace integrity and provenance

Gold stays separate from inference inputs and is used only for stratified selection and explicit scoring/review. The runner verifies frozen input/PDF hashes and imported source/configuration identity between cases. `--trace-prompts` preserves each stage's exact public message content, original source passages and raw model JSON before local quotation expansion. A field allowlist excludes endpoint URLs, settings, transport headers and API keys; claim and booklet text is retained. Trace configuration participates in run identity, each trace file has a recorded hash, and resume rejects missing or changed diagnostics. Traces and all evaluation gold are excluded from final delivery.

Both frozen Python source packages and the unchanged active package have aggregate SHA-256 `0064cb2247b3ae06f72533063c0accbd9cac39c7a119898e84d278264805796e`. Baseline and candidate settings differ only in citation mode, `full` versus `prefix`; model, endpoint identity, runner and diagnostic configuration match. This package hash covers `src/claimlens/*.py`; separate manifests identify the runner, source snapshots, input assets and report artifacts.

The completed experiment is preserved under the workspace's `archive/track_2a/output/v7-final/`. These archival identifiers are excluded from the prediction image and final delivery.

| Record | Artifact relative to that archive directory |
| --- | --- |
| Predeclared protocol, dataset/prior-input/cohort hashes | `experiment-plan.json`, `selection.json` |
| Frozen requests, original PDFs, separate gold | `frozen/tuning/`, `frozen/confirmation/` |
| Source snapshots and file hashes | `baseline-source/`, `baseline-source.json`, `candidate-source/`, `candidate-source.json` |
| Baseline and candidate predictions, usage, identity and traces | `runs/{baseline,body-prefix-5000}/{tuning,confirmation}/` |
| Locked candidate and explicit rejection | `candidate-lock.json`, `promotion-decision.json` |
| Paired metrics, exact-input comparisons and combined official scores | `review/paired-complete/comparison.json`, `review/paired-complete/comparison.md`, `review/paired-complete/combined-official/` |
| Substantive evidence reviews | `review/tuning-evidence.md`, `review/confirmation-evidence.md` |
| Official scorer and its provenance | `official/evaluate.py`, `official/source.json` |
| Current local software/frontend logs | `verification/local-tests.log`, `verification/frontend-tests.log` |
| Current container software/interface checks | `verification/docker-tests.log`, `verification/submission-checks.log` |
| Model artifact verification and native shutdown | `verification/model-verification.log`, `verification/stopped-native-services.json` |
| Separate presentation rehearsal | `presentation/request.json`, `presentation/response.json`, `presentation/rehearsal.json` |

Dataset: `OSTswiss/MNLIoverSwissVotingBooklets`, revision `fc2b27600310778da6bbf445651ddbca22d86269`. Official evaluator SHA-256: `c96ad66334021aeb5636b113ed0f060ccfcbd2f0074c9fd37f1524f98290bd8b`. Relocated archives retain their measured absolute source paths. Copy the inputs and snapshots into a fresh experiment directory rather than changing manifests or resuming archived runs.

Final shutdown proof is preserved in `verification/final-shutdown.json`.

## Remaining validation

- Improve evidence selection and relation consistency without discarding decisive quotations; validate new changes on fresh paired cases with a separate confirmation cohort.
- Evaluate broader frozen Task A/B cohorts, retaining failures and reviewing neutral decisions and substantive support across all language pairs.
- Verify authenticated organizer-proxy access, available model IDs, context limits and usage reporting.

Use [evaluation.md](evaluation.md) for reproducible commands. The [technical report](../technical_report.md) presents the delivered method and limitations in the template format. The [two-minute video script](video-script.md) and [recording walkthrough](presentation-walkthrough.md) distinguish the live demonstration from benchmark evidence. Packaging checks and a prepared presentation do not establish organizer acceptance.
