# Technical report — ClaimLens

- **Track:** Track 2A — OST: Multilingual Natural Language Inference over Swiss Official Voting Booklets
- **Event:** Hack Apertus Online, 1–16 October 2026
- **Team:** OneLegedCoder — Xavier
- **Demo:** Local browser application; launch instructions in [README.md](README.md)
- **Report date:** 8 October 2026

## 1. Summary

ClaimLens checks a natural-language claim against a Swiss voting booklet or supplied reference, returning **0 entailment, 1 neutral or 2 contradiction**, with original-source evidence, physical PDF pages, token usage and inference time. It accepts all German, French and Italian source–claim combinations. Apertus expands multilingual search terms, a cached lexical index selects passages, and Apertus assesses the original claim against those excerpts. The retained configuration classified **7/9 new public development cases correctly**, with macro-F1 **0.750000** and mean time **47.42 seconds**. A shorter-output experiment preserved all nine classifications but dropped useful evidence from one answer and was rejected for default use. These small measurements establish working live inference and remaining errors, not private-benchmark readiness.

## 2. Architecture

The Python application follows the template's `track_2a/` structure. Its official JSONL CLI and optional local browser share the same prediction engine. The browser uses the locally configured Apertus server; the CLI also supports the organizer's injected inference endpoint.

| Component | Responsibility |
| --- | --- |
| `cli.py`, `server.py`, `static/` | Batch interface, local UI, evidence display and usage reporting |
| `booklets.py`, `ocr.py`, `library.py` | PDF extraction, bounded OCR, metadata and physical page positions |
| `retrieval.py` | Cached BM25 and character-trigram ranking of exact source spans |
| `fast.py`, `context.py`, `llm.py` | Prompt planning, multilingual queries, inference and shared budgets |
| `engine.py` | Whole-claim assessment, classification mapping and quotation validation |

Short booklet text that fits the final prompt budget goes directly to Apertus in one call. For longer booklets, one Apertus call generates German, French and Italian claim/proposal search phrases. Local retrieval combines lexical ranking, proposal terms and neighboring context, selecting at most 12 candidate units. Source IDs, exact text and page offsets are checked before prompt assembly. One final Apertus call assesses the unchanged claim against those original excerpts. Generated search terms never become evidence.

The index caches source statistics, never labels or predictions. Keys include current text, provenance and the indexing algorithm; returned units are reconstructed from current passages even on cache hits. Every verdict uses live Apertus. The UI displays selected pages and warns that unselected pages have not been examined by the model. Task B reference inputs use only their supplied reference, with full-reference processing. An explicit exhaustive booklet mode remains available for comparisons.

Accepted CLI output contains `id`, integer `label`, matching `label_name`, up to five `evidence: [{page, text}]` items, and `metrics: {input_tokens, output_tokens, inference_time_ms}`. Booklets use one-based physical PDF pages; reference citations use `null`. Neutral predictions have no exported evidence. Non-neutral predictions require exact quotations. Retrieved quotations retain surrounding body text, usually up to 900 characters; a small contiguous tail may be merged up to 1,200 characters. Ordinary JSON responses may have a unique exact anchor expanded to its containing supplied context, with that expansion disclosed. Expansion never crosses omitted text or changes the verdict.

Invalid output, invented citations and exhausted budgets fail explicitly. The batch runner continues with later cases and checkpoints accepted predictions atomically, but replaces the requested final output only when every case succeeds. Failed inference is never exported as neutral. See the [interface contract](docs/solution-api.md).

## 3. Use of Apertus

- **Model:** `swiss-ai/Apertus-v1.5-8B`; the official 70B identifier is also configurable when an endpoint serves it.
- **How it is used:** Inference for multilingual query expansion and source-relative classification; no fine-tuning, external judge or additional remote model.
- **Where it runs:** Local llama.cpp with Apple Metal for recorded measurements; an OpenAI-compatible organizer endpoint for the submission interface.

Local measurements use an unofficial **Q4_K_M quantization of the Apertus 1.5 text backbone**, not the original multimodal checkpoint. The pinned artifact is `Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF`, revision `248ec68a63e219e3f061e4c946fc8a20d63b9975`, size 5,059,027,136 bytes. SHA256:

