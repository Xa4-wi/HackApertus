# ClaimLens V2 — three-minute presentation

The presentation shows three concrete capabilities: checking a claim across languages, tracing a result to its source, and importing full official booklets. Keep stored demonstrations and real model results visibly distinct.

## Prepare before presenting

Start `make model-serve` and `make dev` in separate terminals, then open http://localhost:8000. Wait until the model status reports that local Apertus is ready. The launcher and application should both use a 16,384-token context. Avoid running evaluation in parallel.

Keep two browser tabs open:

- **Tab A — guided example:** Select **Guided walkthrough**, **Demo**, and **Find the changed numbers**. Examine the claim. This is a stored example and should stay visibly labeled as such.
- **Tab B — actual model result:** Select **Voting booklets**, the French booklet for **3 March 2024**, and the retirement initiative: `Initiative populaire « Pour une prévoyance vieillesse sûre et pérenne (initiative sur les rentes) »`. Enter the German claim below, choose German as the claim language and **Live Apertus**, then run it before the presentation. Keep the actual result, evidence and warnings visible. Full-booklet inference can take several minutes; do not assume it will fit inside the presentation slot.

A suitable claim to examine is:

> Bei Annahme der Initiative steigt das Rentenalter bis 2033 auf 67 Jahre und danach um 100 % der zusätzlichen Lebenserwartung.

This is the same changed-number claim used in the full-booklet smoke check and the guided example. The French source discusses a proposed increase to age 66 by 2033 and an 80% adjustment for additional life expectancy. Review the model's actual verdict, cited pages and coverage before speaking about them; a new run is not promised to reproduce an earlier result. A valid quote does not itself establish correct interpretation. If the run fails or remains unresolved, present that actual state; do not substitute a stored answer while calling it live inference.

**Recorded V2 limitation:** the final actual browser run returned **entailment incorrectly**, despite pages 6/21/22 specifying 66 years and 80%. Its page-22 quotation passed exact-source validation but did not justify that verdict. Use this as an honest demonstration of reviewable evidence and the remaining reasoning problem. Do not present it as a successful classification. The unchanged response, screenshots and review are saved under `output/v2-smoke/`; the run took 179.69 seconds and used 24,820 input / 559 output tokens.

For the import demonstration, use the cached source URL:

```text
https://www.bk.admin.ch/dam/fr/sd-web/In9i5Kp4p64r/2024-03-03_explications_du_conseil_federal.pdf
```

Choose French as the booklet language. Re-importing a cached URL reuses its local document, so this step does not depend on a fresh network transfer. To demonstrate a new download, prepare another direct official PDF URL and test it beforehand. Importing does not run the model.

## Timed walkthrough

| Time | Action | Explanation |
| --- | --- | --- |
| **0:00–0:25** | Show the application and its model status. | “ClaimLens compares a claim with a Swiss voting booklet. German, French and Italian sources and claims can be mixed. Apertus runs locally on this Mac.” |
| **0:25–1:05** | In Tab A, show **Find the changed numbers**, then select `67 Jahre` and `100 %` to inspect their quotations. | “This is a prewritten walkthrough, so no model is running. The claim changes two quantities. The French reference gives 66 years and 80%. Each highlighted assessment leads to its source wording.” |
| **1:05–1:40** | Switch to Tab B. Show the selected French PDF, proposal name and German claim. Open the cached PDF link. | “V2 works with full booklets, not just the walkthrough reference. The library contains 60 PDFs, 20 per source language. Naming the proposal avoids confusing multiple votes in one booklet.” |
| **1:40–2:20** | Show the actual completed live result, its quotations and original page links. Point to token usage, duration and coverage. | “This answer was generated locally before this three-minute presentation. The displayed counts and duration belong to that actual run. For longer sources, each segment is examined and the final pass reasons over selected exact excerpts.” |
| **2:20–2:45** | Expand **Add a voting booklet**. Show **Official URL** and **Upload PDF**. Optionally re-import the cached URL above. | “An official PDF link or a local upload can add another document. PDFs and extracted pages are cached; importing does not run inference. Scanned pages can use local OCR, with warnings retained.” |
| **2:45–3:00** | Return to the result and source. | “The output is entailment, neutral or contradiction, plus verifiable source passages. Exact quotes help review the result; model interpretation and evidence selection still need evaluation. The official CLI produces the same labels and measured usage.” |

If the live run is unavailable, use the 1:40–2:20 slot to show the visible runtime/error state and explain the input, page-preserving extraction and coverage design. Continue using the clearly labeled guided example to explain the intended result interface. Do not announce a fixed live verdict in advance.

## Stored-example outcomes

These expected outcomes describe only the bundled **Demo** records. They are not accuracy claims about Apertus.

| Guided example | Stored classification | Point to demonstrate |
| --- | --- | --- |
| Find the changed numbers | **2 — contradiction** | `67` versus `66`; `100 %` versus `80 %` |
| Original OST example | **0 — entailment** | Original dataset label with cross-language evidence |
| Try a French claim | **0 — entailment** | Same-language support for the proposed age increase |
| Try an unresolved Italian claim | **1 — neutral** | The reference does not establish a CHF 500 monthly guarantee |

## Useful follow-up material

- [Setup and official CLI](../README.md)
- [Local model and provenance](local-model.md)
- [Technical report and current measured results](../technical_report.md)
- `track_2a/output/v2-evaluation/summary.json` after `make evaluate` completes

The evaluation is a small stratified development sample of the OST training split. Software tests, a working PDF importer and one convincing demo do not establish general model accuracy. The organizer's remote proxy still needs a check with organizer credentials.
