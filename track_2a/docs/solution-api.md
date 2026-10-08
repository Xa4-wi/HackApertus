# OST solution API contract

Verified on **8 October 2026**. Source of truth: [official solution API guide](https://hackapertus.notion.site/solution-api-guide-ef5b4fec112a834da43101ede56300f5). The [optional OST starter](https://gitlab.com/ifsoftware/hackapertus-starter) demonstrates the contract with random predictions; its output is not a working model baseline.

## Invocation

The Docker entrypoint must accept:

```text
<entrypoint> --input /data/cases.jsonl --output /output/predictions.jsonl
```

Both files are UTF-8 JSONL: each nonempty line is one complete JSON object. Produce exactly one response for each input ID, in any order. Exit with status `0` on success. Cases may mix tasks, languages, proposals, and PDF paths. Several cases can share a PDF; caching is allowed, but a prediction cannot depend on its position in the input.

The guide does not prescribe parallel processing or a concurrency limit. Sequential processing is a valid initial design. It does not define optional extra request fields or a recoverable error object. Keep official output fields stable; diagnose failures on stderr rather than filling in a fabricated prediction.

## Request

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Unique case identifier, echoed unchanged. |
| `vote` | string | Proposal name in the source language, used to locate the correct proposal. |
| `claim.text` | string | Claim to classify. |
| `claim.language` | `de`, `fr`, or `it` | Language of the claim. |
| `booklet.path` | string, task A only | PDF path relative to `/data`, for example `booklets/2024_09_22_de.pdf`. |
| `booklet.language` | `de`, `fr`, or `it` | Language of the PDF. |
| `reference.text` | string, task B only | Supplied reference passage. |
| `reference.language` | `de`, `fr`, or `it` | Language of that passage. |

Exactly one of `booklet` and `reference` is present. Source and claim languages are independent; support all nine combinations. Do not replace a task B reference with additional material retrieved from the dataset or web.

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

## Model endpoint and environment

Use only Apertus v1.5 models. The official checkpoint names include `swiss-ai/Apertus-v1.5-8B` and `swiss-ai/Apertus-v1.5-70B`; an actual endpoint may expose only a subset. The CSCS model catalog requires authentication, so available served IDs were not confirmed by the unauthenticated documentation check.

| Variable | Contract |
| --- | --- |
| `BASE_URL` | Development: `https://api.inference.cscs.ch/v1`. Evaluation supplies a token-counting proxy. Every remote model request must honor this runtime value. |
| `API_KEY` | Runtime API key or injected team key. Never include it in source, logs, or an image. |
| `LLM_NAME` | Generic template's model name/version setting. |
| `LLM_BASE_URL`, `LLM_API_KEY` | Generic template compatibility names; they must not override OST's injected `BASE_URL` and `API_KEY`. |

Runtime environment takes precedence over local configuration. The guide allows local parsing, OCR, and embeddings. It does not permit an additional remote model call that bypasses `BASE_URL`. The general Track 2 README permits other open-weight development judges; the narrower OST evaluation contract restricts the submitted inference path to Apertus v1.5.

## Container and data preparation

- Build and run for `linux/amd64` without a GPU.
- `/data` is read-only. Predictions go to the supplied output path under `/output`; caches go to a writable path such as `/tmp`.
- Install dependencies and required local weights into the image at build time. Do not fetch them during prediction.
- Exclude `.env`, API keys, and gold labels from the prediction image and mounts.
- Dataset rows map `claim`, `claim_language`, `vote`, and `reference_language` into request fields. Task B uses `reference_string`; task A uses the PDF referred to by `booklet_url`.

Prepare downloads separately and pin the development dataset revision for reproducibility. The organizer's current preparation script follows `main/v1.1.jsonl`; row-index IDs can change when that file changes. Its gold-label output exists only for separate evaluation.

## Scope of verification

The official guide, starter README, `main.py`, and `evaluate.py` were read directly. This document records their observed contract. It does not certify a complete official JSON Schema, undocumented evaluator behavior, endpoint model availability, inference quality, or acceptance of a final submission.
