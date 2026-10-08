# ClaimLens V0.4 — live presentation

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

Select **Check claim**. Full booklets can take several minutes, so run the check
before a short presentation and keep the completed result open. Review its actual
verdict and original pages yourself. There is no expected response embedded in the
application, and no fallback answer when inference fails.

## Three-minute walkthrough

| Time | Show | Explain |
| --- | --- | --- |
| 0:00–0:30 | Booklet library and local model status | Search by date/title, filter the source language, and inspect the selected PDF. The cached collection has 60 official booklets. |
| 0:30–1:00 | Proposal, claim and independent language choice | A booklet may contain several proposals. French, German and Italian claims can be checked against any of those source languages. |
| 1:00–2:00 | The actual completed result | The assessment and quoted evidence are shown together. Select a finding, open its original PDF page and verify the interpretation. Be explicit if the model got it wrong. |
| 2:00–2:30 | Usage and processing details | Longer booklets are examined in segments; oversized selected evidence is reduced in bounded model passes. Reported time/tokens include those passes and retries. Reduction can omit relevant facts. |
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

V0.4 adds bounded retries, preserves successful cases when another case fails,
and counts reported usage across attempts. The model now returns a brief
explanation, source relation and evidence. Python retains the original claim,
maps the relation to the official labels and independently validates exact
quotes. The UI displays one whole-claim finding. Show the completed measurements in
the [current technical report](../technical_report.md), and use the
[readiness evaluation guide](evaluation.md) to explain the separate development
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
Task B's source snapshot predates the long-document fix, whose short-source path
is unchanged. The nine full-booklet Task A cases are being rerun after the
context-overflow fix; do not claim their final performance or complete readiness. Exact
source quotations help review a result but do not certify that its classification
is correct.

Stop both terminals with `Ctrl+C` after presenting. Downloads and source documents
remain saved for the next session.
