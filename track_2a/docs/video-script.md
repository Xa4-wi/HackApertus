# ClaimLens — two-minute video script

**Presenter:** Xavier · OneLegedCoder  
**Challenge:** Hack Apertus Track 2A · OST multilingual claim checking  
**Length:** 2:00, including transitions. Record the actual local application. The [recording walkthrough](presentation-walkthrough.md) contains setup and the verified example.

## Shot list

| Time | Picture and action | Narration |
| --- | --- | --- |
| 0:00–0:12 | ClaimLens heading; add a small “Xavier · OneLegedCoder” title. Keep **Local inference** visible. | Paragraph 1 |
| 0:12–0:32 | Search **2022-02-13**, filter **German**, and choose **13 February 2022**. Show the stamp duties proposal, paste the exact Italian claim from the walkthrough, and set **Claim language → Italian**. | Paragraph 2 |
| 0:32–0:44 | Select **Check claim** once; show the live progress indicator. Cut to the completed result with **“Inference wait shortened in editing”** visible across the cut. | Paragraph 3 |
| 0:44–1:10 | Frame **2 · Contradicted**, the explanation and **Source evidence** together. Open **View PDF · page 38** and point to **1%** and the exemption in the original diagram. | Paragraph 4 |
| 1:10–1:30 | Return to the result. Frame **Analysis time**, **Input tokens**, **Output tokens** and **Pages selected / booklet**. | Paragraph 5 |
| 1:30–1:48 | Select **Export JSON**. Briefly show `track_2a/` with `technical_report.md` and `technical_report.pdf` together, without local credentials or development archives. | Paragraph 6 |
| 1:48–2:00 | Return to the evidence and source. End on the ClaimLens heading and team name. | Paragraph 7 |

## Voiceover

I’m Xavier from OneLegedCoder. ClaimLens checks claims against Swiss voting booklets, with original evidence that people can inspect themselves.

Here I select a German booklet and the stamp duties proposal. My Italian claim says the capital issuance tax is two percent. German, French and Italian sources and claims can be combined independently.

Every check uses Apertus running locally. I’ve shortened the wait in this video; the verdict and reported analysis time come from the actual run.

The model returns two: contradicted. This original German passage says one percent and gives an exemption of one million francs. Opening physical PDF page thirty-eight lets us verify it in context. The other possible labels are zero for supported and one for unresolved.

For longer booklets, ClaimLens searches original passages before asking Apertus for an assessment. It preserves the original claim and checks quotations against the source. The interface shows selected pages, input and output tokens, and measured analysis time, so the cost of this check is visible.

The result can be exported as JSON. A separate command-line interface and Docker submission support automated evaluation, including claims with a supplied reference. The project and technical report sit together in the template’s Track 2A directory and document how to reproduce the workflow.

This is a research prototype: retrieved evidence can be incomplete, and the model can be wrong. ClaimLens makes each assessment easier to review against the source.

## Editing and claim checks

The exact example passed a real local HTTP application rehearsal with 3,485 input tokens, 297 output tokens and 32.004296 seconds of reported analysis time. This known presentation case is excluded from fresh evaluation statistics. HTTP and automated DOM checks are complete; an in-person browser visual rehearsal is still needed. No video has been recorded by this package.

- Use one continuous application recording for the input, request and returned result. Split or speed up the waiting section only; label the edit as specified above. Keep the original recording and exported JSON together.
- Show this recording’s own token counts and measured time. Do not replace them with an average or the rehearsal’s values. Model loading is outside the displayed analysis time. If its verdict or citation differs, review the response and adapt the corresponding narration before recording the voiceover.
- Keep the source-language selection, claim-language selection, actual verdict and original page readable. Pan or zoom during editing instead of compressing the entire desktop into one frame.
- The three output meanings are a legend, not three demonstrated predictions. Do not manufacture additional examples to fill the timeline.
- Do not claim “instant,” “all pages read,” “100% accurate,” or official acceptance. The current validation record states the measured quality and remaining limits.
- Aim for approximately 120 spoken words per minute. Rehearse once, then trim pauses and transitions to end at exactly 2:00; never speed up the narration to hide an overlong script.
