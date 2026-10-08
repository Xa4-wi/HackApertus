# Technical report — ClaimLens v0.4

- **Track:** Track 2A — OST: Multilingual Natural Language Inference over Swiss Official Voting Booklets
- **Event:** Hack Apertus Online, 1–16 October 2026
- **Team / member:** OneLegedCoder - Xavier
- **Interfaces:** Official JSONL CLI; local browser application
- **Report date:** 8 October 2026
- **Status:** Software checks, development scoring and both final reference cohorts completed. The full-booklet rerun was intentionally stopped at the user's request for latency redesign after one of nine cases produced an accepted output; no Task A score is reported. The final image rebuild and PDF regeneration remain pending. Organizer-proxy access and the private benchmark have not been tested.

## 1. Summary

ClaimLens assesses whether a supplied Swiss voting booklet or reference supports a natural-language claim. It returns **0 entailment, 1 neutral, or 2 contradiction**, with exact evidence quotations, physical PDF page numbers and measured inference usage. German, French and Italian source/claim combinations are supported independently.

Version 0.4 accepts both the minimal presentation inputs and the annotated starter inputs, adds bounded recovery with honest token accounting, and introduces frozen public-data evaluation using the official scorer. The local model prompt and decoding schema were revised to address the previous tendency to treat missing evidence as contradiction. These changes require measured validation; they do not establish benchmark success by themselves. The browser and CLI use live Apertus inference. No stored-answer or demo mode remains.

## 2. Architecture and input/output contract

| Stage | Responsibility |
| --- | --- |
| CLI / local browser | Validate inputs; select the supplied reference or booklet |
| `booklets.py`, `ocr.py`, `library.py` | Preserve original PDFs, page text, source attribution and bounded OCR |
| `context.py`, `llm.py` | Plan context, select evidence when needed, call Apertus and account for usage |
| `engine.py`, `cli.py` | Validate whole-claim output and exact quotations; export the official schema |

The template's `track_2a/` structure is retained. A static HTML/CSS/JavaScript interface calls the Python server. Its searchable library, claim form and source-linked results require the configured local model. The independent CLI can use the organizer's remote endpoint and does not require the browser server.

The CLI accepts `--input` and `--output` UTF-8 JSONL files. Each request has a unique string ID, a claim object and exactly one `booklet` or `reference` object. Language fields may be omitted, as in the presentation; supplied codes must be `de`, `fr` or `it`. Missing metadata uses automatic multilingual handling without changing the source text. Reference cases may omit `vote`; booklet cases require it to identify the intended proposal. PDF paths must remain inside the mounted input directory. Missing source-language metadata enables all three OCR languages.

Each output contains `id`, `label`, matching `label_name`, `evidence: [{page, text}]`, and `metrics: {input_tokens, output_tokens, inference_time_ms}`. PDF evidence uses one-based physical pages, preserving blank-page positions; reference evidence uses a null page. Neutral exports contain no evidence. A single whole-claim assessment determines the label. Python preserves the exact submitted claim and constructs its full-span check rather than requiring the model to copy it. The exporter retains at most five evidence items. Exact quotation validation checks provenance, not semantic correctness.

Web imports accept uploaded PDFs or validated HTTPS Federal Chancellery PDF URLs. Content hashes preserve originals and deduplicate imports. Imports make no model call. Evaluation reads supplied files and performs no online booklet, dependency or model download. Poppler/Tesseract OCR targets pages with fewer than 40 non-whitespace characters, attempts at most 20 pages within 180 seconds, and retains warnings. OCR transcription is not independently verified against visual content.

### Context handling and recovery

Sources that fit are supplied in full. Larger sources are divided into contiguous segments covering every character. Apertus selects source-unit IDs from each segment; Python reconstructs exact excerpts; a final assessment reasons jointly over those excerpts. There is no vote over segment labels. Selection can still miss relevant facts despite examining every segment.

If selected evidence exceeds the final context, Apertus reconsiders every candidate in fitting windows and selects a smaller set of original source units, preserving their IDs and page provenance. This bounded reduction permits at most eight rounds within the same time and call budgets. It can omit relevant evidence; exact quotations do not eliminate that risk. Processing metadata records the rounds and initial/final selection counts. No-progress and fixed-capacity failures are not retried as whole-document analyses.

