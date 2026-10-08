# Technical report — ClaimLens v0.5

- **Track:** Track 2A — OST: Multilingual Natural Language Inference over Swiss Official Voting Booklets
- **Event:** Hack Apertus Online, 1–16 October 2026
- **Team / member:** OneLegedCoder - Xavier
- **Interfaces:** Official JSONL CLI; local browser application
- **Report date:** 8 October 2026
- **Status:** Fast booklet retrieval with contextual quotations implemented; 233 software tests, frontend checks and 233 isolated container tests passed for this implementation. Final checks after restoring the selected version remain pending. The three-case development experiment and separate same-case timing comparison are complete. No Task A readiness or private-benchmark result is claimed.

## 1. Purpose and current change

ClaimLens compares a natural-language claim with a supplied Swiss voting booklet or reference and returns **0 entailment, 1 neutral, or 2 contradiction**. Source and claim languages independently support German, French and Italian. Results include original-language quotations, physical PDF pages and measured inference usage. The application always uses live Apertus; no stored-answer or demo mode remains.

Version 0.5 addresses full-booklet latency by selecting a small set of original-source passages before the final assessment. A separate run of the same previously slow case took **56.11 seconds and 4,363 input tokens**, compared with **458.53 seconds and 62,050 input tokens** under the earlier exhaustive pipeline. This is a one-case operational comparison, unscored for correctness, and includes runtime/cache changes. Its nine-case quality evaluation remains incomplete.

Retrieval trades full model coverage for lower input volume. **Apertus does not read every booklet page in this mode.** Relevant qualifications or counter-evidence may be missed. The UI labels results **Selected passages**, shows the coverage warning and distinguishes selected pages from total source pages. Task B reference inputs continue through the existing full-reference pipeline.

## 2. Architecture and evidence provenance

| Component | Responsibility |
| --- | --- |
| `cli.py`, `server.py`, `static/` | Official batch input/output; local UI, progress, evidence and usage |
| `booklets.py`, `ocr.py`, `library.py` | Preserve original PDFs, physical pages, source metadata and bounded local OCR |
| `retrieval.py` | Cache a lexical index and rank exact source spans with neighboring context |
| `fast.py`, `context.py`, `llm.py` | Enforce budgets, expand multilingual search queries and call Apertus |
| `engine.py`, `cli.py` | Validate the whole-claim assessment and source quotations; export official predictions |

The project retains the template's `track_2a/` structure. Its static HTML/CSS/JavaScript browser calls the local Python server. The submission CLI does not require that server and can use the organizer's injected remote endpoint.

For short booklet text that fits the fast prompt budget, Apertus receives the complete supplied source in one assessment. For larger booklets, one Apertus call creates brief German, French and Italian claim/proposal search phrases. Those phrases guide local retrieval; they never replace the original claim or become evidence. A lexical index combines BM25 word ranking, character trigrams, a soft proposal-page boost and neighboring source spans. It returns at most 12 candidate units. Original source text and page offsets are independently checked before selected units are packed into the final prompt.

The final Apertus call jointly assesses the selected excerpts. Python maps `supported`, `not_enough_information` and `refuted` to labels 0, 1 and 2 and preserves the exact submitted claim. Missing facts are not automatically contradictions. Non-neutral exported predictions require exact evidence quotations. Invalid structure, invented citations, no retrieval matches or evidence that cannot fit cause explicit failures; none are converted into neutral predictions or an automatic exhaustive fallback.

Retrieved evidence uses contextual body spans rather than isolated footer or sentence fragments. Local constrained decoding offers exact spans of up to 900 characters, merging a short contiguous tail where the combined span remains within 1,200 characters. For ordinary JSON responses, Python may expand a unique exact anchor within its supplied passage to a containing original-text span. It never crosses an omission marker, invents wording, guesses a repeated anchor or repairs a wrong source ID. Expansion is reported and never changes the predicted label. The reference-task quotation path is unchanged.

Indexes contain source statistics, not labels, verdicts or generated answers. Keys include all source text, provenance metadata and the algorithm version. Source units are rebuilt from current passages even on a cache hit. Disk entries have size and checksum checks; writes are atomic. An unavailable cache triggers local recomputation. Every final verdict still calls Apertus.

An explicit `DOCUMENT_STRATEGY=exhaustive` option retains the earlier segment-selection/reduction pipeline. It examines each source segment with the model before joint assessment, although evidence selection can still omit relevant facts. Its measurements must be distinguished from retrieval results.

