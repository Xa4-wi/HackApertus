# ClaimLens — recording a two-minute presentation

Use the [two-minute shot list and voiceover](video-script.md) for the final video. This page covers the actual local application and recording setup. The presenter is **Xavier · OneLegedCoder**; no contact details are required.

## Prepare the application

On the configured Mac, the Apertus weights and 60 official booklets are already cached. First-time installations should follow [the README](../README.md#first-time-setup) and [local model setup](local-model.md). Booklets can also be added with **Add a booklet**, using an official PDF link or a local PDF upload; importing a source does not run inference.

From `track_2a/`, start the model in one terminal:

```sh
make model-serve
```

Start the application in another terminal:

```sh
make dev
```

Open **http://localhost:8000**. Wait until the model panel says **Ready**; use **Refresh model status** if necessary. An offline model disables claim checking. Every submitted check calls the local Apertus model; the application has no demo answers.

If connectivity needs a separate check, `make check-endpoint` makes a real synthetic CLI prediction and reports its usage and time. Run it before recording and never at the same time as a browser check: this local runtime has one inference slot. It is a connection and format check, not a quality benchmark.

Use the delivered configuration documented in [validation.md](validation.md):

```dotenv
RETRIEVAL_QUERY_MODE=multilingual
RETRIEVAL_CITATION_MODE=full
RETRIEVAL_PROMPT_TOKENS=5000
```

The faster prefix candidate was rejected because it lost relevant evidence. Full quotations, multilingual queries and the 5,000-token assessment budget remain the final defaults. Keep these settings for the recording; shortening the edit does not require shrinking the model’s input. Keep the source and result readable, and disclose any edit that removes inference waiting.

## Verified recording example

Search **2022-02-13**, filter **German**, and select **13 February 2022**, shown with **German · 64 pages**. Its [official PDF](https://www.bk.admin.ch/dam/de/sd-web/JwKnnvQMcYT2/2022-02-13_erlaeuterungen_des_bundesrates.pdf) is already cached locally.

Set **Proposal in this booklet** to:

```text
Änderung des Bundesgesetzes über die Stempelabgaben
```

Set **Claim language** to **Italian**, and paste this exact claim:

```text
Nel riepilogo si afferma che l’Emissionsabgabe corrisponde al due per cento del capitale raccolto.
```

For the English narration, this says that the summary gives the capital issuance tax as two percent. Keep the actual Italian text on screen.

The real local HTTP application rehearsal on **8 October 2026** returned **2 · Contradicted**. Apertus cited physical **PDF page 38**, including these opening lines:

> Die Emissionsabgabe beträgt 1% des aufgenommenen Eigenkapitals.
> Es gilt ein Freibetrag von einer Million Franken.

The returned quotation continues through the diagram labels. Its wording matches the original page. The one-percent rate contradicts the claim’s two percent, and the quotation preserves the one-million-franc exemption. Open **View PDF · page 38** and show both the rate and the exemption. Page 8 also gives the rate in the booklet’s summary, and page 37 explains it in more detail.

| Rehearsal observation | Actual result |
| --- | --- |
| Source → claim | German → Italian |
| Verdict | **2 · Contradicted** |
| Evidence | One quotation, physical PDF page 38 |
| Input / output tokens | **3,485 / 297**, reported by the inference provider across both requests |
| Analysis time | **32.004296 seconds**; the UI rounds this to **32.0 s** |
| HTTP request wall time | **32.014 seconds** |
| Model requests | **2**, with no simulated response |
| Retrieved source | **12 units on 8 physical pages** of the 64-page PDF; the UI shows **8 / 64** |
| Source extraction | **63 text-bearing passages**; page 2 has no readable text |
| Source-only token count | Unavailable; reported as `null`, separate from measured input tokens |

The selected pages were 7, 8, 36, 37, 38, 39, 43 and 60. This is a known presentation case, excluded from the new evaluation statistics. Its latency describes this run, not a promised response time. Repeating the request runs the actual model again and can change the response and measurements.

**Completed:** live HTTP application rehearsal and automated DOM interaction checks. **Still required before filming:** an in-person visual rehearsal. No browser was available for automated visual inspection in this session. Confirm text size, scroll positions and the PDF viewer’s page navigation on the recording machine.

## Capture the real interaction

1. Enable Do Not Disturb, close unrelated tabs and hide terminals containing configuration. Record the browser window at 1920 × 1080 if available. Start around 100–110% browser zoom, then adjust until labels and quotations are legible without horizontal scrolling.
2. Begin with the **ClaimLens** heading and **Ready** model panel. Filter **Choose a booklet** by the verified source language and search its date. Select the source and show **Open PDF** briefly if useful.
3. Enter the exact proposal and claim from the verified example, with the separate **Claim language** selector set correctly. Start recording before selecting **Check claim** once.
4. Record continuously while Apertus runs. The default retrieval deadline is 120 seconds; actual time depends on the input and runtime. Keep the raw recording. Shorten only the wait in the edit and display **“Inference wait shortened in editing”** across that transition.
5. Capture the returned verdict, explanation and **Source evidence**. Follow **View PDF · page …** to the cached original and inspect the matching passage. PDF page numbers are physical page positions, including covers and blank pages.
6. Return to **Analysis time**, **Input tokens**, **Output tokens** and **Pages selected / booklet**. Use the current run’s visible values. The exported response preserves these measurements; a repeat can differ from the verified example.
7. Select **Export JSON** and save it beside the raw recording. Briefly show the active `track_2a/` directory with `technical_report.md` and `technical_report.pdf` visible together, then return to the result for the closing shot. Do not show `.env`, keys, archived gold labels or local evaluation artifacts on screen.

The video script schedules exactly 120 seconds and includes a short disclaimer about model errors. If a new run fails or changes its verdict, inspect it and disclose what happened; do not replace the result with a typed answer or imply that a previously captured result just completed. Rehearsal and recorded inference both use the real model.

## Explain what the audience sees

The interface labels correspond to the challenge output:

| UI verdict | Official output | Meaning |
| --- | --- | --- |
| **0 · Supported** | Entailment | The booklet supports the claim. |
| **1 · Unresolved** | Neutral | The booklet does not provide enough information either way. |
| **2 · Contradicted** | Contradiction | The booklet contradicts the claim. |

A German, French or Italian claim can be paired with a booklet in any of those languages. The app keeps the original claim and original source wording. For long booklets, multilingual search locates selected passages before Apertus assesses them. Exact quotations are checked against the source, with physical PDF links so a viewer can inspect the interpretation. Selected passages do not establish complete booklet coverage.

The local model is the pinned community Q4_K_M text conversion of **Apertus v1.5 8B**, served by llama.cpp on this Mac. Inference uses the supplied source; it performs no internet search. Downloading a new official booklet needs internet access, while cached sources remain available locally.

**Export JSON** downloads the actual browser response. The separate CLI supplies the challenge’s JSONL predictions, labels 0/1/2, page/text evidence and token/time metrics. It supports whole-booklet inputs and supplied-reference inputs. Its Docker submission calls the configured inference endpoint; model weights are kept outside the image. The browser is the presentation interface, and the CLI is the evaluator interface.

See [validation.md](validation.md) for measured quality and timing, and the technical report in [Markdown](../technical_report.md) or [PDF](../technical_report.pdf) for the final method and limitations. Small local samples do not establish general accuracy or private-benchmark readiness. Do not promise that exact quotations guarantee the model’s interpretation.

## Finish and stop services

Export the result and save the raw recording, edited two-minute video and narration together. Stop the application terminal and model terminal with **Ctrl+C**. If a separate Docker verification session was started, also stop its application container and run `colima stop --profile claimlens` when it is no longer needed. Native recording does not require starting Colima.

Keep the downloaded weights and booklet cache for the next session. They are excluded from final delivery. The root [README](../../README.md#validation-and-delivery) describes the active project and final reports; the former export is preserved under `archive/legacy-submission/`.