Local planning can use the runtime's chat-template/tokenizer APIs. Remote planning uses a conservative byte-based estimate and only calls the configured chat-completions API. Estimates never replace measured usage. Context overflow, invalid extraction and exhausted budgets fail explicitly rather than silently truncate source text.

Transport permits at most three attempts for recoverable HTTP or JSON failures within one request deadline and the remaining document call budget. A malformed verdict or citation can receive one additional assessment when prior usage is known. Failed attempts count toward tokens, time and call limits. Ambiguous network/server failures leave usage unknown; mandatory unknown metrics prevent official export rather than becoming estimates or zero usage. Explicitly rejected rate-limit requests count as zero unless the provider reports usage. Late responses are rejected while retaining known usage.

JSON syntax and duplicate IDs are checked before inference. A failed case is reported individually and does not stop later cases. Successful predictions are atomically checkpointed to `OUTPUT.partial.jsonl`. The requested output is replaced only when every case succeeds; otherwise the CLI exits nonzero and preserves any previous complete output. Partial files are recovery artifacts, not complete submissions. Infrastructure failures are never fabricated neutral predictions.

## 3. Model and runtime

The canonical selection is `swiss-ai/Apertus-v1.5-8B`; the 70B ID is also supported when available at the endpoint. Local measurements use the pinned community Q4_K_M text-backbone conversion, **5,059,027,136 bytes**, served by llama.cpp on an Apple M4 with 16 GiB RAM, Metal offload, one slot and a **16,384-token combined context**. This is an unofficial derivative, not the full original multimodal checkpoint. Artifact revision and verified SHA256 are in [local model provenance](docs/local-model.md).

Temperature is zero; final responses reserve up to 3,000 tokens and extraction responses up to 1,600. Local limits are 300 seconds per request, 1,800 seconds per case and 48 model calls, including retries. Context-only usage is null when unreported; source characters are measured separately. Case timing includes source preparation, inference and validation; PDF extraction is cached within a batch.

The revised prompt distinguishes an incompatible fact about the same entity/time/condition from an unmentioned or unrelated fact. Synthetic illustrations explain the classes without evaluation answers. The model returns a compact object with `explanation`, `relation` and `evidence`. Explanation comes first; the relation is exactly one of `supported`, `not_enough_information` or `refuted`. Python maps these to official labels **0, 1 and 2**, respectively, and constructs the exact whole-claim check. The model no longer generates copied claim text, dimensions or diagnostic subchecks. Local constrained decoding restricts quotation candidates to exact source spans; independent validation still requires evidence for non-neutral labels.

Remote proxies use JSON-object mode. If such a response supplies evidence as bare quote strings, the adapter binds a string only when it occurs verbatim in exactly one source passage. Ambiguous or invented quotations remain invalid, and supplied wrong passage IDs are never repaired. A local JSON-only protocol smoke test exercised this path successfully; the actual organizer proxy remains untested.

Injected `BASE_URL` and `API_KEY` override local settings and aliases. A local served-model alias applies only to allowlisted local hosts; remote requests use the canonical model ID. No additional remote model, external judge, fine-tuning, model browsing or shell tool is used. The CPU `linux/amd64` image includes Python and PDF/OCR dependencies; it excludes credentials, model weights, downloaded datasets and gold labels. Inference is supplied through the endpoint.

## 4. Data and evaluation method