## 3. Contract, runtime and accounting

The CLI reads UTF-8 JSONL through `--input` and writes through `--output`. Requests contain a unique string `id`, a `claim` object and exactly one `booklet` or `reference`. Language metadata is optional as in the presentation; supplied values must be `de`, `fr` or `it`. Reference cases may omit `vote`; booklet cases require the proposal name. PDF paths remain inside the mounted input directory. Evaluation downloads no model weights, dependencies or booklet files.

Each accepted response contains `id`, integer `label`, matching `label_name`, `evidence: [{page, text}]` and `metrics: {input_tokens, output_tokens, inference_time_ms}`. Up to five quotations are exported. Booklet citations use one-based physical PDF pages; reference citations use `null`. Neutral predictions export no evidence. Exact text provenance does not establish semantic correctness or correct attribution.

`DOCUMENT_STRATEGY=retrieval` is the default for booklets. `RETRIEVAL_PROMPT_TOKENS=5000` limits the final prompt, subject to the serving context and a reserved output budget. It is not a cap on aggregate tokens across query expansion, final assessment and retries. `RETRIEVAL_TIMEOUT_SECONDS=120` and a maximum of four transport attempts bound the fast pipeline. Query expansion reserves 384 output tokens; final assessment reserves 3,000. Fast booklet cases are not repeated as whole analyses after invalid output. Every attempt shares the remaining case deadline.

CLI timing includes source preparation, model calls and validation. PDF/OCR preparation receives the remaining deadline; checks around parser/page operations are cooperative and cannot forcibly preempt a single blocking parser operation. OCR and column-order errors remain possible. Token planning uses the configured local tokenizer when needed, or conservative UTF-8 byte estimates for remote endpoints. Estimates never replace provider-reported usage. Ambiguous transport failures retain unknown usage; missing mandatory totals prevent official export. Diagnostic records retain known partial usage when available.

Malformed JSON and duplicate IDs are rejected before inference. A case failure does not stop later cases. Valid predictions are atomically checkpointed to `OUTPUT.partial.jsonl`; the requested output is replaced only when every case succeeds. A partial file is a recovery artifact, not a complete submission.

The canonical model is `swiss-ai/Apertus-v1.5-8B`; the 70B ID is supported when the endpoint provides it. Local measurements use a pinned community Q4_K_M text-backbone derivative served by llama.cpp on an Apple M4 with 16 GiB RAM, Metal offload, one slot and a 16,384-token combined context. The serving script now limits its host prompt cache to **1,024 MiB**. This cache is separate from the local lexical index and does not cache ClaimLens verdicts. The weights are an unofficial derivative, not the original multimodal checkpoint; size, revision and verified hash are recorded in [model provenance](docs/local-model.md).

Injected `BASE_URL` and `API_KEY` override local aliases and settings. Remote requests use the canonical model identifier and JSON-object mode; local constrained decoding can restrict evidence to exact source spans. Generic JSON-object retrieval compatibility remains under verification; the local measurements use the configured local decoding path. Only unambiguous exact quote strings may be bound to source IDs; wrong supplied IDs and invented text remain invalid. The CPU `linux/amd64` submission image includes extraction/OCR dependencies and excludes model weights, credentials, downloaded datasets and gold labels. No additional remote model, external judge or fine-tuning is used.

## 4. Data, experiment and recorded results

