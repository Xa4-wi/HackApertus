# ClaimLens and Hack Apertus Track 2A

Verified on **8 October 2026** against the organizer's guide, OST's solution API guide, the official project template, and the OST starter. This records requirements; it does not claim that the prototype has passed the private benchmark.

## Selected challenge

ClaimLens implements **Track 2A — OST: Multilingual Natural Language Inference over Swiss Official Voting Booklets**. The task assesses a claim against supplied documents, including attributed arguments, legal detail, quantities, dates, and qualifications. Its labels describe what the source entails, leaves unresolved, or contradicts. They do not establish unrestricted real-world truth or recommend a political choice.

The initial concept brief suggested one language. The verified challenge requires **all nine source–claim combinations of German (`de`), French (`fr`), and Italian (`it`)**, and both document and reference tasks. An interactive evidence review interface is an additional product feature; the CLI is the evaluation interface.

Sources: [OST challenge](https://hackapertus.notion.site/3deb4fec112a80258fd2ddc61616011d), [solution API guide](https://hackapertus.notion.site/solution-api-guide-ef5b4fec112a834da43101ede56300f5).

## Task and data

| Task | Supplied source | Required operation |
| --- | --- | --- |
| A — Document | Voting booklet PDF, proposal name, claim | Locate the correct proposal and classify the claim with cited PDF evidence. |
| B — Reference | Reference passage, proposal name, claim | Classify the claim against only the provided passage. |

Use the human-annotated [OSTswiss/MNLIoverSwissVotingBooklets](https://huggingface.co/datasets/OSTswiss/MNLIoverSwissVotingBooklets) development dataset. The API guide currently points to `main/v1.1.jsonl`. The Federal Chancellery's [booklet archive](https://www.bk.admin.ch/de/sammlung-der-abstimmungsbuechlein-seit-1978) is the linked original corpus. The dataset supplies the booklet URL for document cases and `reference_string` for reference cases.

Prepare data before evaluation. Keep gold labels outside the prediction container; the predictor must never use them. Retain provenance, dataset revision, original licenses, and source languages for imported material. The official starter notes that reference rows containing only a title must also be preserved. Its first-N sampling is not necessarily balanced.

The guide recommends a full-document baseline before testing retrieval or compression. RAG, OCR, Docling, embeddings, and fine-tuning are not mandatory. A later retrieval experiment should be compared with that baseline on classification quality, evidence, tokens, and time.

Sources: [API guide](https://hackapertus.notion.site/solution-api-guide-ef5b4fec112a834da43101ede56300f5), [official starter README](https://gitlab.com/ifsoftware/hackapertus-starter/-/blob/main/README.md).

## Models and execution

Use **Apertus v1.5** for inference. The prototype's intended first selection is `swiss-ai/Apertus-v1.5-8B`, with `swiss-ai/Apertus-v1.5-70B` as the larger alternative. Those checkpoint names are published in the [official model card](https://huggingface.co/swiss-ai/Apertus-v1.5-8B). Endpoint availability still depends on the supplied account; a checkpoint name is not proof that an endpoint currently serves it.

The OST guide specifies `https://api.inference.cscs.ch/v1` for development. At evaluation, the organizer injects a token-counting proxy through runtime `BASE_URL` and `API_KEY`. Every remote model call must use that URL. Local configuration must not override the injected environment. The generic template also names `LLM_NAME`, `LLM_BASE_URL`, and `LLM_API_KEY`; compatibility aliases must preserve the OST variables' precedence.

The Docker target is **`linux/amd64`, CPU only**. Install dependencies and any required local weights at build time. Evaluation must not download models or dependencies. Mount `/data` read-only, write predictions to `/output`, and use `/tmp` for writable caches. Exclude secrets and `.env` files from the image. See [solution-api.md](solution-api.md) for the exact request/response contract.

The [resources guide](https://hackapertus.notion.site/0e9b4fec112a8380989881f264af0895) stated, in its 6 October 2026, 18:40 CEST update, that CSCS keys had been distributed and new requests were closed. Organizer/CSCS inference still needs valid supplied credentials; the configured local Apertus runtime works without an API key. Interface tests do not establish hosted access or model accuracy; report actual inference measurements separately.

## Repository and deliverables

Preserve `track_2a/` and its template locations: `README.md`, `technical_report.md`, `Makefile`, `src/`, `data/`, and `docs/`. Remove other tracks. Organize implementation into readable modules inside `src/`; keep supporting documentation inside `docs/`. `data/` must stay at or below **100 MB**.

The template was inspected at commit [`7f2382275461baf3fa6c8855d157d86abffe9f0e`](https://github.com/HackApertus/project-template/tree/7f2382275461baf3fa6c8855d157d86abffe9f0e). Judges expect `make run` on a clean checkout to launch Docker. The official OST API additionally requires the container entrypoint to accept `--input` and `--output`.

Submission needs the reproducible repository, working entailment CLI, evidence passages, and a technical report including token usage and inference time. The [submission website](https://hackapertus.ch/online-hack/submissions) lists a **PDF report of at most six pages** for OST and **no mandatory demo video**. The Markdown report provides detailed project documentation; `scripts/build_report.py` builds a shorter presentation PDF using recorded measurements. Record methodology, model and configuration, context preparation, experiments, shortcomings, and what has actually been measured.

Sources: [template README](https://github.com/HackApertus/project-template/blob/7f2382275461baf3fa6c8855d157d86abffe9f0e/README.md), [Track 2A README](https://github.com/HackApertus/project-template/blob/7f2382275461baf3fa6c8855d157d86abffe9f0e/track_2a/README.md), [submission guide](https://hackapertus.notion.site/c91b4fec112a82f6adcf81c67c2acde3).

## Evaluation

Primary quality measurement is three-class macro-F1 on a held-out private benchmark, separately for tasks A and B. The [official starter evaluator](https://gitlab.com/ifsoftware/hackapertus-starter/-/blob/main/evaluate.py) and README specify minimum macro-F1 **0.60 for A** and **0.70 for B**. These are targets, not results achieved by ClaimLens.

Evidence is scored separately for non-neutral task A cases. Only the first five evidence items count, with a maximum of 5,000 characters per item. The local evaluator uses fuzzy overlap with the gold passage and currently does not validate page numbers. Official evidence requirements still demand correct PDF pages. Metrics include input tokens, output tokens including reasoning, and case wall-clock milliseconds. The final proxy-derived efficiency comparison cannot be reproduced from a small local fixture run.

## Event and submission

- Online hackathon: **1–16 October 2026**; teams of **one to five**.
- Final deadline: **16 October 2026, 12:00 CEST (Europe/Zurich)**, without an extension.
- Submit on the [Hack Apertus website](https://hackapertus.ch/online-hack/submissions), not Devpost. Registration and discovery also use [Devpost](https://hackapertus.devpost.com/).
- Main event communication: [Discord](https://discord.gg/hack-apertus). OST challenge channel: [challenge Discord link](https://discord.gg/bfmRY36n3).
- OST information session: 2 October, 13:30–14:15 CEST; Q&A: 8 October, 12:00–12:30 CEST. Speakers: Prof. Dr. Mitra Purandare and Abinas Kuganathan.
- Online winners are selected by 23 October 2026; qualifying winners advance to the Grand Finals on **14 May 2027 in St. Gallen**.

Sources: [getting started guide](https://hackapertus.notion.site/getting-started-guide-onlinehack), [Devpost event](https://hackapertus.devpost.com/), [OST guide](https://hackapertus.notion.site/3deb4fec112a80258fd2ddc61616011d).

## Licensing and remaining checks

The organizer's [terms, section 6](https://hackapertus.ch/terms-and-conditions), specify Apache-2.0 for submitted source code and model weights, CC-BY-4.0 for documentation and other non-code work, and CDLA-Permissive-2.0 for submitted datasets, subject to any event-specific override. Participants retain ownership. Existing third-party content keeps its own license and attribution; importing a benchmark does not make the team its author.

Before submission, recheck the live guide, run the Docker image under the judging mounts, evaluate actual Apertus outputs across both tasks and every language pair, and produce the PDF report. The public guides do not state a concurrency limit, retry policy, or a JSON error-response schema. They do not authorize treating a failed inference call as a neutral prediction.
