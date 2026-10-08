# OST solution API contract

Verified on **8 October 2026**. Source of truth: [official solution API guide](https://hackapertus.notion.site/solution-api-guide-ef5b4fec112a834da43101ede56300f5). The [optional OST starter](https://gitlab.com/ifsoftware/hackapertus-starter) demonstrates the contract with random predictions; its output is not a working model baseline.

## Invocation

The Docker entrypoint must accept:

```text
<entrypoint> --input /data/cases.jsonl --output /output/predictions.jsonl
```

Both files are UTF-8 JSONL: each nonempty line is one complete JSON object. Produce exactly one response for each input ID, in any order. Exit with status `0` on success. Cases may mix tasks, languages, proposals, and PDF paths. Several cases can share a PDF; caching is allowed, but a prediction cannot depend on its position in the input.

The guide does not prescribe parallel processing or a concurrency limit. Sequential processing is a valid initial design. It does not define optional extra request fields or a recoverable error object. Keep official output fields stable; diagnose failures on stderr rather than filling in a fabricated prediction.

ClaimLens continues with later cases after a case fails and writes successful predictions to `OUTPUT.partial.jsonl` after each success. It replaces the requested output only when every case succeeds; a failed batch exits nonzero and leaves any previous complete output untouched. The partial file is a recovery artifact, not a complete submission. A verdict rejected by claim/citation validation gets one recovery attempt when all billed usage is known. The case's inference deadline and call budget cover both attempts. Transport retries are bounded; unknown token usage remains unknown and prevents an official record instead of being replaced with an estimate.

For long documents, the complete source is examined before evidence selection. If selected excerpts are too large, the model ranks their original units in at most eight reduction rounds, examining every candidate in each round. Original IDs, verbatim text and physical pages are preserved. Reduction may omit relevant evidence and is disclosed in processing metadata. Time/token totals include these passes and retries. Exhausted or fixed context/call-capacity constraints fail explicitly without repeating the whole analysis.

## Request

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Unique case identifier, echoed unchanged. |
| `vote` | string | Proposal name used to locate the correct proposal. Required for task A; optional for task B. |
| `claim.text` | string | Claim to classify. |
| `claim.language` | `de`, `fr`, or `it` | Optional language of the claim. |
| `booklet.path` | string, task A only | PDF path relative to `/data`, for example `booklets/2024_09_22_de.pdf`. |
| `booklet.language` | `de`, `fr`, or `it` | Optional language of the PDF. |
| `reference.text` | string, task B only | Supplied reference passage. |
| `reference.language` | `de`, `fr`, or `it` | Optional language of that passage. |

Exactly one of `booklet` and `reference` is present. Source and claim languages are independent; support all nine combinations. Do not replace a task B reference with additional material retrieved from the dataset or web.

The challenge presentation's slide 24 omits all language fields and also omits `vote` for task B. The fuller API/starter examples include that metadata. **Both forms are accepted.** Omitted language metadata is represented internally as `auto`; Apertus reads the original text directly. No language or label is inferred from the case ID, filename, or dataset annotations. An omitted task B vote supplies no proposal context. If supplied, language metadata must still be exactly `de`, `fr`, or `it`; explicit `null`, an empty string, or `auto` are rejected. A supplied vote must be a nonempty string. Scanned PDFs without a language use one local OCR pass with German, French, and Italian together; missing traineddata is reported.

These are the minimal forms from slide 24:

```json
{"id":"case-0042","booklet":{"path":"booklets/2024_11_24_de.pdf"},"vote":"Étape d'aménagement 2023 des routes nationales","claim":{"text":"La proposition entraînera une augmentation de la TVA."}}
{"id":"case-0043","reference":{"text":"Der Bundesrat und der Nationalrat lehnen die Volksinitiative ab. Die Initiative bringt zahlreiche neue Vorschriften mit sich."},"claim":{"text":"Le Conseil fédéral recommande d'accepter l'initiative."}}
```

The following compact example illustrates task B and deliberately contains no gold label:

```json
{"id":"format-example-B","vote":"Example proposal","claim":{"text":"Die Regel gilt ab 2028.","language":"de"},"reference":{"text":"La règle s’applique à partir de 2028.","language":"fr"}}
```

This is synthetic format documentation, not official voting material.

## Response

| Field | Required content |
| --- | --- |
| `id` | Request ID, unchanged. |
| `label` | Integer `0`, `1`, or `2`. |
| `label_name` | Exact lowercase name matching the integer. |
| `evidence` | Array of objects containing `page` and `text`. |
| `metrics.input_tokens` | Sum of all model input tokens attributable to the case. |
| `metrics.output_tokens` | Sum of all model output tokens, including reasoning tokens. |
| `metrics.inference_time_ms` | Case wall-clock duration, in milliseconds. |

| Label | `label_name` | Source-relative interpretation |
| --- | --- | --- |
| `0` | `entailment` | The source supports the claim. |
| `1` | `neutral` | The source provides insufficient information to support or refute it. |
| `2` | `contradiction` | The source refutes the claim. |

The [public evaluator](https://gitlab.com/ifsoftware/hackapertus-starter/-/blob/main/evaluate.py) requires an integer label, rejects booleans, and compares the label name case-sensitively. A missing or duplicate response, invalid label, or mismatched name is counted as an incorrect prediction. Unknown output IDs are flagged.

Use observed, nonnegative token counts and timing. The public evaluator accepts nonnegative integers or floats for the three metric values and rejects booleans and `null`. Missing/invalid metrics generate warnings in the local evaluator even though they do not alter its classification F1. This does not waive the official reporting requirements. Do not use the starter's zero-valued placeholders for real model calls. If the endpoint does not supply reliable usage, make that limitation explicit rather than inventing counts.

## Evidence

For task A predictions `0` and `2`, return at least one evidence item. Each item has a **1-based PDF page number** and a verbatim quote or page text in the source's original language. Do not translate the quote. Each text is at most **5,000 characters**, and only the **first five** items are scored. A neutral prediction may have an empty evidence array.

Prefer the section treating the proposal in detail. A repeated fact on a summary page might not overlap the benchmark's reference passage; where useful, cite occurrences separately, placing the most relevant first. An item may be a sentence, paragraph, or full page within the length limit. Local fuzzy matching tolerates case, whitespace, and PDF hyphenation differences. Local evaluation currently does not verify page numbers; production output must still report them correctly.

For task B, evidence is optional and is not scored. Use `[]`, or return quotes with `"page": null`. Do not invent a PDF page for a reference-only request.

Some ordinary JSON-object endpoints return a quote string instead of a citation object. ClaimLens binds such a string only when it is a verbatim substring of exactly one supplied passage, then applies independent citation validation. Ambiguous matches, paraphrases and an explicitly incorrect passage ID remain invalid. The official exported evidence format is unchanged.

## Model endpoint and environment

Use only Apertus v1.5 models. The official checkpoint names include `swiss-ai/Apertus-v1.5-8B` and `swiss-ai/Apertus-v1.5-70B`; an actual endpoint may expose only a subset. The CSCS model catalog requires authentication, so available served IDs were not confirmed by the unauthenticated documentation check.

| Variable | Contract |
| --- | --- |
| `BASE_URL` | Development: `https://api.inference.cscs.ch/v1`. Evaluation supplies a token-counting proxy. Every remote model request must honor this runtime value. |
| `API_KEY` | Runtime API key or injected team key. Never include it in source, logs, or an image. |
| `LLM_NAME` | Generic template's model name/version setting. |
| `LLM_BASE_URL`, `LLM_API_KEY` | Generic template compatibility names; they must not override OST's injected `BASE_URL` and `API_KEY`. |

Runtime environment takes precedence over local configuration. The guide allows local parsing, OCR, and embeddings. It does not permit an additional remote model call that bypasses `BASE_URL`. The general Track 2 README permits other open-weight development judges; the narrower OST evaluation contract restricts the submitted inference path to Apertus v1.5.

The local-only browser does not restrict the submission CLI: the CLI accepts an injected remote organizer endpoint. A local `LOCAL_MODEL_ID` is ignored for remote hosts, so the canonical `LLM_NAME` reaches the proxy. Explicitly empty `BASE_URL`/`API_KEY` values are not replaced by generic aliases or a checked-out `.env`.

### Check an organizer endpoint

The actual organizer proxy and its authenticated model availability remain **untested**. Once credentials are available, put them in the shell environment or the ignored `track_2a/.env`. Use the organizer's exact proxy URL and a supported Apertus ID; do not put credentials in a Makefile, source file, or image. This command sends a real request and consumes inference tokens:

```sh
# BASE_URL and API_KEY must already contain the values supplied by the organizer.
# Export them without printing their values; inherited variables override .env.
export BASE_URL API_KEY
export LLM_NAME=swiss-ai/Apertus-v1.5-8B
make check-endpoint
```

`check-endpoint` writes one temporary, language-free German-reference/French-claim case and calls the production CLI. It reports the canonical model, validated label, provider input/output token counts, elapsed time, and whether the simple synthetic example was classified correctly. It does not list or print credentials and deletes temporary inputs/outputs on exit. Exit `0` means a valid official prediction was produced; check `matches_synthetic_example` separately. This is a connectivity/schema check, not a benchmark or an acceptance guarantee. It also works with the configured local endpoint when that model server is running.

A completed [local generic-protocol smoke](../output/v4-readiness/local-api-protocol-smoke.json) used the canonical Apertus ID and ordinary JSON-object mode: the expected entailment was returned with 514 input tokens, 60 output tokens and 3,152.339 ms. This test reached the local Apertus server; it did not reach the organizer endpoint.

For the actual container path, with the same exported credentials:

```sh
make submission
docker run --rm --platform linux/amd64 \
  -e BASE_URL -e API_KEY -e LLM_NAME \
  -v "$PWD/track_2a/data/input:/data:ro" \
  -v "$PWD/track_2a/output:/output" \
  claimlens:submission --input /data/cases.jsonl --output /output/predictions.jsonl
```

Run this example from the repository root after preparing those input/output directories. The endpoint check does not start a model server or obtain credentials.

## Current implementation limits

The following are ClaimLens resource bounds, **not documented organizer input limits**. The observed presentation/API contract does not establish matching maximum sizes, so oversized valid organizer cases remain a compatibility risk. The application reports a failure rather than truncating source text or fabricating a label.

| Resource | Current bound |
| --- | --- |
| Case ID | 256 characters. |
| Claim and supplied vote | 2,000 characters each. |
| Reference text / aggregate source text passed to the engine | 300,000 characters. |
| PDF file / physical pages | 25 MB / 200 pages; encrypted PDFs are rejected. |
| Extracted PDF text before engine validation | 2,000,000 characters; the stricter 300,000-character engine bound still applies. |
| OCR | At most 20 scant-text pages, 180 seconds total, and 30 seconds per external command. |
| Model context | `CONTEXT_TOKENS`, default 8,192, configurable from 4,096 to 262,144 and required to match the serving runtime. |
| HTTP request timeout | `LLM_TIMEOUT_SECONDS`, default 120 seconds, configurable from 1 to 600. |
| Case inference/recovery budget | `DOCUMENT_TIMEOUT_SECONDS`, default 1,800 seconds, configurable up to 3,600. |
| Model-call budget per case | `MAX_DOCUMENT_MODEL_CALLS`, default 48, configurable from 2 to 128. |

The inference deadline is checked around model processing and recovery; it is not a separate process watchdog for PDF parsing. OCR retains its own bounded subprocess deadlines. Confirm the organizer's overall execution limit and actual case sizes before a final submission. These settings do not establish that the implementation will fit an undocumented evaluation time limit.

## Container and data preparation

- Build and run for `linux/amd64` without a GPU.
- `/data` is read-only. Predictions go to the supplied output path under `/output`; caches go to a writable path such as `/tmp`.
- Install dependencies and required local weights into the image at build time. Do not fetch them during prediction.
- Exclude `.env`, API keys, and gold labels from the prediction image and mounts.
- Dataset rows map `claim`, `claim_language`, `vote`, and `reference_language` into request fields. Task B uses `reference_string`; task A uses the PDF referred to by `booklet_url`.

Prepare downloads separately and pin the development dataset revision for reproducibility. The organizer's current preparation script follows `main/v1.1.jsonl`; row-index IDs can change when that file changes. Its gold-label output exists only for separate evaluation.

## Scope of verification

The official guide, starter README, `main.py`, `evaluate.py`, and challenge presentation were read directly. The two slide 24 inputs, full annotated inputs, all nine language combinations, path confinement, and unknown-language OCR have automated interface coverage. Stubbed endpoint checks establish software behavior only. The actual organizer endpoint, held-out model accuracy, and final organizer scoring must be checked separately. This document does not certify a complete official JSON Schema, undocumented evaluator behavior, endpoint model availability, inference quality, or acceptance of a final submission.