The cached [OST dataset](https://huggingface.co/datasets/OSTswiss/MNLIoverSwissVotingBooklets), revision `fc2b27600310778da6bbf445651ddbca22d86269`, contains **1,488 public training rows**, comprising 495 entailment, 498 neutral and 495 contradiction examples. There are 1,153 unique requests and 335 duplicates without conflicting duplicate labels. The local library contains its 60 referenced PDFs, 20 per language; it is not the complete historical voting archive.

The v0.5 latency experiment froze **three development-only Task A cases** before inference, using previously exercised ballot dates and excluding previously evaluated exact development requests. Source-to-claim pairs are **German→French, French→Italian and Italian→German**, with one selected label per pair and one example of each label overall. The original PDFs contain 32, 72 and 40 pages. Gold and reference passages are separated from inference inputs. This is a small latency experiment, not a held-out accuracy benchmark; none of the nine final Task A cases or 54 final Task B cases belongs to it.

`scripts/evaluate_fast.py` refuses broader cohorts and caps each case at 120 seconds with a final prompt budget of at most 5,000 tokens. Its shared runner uses the production `predict_case` path and records every failure, model call, available token total and elapsed duration. The same three development inputs were repeated while improving evidence presentation; this is development tuning, not independent validation. Input/PDF/gold hashes, dataset identity, source/model/settings identity and the unmodified official evaluator are retained with each run. The selected contextual-quotation run is `output/v5-latency-context/`, source hash `e02519ffb5272a8de498ccf4798e82efd14296e6832fce97c49fbcb4ece36031`.

| Check / cohort | Recorded observation |
| --- | --- |
| Selected implementation checks | **233 Python tests passed; frontend smoke passed.** Inference is stubbed in software tests. Final confirmation after restoring this version remains pending. |
| v0.5 three-case contextual-quotation run | **3/3 correct and accepted; zero failures; macro-F1 1.0.** Mean **54.97 s**, maximum **70.63 s**; **12,819 input / 1,632 output tokens** in total, complete usage for all three cases. These repeatedly used development cases do not establish general accuracy. |
| v0.5 evidence checks | Official gold-passage overlap **0.50 (1/2 non-neutral cases)**. Independent audit verified **three exact quotations on their physical PDF pages**, with zero output/provenance issues. Manual review found substantive support for both non-neutral decisions. |
| v0.5 submission container | **233 tests passed** in the CPU `linux/amd64` image with read-only filesystem, network disabled and writable temporary storage. Final verification after restoring this version remains pending. |
| v0.4 Task B, primary 27 | **26/27 correct (96.30%), macro-F1 0.9628; zero failures**, mean **15.55 s**. Historical measurement; not rerun for v0.5. |
| v0.4 Task B, extension 27 | **24/27 correct (88.89%), macro-F1 0.8866; zero failures**, mean **16.15 s**. Historical measurement; not rerun for v0.5. |
| v0.4 Task B, combined 54 | **50/54 correct (92.59%), macro-F1 0.9247219355578489; 54 accepted, zero failures**. Mean **15.85 s**, p95 **27.74 s**; **119,486 input / 7,069 output tokens**. |
| v0.4 exhaustive Task A rerun | **Stopped after one of nine cases produced an accepted output; unscored.** That case took **458,532.384 ms**, **62,050 input / 661 output tokens**, six calls and one reduction round. The following case was interrupted with incomplete usage. |
| Organizer endpoint / private benchmark | **Not tested / not available.** |

Each selected-run case used **two model calls**, with mean usage of **4,273 input / 544 output tokens**. Individual times were **70.63, 38.68 and 55.60 seconds**. Each run parsed the original PDF again and reused its local retrieval index from an earlier iteration; no gold or verdict cache exists. The recorded nearest-rank p95 is **70.63 seconds**, simply the maximum of three observations, not a population latency estimate. Results are in `output/v5-latency-context/summary.json`, `results.jsonl` and `evidence-audit.json`.

The separate **same-case timing comparison** completed in **56,112.593 ms**, with **4,363 input / 526 output tokens**, two model calls, 12 selected units and a warm retrieval index. The earlier exhaustive observation was **458,532.384 ms**, **62,050 input / 661 output tokens** and six calls: an observed **8.17× speedup and 92.97% reduction in input tokens** for this case. Both used the same Apertus Q4 weights, M4 hardware and 16K serving context. The old server used an 8,192 MiB default prompt-cache allowance; the current server uses 1,024 MiB, and cache state differs. The experiment does not isolate algorithmic causes or establish general speedup. It received no gold-based score and is excluded from the three-case accuracy result. Records are preserved in `output/v5-latency-context/same-case-comparison/`.

Manual evidence review distinguishes substantive support from the **0.50 official overlap score**. The AHV quote on page 15 attributes the position to the initiative committee, gives reserves of nearly 50 billion francs and says the financial means are available; this supports the attributed French claim. Its extra page-9 quotation is unnecessary background. The decisive page-15 quote scores **87.70**, below the evaluator's fuzzy threshold of 90, with surrounding attribution and headings affecting the alignment. The biodiversity quote on page 11 demands more funds and describes additional annual costs above 400 million francs. That contradicts the German claim's lower-spending assertion, enough to refute its conjunction; the quote does not separately establish the clause about easier interventions. It scores **99.53** for gold overlap. The neutral retirement-age claim is unrelated to the tenancy proposal; retrieval cannot prove that no relevant fact exists elsewhere. The source-hashed review is saved in `output/v5-latency-context/verification/citation-review.md`. These few reviewed outputs do not establish general retrieval recall or Task A readiness.

The initial v0.5 run (`output/v5-latency/`) returned 3/3 correct labels at a 39.15-second mean, but its footer-only AHV quotation and truncated biodiversity fragment did not substantiate the decisions. Exact-page and fuzzy checks did not expose that weakness. Contextual spans improved evidence at additional generation cost. A later citation-ID optimization (`output/v5-fast-final/`) reduced quotation copying but regressed to **2/3 correct, macro-F1 0.5556** on the same cases; it was rejected and is not shipped. All iterations are preserved and counted as development tuning.

The preserved v0.4 reference cohorts were grouped by ballot date away from development cases. All 18 neutral examples were correct, and independent audits verified all 34 returned quotations against their references. Combined F1 was recomputed over all 54 predictions, not averaged from cohort F1 values. These are public-data local results, not private-benchmark results. The full-reference prompt and decision path are retained in v0.5, but those 54 measurements keep their original source/runtime identities and have not been remeasured.

The official scorer requires macro-F1 of **0.70 for Task B** and **0.60 for Task A**. Its Task A evidence score checks fuzzy overlap with gold passages. A separate offline auditor checks exact text and physical page numbers against original PDFs; OCR-only quotes can remain unverified. Neither method proves the model's reasoning. Missing/failed predictions remain in score denominators. Token/time ranking requires the official run and other teams' results.

Historical development runs, interrupted attempts and the stopped v0.4 report are preserved. They include neutral-class failures and a wrong whole-booklet verdict despite an exact quotation. Details remain in [evaluation documentation](docs/evaluation.md) and `output/v4-readiness/technical-report-v4-stopped.md`; no unsuccessful run has been relabeled as a completed benchmark.

## 5. Reproduction, limits and submission status

Use `make model-serve` and `make dev` for the live local UI. Use `make test`, `make test-ui`, `make submission` and `make verify-submission` for software/container checks. With the prepared three-case inputs, run `scripts/evaluate_fast.py run`, then `scripts/evaluate_fast.py score` from `track_2a/`; scoring requires `requirements-evaluation.txt`. The run command never reads gold. Preserve failed cases and previous source identities; do not resume changed code/model/settings into an earlier run.

Use `scripts/audit_evidence.py` with the input and exported prediction files to check citation provenance. `make check-endpoint` provides a synthetic protocol check when organizer credentials become available. `make report` renders this Markdown with a six-page limit; inspect every rendered page after the last content update. The existing PDF is an earlier draft and must be regenerated before submission.

Limits include 2,000 claim characters, 300,000 inference source characters, and PDFs of 25 MB and 200 physical pages. Multilingual lexical retrieval depends on generated search terms; relevant passages can rank below unrelated material, and a retrieved neutral verdict may omit evidence elsewhere in the booklet. OCR, hyphenation, table extraction and ambiguous speaker attribution remain failure sources. The browser is a single-user local application without deployment authentication or scaling.

The three-case experiment cannot establish retrieval recall, all-nine-language-pair quality or general Task A accuracy. No Task A readiness claim follows from the historical Task B score. Before submission, review retrieval/evidence errors on a broader authorized evaluation, verify the final container and organizer endpoint, and regenerate the reviewed report. No entry has been submitted.

## License and references

Code follows Apache-2.0; documentation uses CC-BY-4.0. Imported datasets and official booklets retain their licenses and attribution. Newly distributed generated datasets must follow the event's CDLA-Permissive-2.0 requirement and preserve third-party rights.

- [Project template](https://github.com/HackApertus/project-template) and [recorded event requirements](docs/event-requirements.md)
- [OST challenge](https://hackapertus.notion.site/3deb4fec112a80258fd2ddc61616011d) and [solution API](https://hackapertus.notion.site/solution-api-guide-ef5b4fec112a834da43101ede56300f5)
- [Official evaluator](https://gitlab.com/ifsoftware/hackapertus-starter), [OST dataset](https://huggingface.co/datasets/OSTswiss/MNLIoverSwissVotingBooklets) and [Federal Chancellery archive](https://www.bk.admin.ch/de/sammlung-der-abstimmungsbuechlein-seit-1978)