`a037df8d87ff6caacee794ee85f55342f2152e0d359b7389033300c3bee5f299`

Prompts distinguish missing information from explicit contradiction about the same entity, time and condition. Apertus returns an explanation, a source relation and quotations. Python maps `supported`, `not_enough_information` and `refuted` to 0, 1 and 2. Local constrained decoding restricts JSON structure and permitted quotations; independent validation still checks the result. Generic endpoints use JSON-object mode and the canonical model ID. Injected `BASE_URL` and `API_KEY` override local settings; every remote inference call uses that endpoint.

The default booklet strategy is `retrieval`, with a 5,000-token final prompt budget, 384 reserved query-output tokens and 3,000 reserved final-output tokens. These are limits, not measured consumption. The fast pipeline shares a 120-second deadline and at most four transport attempts. It does not automatically repeat the whole analysis or fall back to exhaustive processing. Provider-reported usage is aggregated across model calls and retries; planning estimates never replace actual usage. Unknown mandatory usage prevents official export. Context-only tokens remain unavailable when the provider does not report them separately.

Production defaults retain multilingual queries and full native quotations: `RETRIEVAL_QUERY_MODE=multilingual`, `RETRIEVAL_CITATION_MODE=full`, `RETRIEVAL_PROMPT_TOKENS=5000`. Optional source-language queries and exact-prefix citations remain experimental and disabled by default. Native prefixes can reduce generated text while Python restores complete contextual quotations, but neither exact expansion nor a minimum citation length guarantees relevance or correct interpretation.

## 4. Data