The pinned [OST dataset](https://huggingface.co/datasets/OSTswiss/MNLIoverSwissVotingBooklets), revision `fc2b27600310778da6bbf445651ddbca22d86269`, contains **1,488 public training rows**: 495 entailment, 498 neutral and 495 contradiction. There are 1,153 unique requests and 335 duplicates, without conflicting duplicate labels. The cache includes all 60 distinct referenced PDFs—20 per language—with 3,408 physical pages and 22 pages of recovered OCR text across 10 documents. It is the dataset's collection, not the complete historical archive.

The v0.4 split was frozen before final inference, with seed `claimlens-v4-readiness-20261008`. It groups all languages and proposals from a ballot publication date together. The 14 dates exercised by earlier development cases or the known 3 March 2024 booklet smoke remain development-only; six other dates supply final cohorts. Identical requests are deduplicated. Final PDF cases exclude normalized same-language claims selected for the reference cohorts.

| Frozen cohort | Cases | Purpose |
| --- | --- | --- |
| Development B | 27 | One case per language pair and label; tuning permitted |
| Final B | 27 | One case per language pair and label from separate dates |
| Final B extension | 27 | Second preselected case per stratum; not a replacement chosen after scoring |
| Final A | 9 | One full-booklet case per language pair, three cases per label |

Gold labels are used only for stratified selection and scoring. The inference runner receives cases alone and uses the CLI's `predict_case` path. Input/PDF/gold hashes, dataset identity, model/settings/code identity and the unmodified official evaluator snapshot are recorded. Interrupted runs are retained; changed source identity requires fresh results. The official scorer measures label metrics and Task A evidence overlap; separate records retain failures, usage and wall-clock mean/p95. Evidence overlap does not validate page numbers or establish semantic correctness.

These are small **public-data local holdouts**, not the organizers' private benchmark. Pretraining exposure cannot be excluded. Final A and B remain correlated through shared dates despite excluding repeated claims. Task A retains upstream reference-task labels, following official preparation; a complete booklet can contain facts absent from the shorter reference. Local thresholds do not reproduce the organizer proxy's efficiency ranking.

## 5. Measurements and verification

| Check / cohort | Observed status |
| --- | --- |
| Current Python suite | **181 tests passed**; includes input compatibility, provenance, evidence reduction, retry accounting and budgets. Inference is stubbed in software tests. |
| Frontend | **Smoke harness passed**; verifies interface behavior, not model accuracy. |
| Submission container | **2 integration + 11 compatibility + 17 resilience checks passed**. The final image rebuild after the API quote-adapter change remains pending. |
| v0.4 development B, 27 cases | **25/27 correct (92.59%), macro-F1 0.9275; 27 accepted, zero failures**. Mean **17.83 s**, p95 **30.66 s**; **65,065 input / 3,303 output tokens**, all cases measured. |
| Local JSON-only API protocol | **Passed** one synthetic cross-language case: correct entailment, **514 input / 60 output tokens**, **3.15 s**. This is local protocol validation, not organizer access or a benchmark. |
| v0.4 final B, primary 27 | **26/27 correct (96.30%), macro-F1 0.9628; zero failures**. Mean **15.55 s**. |
| v0.4 final B, extension 27 | **24/27 correct (88.89%), macro-F1 0.8866; zero failures**. Mean **16.15 s**. |
| v0.4 final B, combined 54 | **50/54 correct (92.59%), macro-F1 0.9247; 54 accepted, zero failures**. Mean **15.85 s**, p95 **27.74 s**; **119,486 input / 7,069 output tokens**, all cases measured. |
| v0.4 final A, 9 PDF cases | **Intentionally stopped; incomplete and unscored.** One accepted output took **458.53 s**, **62,050 input / 661 output tokens**, **six calls** and **one reduction round**. The following case was interrupted with incomplete usage. |
| Organizer inference proxy | **Not tested**; requires organizer credentials |
| Organizer private benchmark | **Not available / not tested** |

The completed development run used the frozen development inputs and the unmodified official scorer. All nine neutral examples were classified correctly; one entailment and one contradiction were classified as neutral. Its score exceeds the local Task B threshold on the tuning cohort only and predates the final API quote-adapter change. Measurements are recorded in `output/v4-readiness/development/summary.json` and `local-api-protocol-smoke.json`.

Both final reference cohorts exceed the official scorer's 0.70 Task B threshold on these public-data cases. **All 18 neutral examples were correct**. Independent audits verified all 34 emitted quotations as exact matches to their references, with no interface or provenance issues; this does not prove semantic relevance. Combined macro-F1 was recomputed by the unmodified official scorer over all 54 predictions, not averaged from cohort F1 values. Both runs have identical code/model/runtime identity apart from their input hashes. `final-b-combined/` contains scoring-only concatenations, the exact combined score **0.9247219355578489**, timing/usage summaries and source-artifact hashes; the original cohorts remain unchanged.

Earlier v0.4 development runs and partial attempts were exploratory and informed prompt/schema revisions; their artifacts remain preserved. An initial final-B run was interrupted after four cases to address a separate synthetic JSON-only protocol issue. Neither final predictions nor final gold were read to choose that compatibility fix. The records and source remain under `final-b/interrupted-api-hardening/` and are excluded from final scores.

The first Task A attempt failed when selected evidence exceeded the final context. Its six calls consumed **75,230 input / 728 output tokens** over **321.84 seconds**, including a redundant full-analysis retry; a following in-flight case was interrupted with unknown usage. These records and the old source remain under `final-a/interrupted-context-overflow/`. No Task A gold was inspected to choose the capacity fix. A rerun began after bounded reduction and non-retryable capacity failures were added. Completed Task B measurements use the preceding source snapshot: the successful full-source inference path, prompt and schema are unchanged by this long-document fix.

The user intentionally stopped that Task A rerun to focus on latency after **one of nine cases produced an accepted output**. Its recorded elapsed time was **458,532.384 ms**, with **62,050 input / 661 output tokens**, **six model calls** and **one evidence-reduction round**. That output has not been scored for correctness. The following in-flight case was interrupted with incomplete usage. All original records are preserved. The nine-case cohort is incomplete, so neither Task A F1 nor overall evaluation readiness is established.

The historical V2 tuned 27-case reference run accepted all outputs and classified **18/27 correctly (66.67%; macro-F1 0.5556)**. All nine neutral cases were incorrectly classified as contradiction. It averaged 24.11 seconds per case and recorded 69,932 input / 6,742 output tokens. It used different development cases from the current run, so this comparison is not a paired measurement of the code change. The original report is preserved at `output/v4-readiness/technical-report-v2.md`, with results under `output/v2-evaluation/`.

A historical full-booklet smoke also mislabeled a changed-number German claim as entailment against the French March 2024 booklet, despite exact quotations passing validation. That response remains in `output/v2-smoke/`. It demonstrates why valid JSON, exact quotes and software checks are insufficient evidence of model quality.

Published macro-F1 targets are **0.70 for Task B** and **0.60 for Task A**. Pending results must not be interpreted as meeting either target. Final reporting must include every frozen case and failure, rather than only favorable examples. Token totals must identify cases whose complete usage was unavailable.

## 6. Reproduction, limitations and submission status

`make model-serve` starts the local model; `make dev` starts the live browser. `make test` and `make test-ui` run software checks. `make submission` builds the predictor; `make verify-submission` checks its isolated CLI contract. `make check-endpoint` exercises a synthetic language-free case through the real CLI, reporting connectivity/schema behavior separately from classification correctness. It is not an accuracy benchmark.

Frozen v0.4 inputs and provenance are under `output/v4-readiness/`. Run or score a cohort from `track_2a/` using `scripts/evaluate_readiness.py run|score --directory output/v4-readiness/COHORT`; scoring requires `requirements-evaluation.txt`. Resume only an unchanged run identity and keep gold outside prediction mounts. `make report` builds the current Markdown report as `output/pdf/claimlens-v4-report.pdf` and enforces the six-page limit; inspect every rendered page after final edits. Old `make evaluate` commands and the explicit `make report-v2` remain historical V2 workflows; their artifacts must not be relabeled as current measurements.

Limits are 2,000 claim characters, 300,000 inference source characters, and PDFs of 25 MB and 200 physical pages. OCR, column order, hyphenation, selection and semantic interpretation remain failure sources. A scanned body with a selectable header may escape the OCR heuristic. PDF parsing runs in-process before OCR bounds. The browser is a single-user local application without deployment authentication or scaling.

Before submission, complete pending measurements, verify the actual organizer endpoint and produce the final report within the six-page PDF limit. Software compatibility and local public-data performance do not certify acceptance or private-benchmark quality. No entry has been submitted.

At the user's requested stop, testing and evaluation were halted. The local model and UI were stopped, ports **8081** and **8000** had no listener, and the Colima VM was stopped. The final image rebuild and PDF regeneration remain pending. The existing V0.4 PDF is an earlier draft and has not been rebuilt after this status update.

## License and references

Code follows Apache-2.0; documentation uses CC-BY-4.0. Imported datasets and official booklets retain their licenses and attribution. Newly distributed generated datasets must follow the event's CDLA-Permissive-2.0 requirement and preserve third-party rights.

- [Project template](https://github.com/HackApertus/project-template) and [recorded event requirements](docs/event-requirements.md)
- [OST challenge](https://hackapertus.notion.site/3deb4fec112a80258fd2ddc61616011d) and [solution API](https://hackapertus.notion.site/solution-api-guide-ef5b4fec112a834da43101ede56300f5)
- [Official evaluator](https://gitlab.com/ifsoftware/hackapertus-starter), [OST dataset](https://huggingface.co/datasets/OSTswiss/MNLIoverSwissVotingBooklets) and [Federal Chancellery archive](https://www.bk.admin.ch/de/sammlung-der-abstimmungsbuechlein-seit-1978)
