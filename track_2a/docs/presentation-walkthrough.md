# ClaimLens V0.5 — live presentation

The current interface uses local Apertus for every check. Start `make model-serve`
and `make dev` in separate terminals, then open http://localhost:8000. The model
panel should show **Ready**. If it says **Offline**, start the model and refresh its
status. You can browse and import PDFs while it is offline, but cannot run a check.

Before the presentation, `make check-endpoint` runs one real synthetic reference
prediction through the CLI and reports actual token usage and time. It checks
connectivity and response format; it does not demonstrate benchmark accuracy.

## Prepare a result

Search for `2024-03-03`, filter to **French**, and choose the booklet. Enter the
proposal `Initiative populaire « Pour une prévoyance vieillesse sûre et pérenne
(initiative sur les rentes) »`. Choose German as the claim language and enter:

> Bei Annahme der Initiative steigt das Rentenalter bis 2033 auf 66 Jahre.

Select **Check claim**. The default retrieval pipeline has a 120-second budget;
the selected version averaged 54.97 seconds on three repeated development cases,
but that is not a guarantee
for this booklet or claim. Prepare an actual result before presenting. Review its verdict, selected-page coverage and original
PDF pages yourself. There is no expected response embedded in the
application, and no fallback answer when inference fails.

## Three-minute walkthrough

| Time | Show | Explain |
| --- | --- | --- |
| 0:00–0:30 | Booklet library and local model status | Search by date/title, filter the source language, and inspect the selected PDF. The cached collection has 60 official booklets. |
| 0:30–1:00 | Proposal, claim and independent language choice | A booklet may contain several proposals. French, German and Italian claims can be checked against any of those source languages. |
| 1:00–2:00 | The actual completed result | The assessment and quoted evidence are shown together. Select a finding, open its original PDF page and verify the interpretation. Be explicit if the model got it wrong. |
| 2:00–2:30 | Selected passages, coverage and usage | A short multilingual query expansion locates original passages in a cached local index; one final Apertus call assesses them. Unselected pages were not read by the model. Reported usage includes both calls and retries. |
| 2:30–3:00 | Add a booklet and Export JSON | An official PDF link or a local upload adds a reusable source. Export preserves the actual model response and its measurements. |

For an import demonstration, this official URL is already cached:

```text
https://www.bk.admin.ch/dam/fr/sd-web/In9i5Kp4p64r/2024-03-03_explications_du_conseil_federal.pdf
```

Select French for this document. Re-importing the cached link does not require a
new download. A new PDF download requires internet access; inference runs locally.

## Explain the evaluation path

The CLI accepts both the presentation's minimal requests and the fuller API
examples: language metadata is optional, and reference-only inputs need no vote.
The submission image runs on a CPU and uses the injected Apertus endpoint. The
local browser is separate from that automated interface.

V0.5 adds the booklet retrieval default: multilingual search expansion capped at
384 output tokens, local BM25 search and a final input budget of 5,000 tokens.
There are at most four transport attempts within the default 120-second budget;
failed checks do not restart the pipeline or silently switch to exhaustive mode.
The original segmented method remains selectable with `DOCUMENT_STRATEGY=exhaustive`.
Task B always keeps full-reference/exhaustive processing. The model returns a brief
explanation, source relation and evidence. Python retains the original claim,
maps the relation to the official labels and independently validates exact
quotes. Retrieved citations retain surrounding original text; when a generic JSON
quote is expanded from an unambiguous exact anchor, the UI warns about it. The
label is unchanged. The UI displays one whole-claim finding. Use the
[current technical report](../technical_report.md) for versioned measurements
and the [readiness evaluation guide](evaluation.md) to explain the separate development
and final public-data cohorts. Do not describe those small public-data samples as
the organizers' private benchmark or claim organizer-proxy verification without
an actual authenticated test.

## Keep the failure history visible

The V2 development evaluation scored 18/27 correct, with all nine neutral cases
misclassified. A full-booklet changed-number claim also received an incorrect
verdict despite containing an exact quotation. Those historical results remain
in the evaluation artifacts and historical V2 PDF, and are discussed in the
[technical report](../technical_report.md). The completed V0.4 development run
scored 25/27 correct and macro-F1 0.927451, with all nine neutral cases correct.
Its mean latency was 17.8 seconds and p95 30.7 seconds. Identify these as tuning
results. The separate 54-case Task B cohorts scored 50/54 correct and macro-F1
0.924722 with no failed predictions; all 34 returned quotes were verified exactly.
These are historical V0.4 measurements with their original source identities.
The V0.4 exhaustive Task A run stopped after one accepted, unscored result took
458.53 seconds. The initial V0.5 run averaged 39.15 seconds but cited an attribution-only
footer and a broken line. The selected contextual-quotation version repeated
those same three cases: all labels were correct, mean time was 54.97 seconds
and p95 was 70.63 seconds, with two calls per case and cached lexical indexes.
Official evidence overlap remained 0.50; all three quotes verified on their
physical pages. These are tuning observations, not fresh validation. The full
nine-case Task A and 54-case Task B evaluations have not been rerun on V0.5.
Do not claim general accuracy or complete readiness from this small experiment.
Exact source quotations help review a result but do not certify that its
classification is correct.

Stop both terminals with `Ctrl+C` after presenting. Downloads and source documents
remain saved for the next session.