The public [OSTswiss/MNLIoverSwissVotingBooklets](https://huggingface.co/datasets/OSTswiss/MNLIoverSwissVotingBooklets) snapshot is pinned to revision `fc2b27600310778da6bbf445651ddbca22d86269`. It contains **1,488 training rows**: 495 entailment, 498 neutral and 495 contradiction, covering all nine language pairs. Deduplication identifies 1,153 unique requests and 335 duplicate rows without conflicting labels. Its dataset card declares MIT; imported content retains source rights and attribution.

The local library holds the dataset's 60 referenced Federal Chancellery PDFs, 20 per language, rather than the complete historical voting archive. PDFs, weights, labeled dataset caches and secrets are excluded from the submission image. Only prepared input JSONL and referenced PDFs belong in the evaluation input mount. Gold labels and scoring references stay outside inference inputs. No new human-subject data was collected.

The new measured cohort contains nine full-booklet requests: one per language pair and three per label. Six requests support tuning; three separate requests were opened only after a candidate was locked. Inputs, gold and PDFs were frozen before inference, using development ballot dates and excluding reserved final-cohort dates. Previously exercised exact requests, including the prior tuning and confirmation cases, were excluded. This does not exclude all related or translated claim families or model pretraining exposure. The nine-case aggregate combines tuning and confirmation; it is not an independent accuracy benchmark.

## 5. Evaluation

The production CLI prediction path was evaluated with the unmodified official scorer. Macro-F1 and accuracy assess classification; the Task A evidence metric checks fuzzy overlap with gold passages. A separate auditor freshly extracts PDFs to check exact text and physical page numbers. Manual review checks whether quotations substantively support the decision. These checks measure different properties.

The retained baseline uses multilingual queries, full quotations and a 5,000-token final prompt limit. A fixed candidate changed only native citation output to exact prefixes, with the existing structural filter excluding short candidates when longer body passages are available. Both source snapshots and this comparison were fixed before selecting six tuning and three confirmation cases. The candidate was rejected on tuning evidence quality; its later locked confirmation run completed the planned comparison and could not reverse that failure.

| Measurement | Retained baseline | Rejected prefix candidate |
| --- | ---: | ---: |
| Six tuning cases | 5/6 correct; F1 0.822222 | 5/6 correct; F1 0.822222 |
| Three confirmation cases | 2/3 correct; F1 0.555556 | 2/3 correct; F1 0.555556 |
| All nine: classification | 7/9; F1 0.750000 | 7/9; F1 0.750000 |
| All nine: accepted / failed | 9 / 0 | 9 / 0 |
| Mean end-to-end case time | 47.42 s | 40.45 s |
| Total input / output tokens | 37,244 / 4,148 | 37,244 / 2,900 |
| Official evidence overlap | 3/6 non-neutral gold cases | 3/6 non-neutral gold cases |
| Exact physical-page audit | 6/6 quotations verified | 4/4 quotations verified |

All 18 predictions completed with full usage reporting across 36 model transport calls. Macro-F1 was recomputed from all nine predictions, not averaged across cohorts. Saved traces establish identical query responses, assessment messages and complete source-passage arrays in all nine pairs. All nine classifications match. The candidate reduced measured mean time by **14.70%** and generated output by **30.09%**, with no input-token reduction.

Those aggregate scores conceal a substantive evidence regression. For the French-booklet/Italian-claim lease-termination case, baseline quotations include easier termination and the change from urgency to importance/currentness. The candidate keeps only the first background quotation and drops both useful supporting passages. The decisive summary paragraph was present in both model inputs. This is evidence-selection loss rather than missing retrieval, and the unchanged official overlap score did not detect it. **Full quotations remain the production default; the measured experimental speedup does not apply to normal application use.**

Both versions also make a cash-initiative classification error despite receiving text that explicitly says there are no new tasks or additional costs. A correct bodily-integrity verdict cites consent background rather than the committee's decisive statement, which was also supplied. Exact provenance, quote length and matching labels do not establish sound reasoning or adequate evidence.

Baseline model transport accounts for about 95.49% of case time: 95.64 seconds in multilingual query generation and 311.86 seconds in assessment across nine cases; all other work totals 19.26 seconds. The experiment does not separately time prefill and decoding. Timings include source preparation and validation but exclude loading the model. Inference was serial; cache state, thermal state and system load were uncontrolled. Baseline lexical indexes were warm in 5/9 cases; candidate indexes were warm in all nine. Five neutral predictions generated identical output counts and were slightly slower with the candidate. These are single observations, not a causal speed estimate or deployment latency guarantee.

**308 local software tests passed.** Frontend DOM simulations passed; these do not constitute browser visual review or measure model accuracy. Previously recorded container verification results are identified separately in [validation.md](docs/validation.md). The authenticated organizer endpoint and private benchmark remain untested.

## 6. Limitations

The model does not read every booklet page in retrieval mode. Query generation and lexical ranking can omit qualifications, counter-evidence or facts spread across pages. Neutral decisions are particularly vulnerable to missed evidence. One request per language pair cannot establish language-pair quality, retrieval recall or the private Task A threshold. The measured reference-task cohorts have not been rerun on this delivery.

OCR, hyphenation, column order, tables and ambiguous speaker attribution remain failure sources. Exact quotes and constrained JSON do not guarantee correct classification. The unofficial local quantization may differ from the organizer's model. Generic JSON was tested locally without authenticated organizer access.

Limits include 2,000 claim characters, 300,000 source characters per analysis, 25 MB per PDF and 200 physical pages. PDF deadlines are checked cooperatively between parsing operations; one blocking parser operation cannot be forcibly preempted. The browser is a single-user local application without deployment authentication or scaling. No private-benchmark result, official acceptance or completed submission is claimed.

## 7. Reproducibility

Recorded inference ran on an **Apple M4 with 16 GiB RAM**, native llama.cpp Metal build 11429 (`d81235049`), one slot, a 16,384-token combined context, temperature zero and reasoning disabled. The launcher sets `LOCAL_MODEL_CACHE_MB=1024`. [Local-model instructions](docs/local-model.md) install and verify the pinned weights. The local artifact's hash was verified after inference; a provider alias alone does not attest loaded weights or runtime behavior.

The fixed comparison uses identical baseline and candidate Python source snapshots, differing only in explicit citation-mode settings. The active prediction package is unchanged from this measured source. Its digest, computed from the sorted JSON map of relative Python paths to file SHA-256 hashes, is:

`0064cb2247b3ae06f72533063c0accbd9cac39c7a119898e84d278264805796e`

Selection used seed `claimlens-v7-full-context-20261008`. The workspace archive at `archive/track_2a/output/v7-final/` preserves the predeclared plan, frozen inputs, separate gold, PDF/evaluator hashes, both source snapshots, candidate lock, complete prompt/response traces, stage usage, decisions and semantic reviews. Both confirmation inference runs finished before either was scored or manually reviewed. Inference reads no gold. Opt-in traces contain public prompt/source text and raw model JSON; transport credentials and endpoint settings are excluded. Trace hashes are checked on resume. The final Markdown report and PDF sit directly inside `track_2a/`; build provenance and visual-review records are kept in ignored `output/report/`. Temperature zero does not guarantee bitwise deterministic GPU inference.

Install `requirements.txt` for the runtime, or `requirements-dev.txt` for runtime plus dataset, evaluation and report tools, from `track_2a/`. Dependency versions are pinned. From repository root, `make run` builds and launches the Docker application. For native development, use `make model-serve` and `make dev` in separate terminals. For the official CLI, configure the endpoint and run `make submission`, then supply `--input` and `--output` with read-only inputs and a writable output mount. Dependencies are installed at image build time; inference downloads neither dependencies nor weights. The [README](README.md) and [solution API guide](docs/solution-api.md) provide exact commands.

Use `make test`, `make test-ui` and `make verify-submission` for software checks. The [evaluation guide](docs/evaluation.md) describes preparing, running, scoring and independently auditing a fresh cohort. Gold is read during selection/scoring only. Changed code, model, settings or inputs require a new run directory; recorded identities prevent mixed resumes. `make check-endpoint` sends a real synthetic protocol request. `make report` renders this document to `track_2a/technical_report.pdf`, beside its Markdown source, with a six-page limit. The source/PDF hash manifest is written to `track_2a/output/report/`; archived experiments and local caches are excluded from delivery.

## 8. Next steps

Further development after submission would focus on four priorities:

- **Broader reliability evaluation:** Build a larger evaluation set covering all nine language pairs, separating ballot dates and related claim families between development and testing. Review classification, evidence relevance and neutral decisions, keeping an untouched test set for comparing improvements.
- **Stronger evidence retrieval:** Evaluate multilingual semantic retrieval and reranking alongside the existing lexical search. Improve OCR and table extraction, and retain speaker attribution, exceptions and context across pages so the cited passages substantiate the complete claim.
- **Lower latency without weaker evidence:** Profile model loading, prompt processing and output generation separately. Measure and improve reuse of existing parsed-document and retrieval caches, and compare model and quantization options. Adopt optimizations only when paired evaluations show no regression in classification and substantive evidence quality.
- **A more useful booklet library:** Add regular synchronization with newly published official booklets, retaining source URLs, document hashes and publication metadata. Improve navigation and quotation highlighting in the original PDFs so users can verify results more easily.

## License

Documentation is **Creative Commons Attribution 4.0 (CC-BY-4.0)**. Source code uses **Apache-2.0**, following the event's source-code terms. The OST dataset declares MIT; model derivatives and official documents retain their respective licenses, notices and attribution. Local third-party caches are not redistributed in the submission image.

## References

- [HackApertus project template, pinned revision](https://github.com/HackApertus/project-template/tree/7f2382275461baf3fa6c8855d157d86abffe9f0e)
- [OST challenge](https://hackapertus.notion.site/3deb4fec112a80258fd2ddc61616011d) and [solution API](https://hackapertus.notion.site/solution-api-guide-ef5b4fec112a834da43101ede56300f5)
- [Official evaluator](https://gitlab.com/ifsoftware/hackapertus-starter), [OST dataset](https://huggingface.co/datasets/OSTswiss/MNLIoverSwissVotingBooklets) and [Federal Chancellery booklets](https://www.bk.admin.ch/de/sammlung-der-abstimmungsbuechlein-seit-1978)
- [Official Apertus model](https://huggingface.co/swiss-ai/Apertus-v1.5-8B), [text conversion](https://huggingface.co/andreasmartin/apertus-v1.5-8b-text) and [pinned GGUF](https://huggingface.co/Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF/tree/248ec68a63e219e3f061e4c946fc8a20d63b9975)
- [llama.cpp](https://github.com/ggml-org/llama.cpp) and [recorded event requirements](docs/event-requirements.md)
