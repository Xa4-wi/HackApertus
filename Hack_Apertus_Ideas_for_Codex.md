# Hack Apertus Track 2A — project ideas and Codex brief

Prepared 8 October 2026. Concept document only: no implementation, generated test suite, model run, or claimed benchmark result.

## Recommendation

**Best fit for you: OST's evidence-backed claim-verification direction.**
**Easiest visible prototype: FHGR's interview-coaching direction.**
**Best research-oriented alternative: UZH's cross-language meaning-difference direction.**

These are my engineering assessments, not official rankings or predictions of winning chances. Your CS background, red-team internship experience and interest in quantitative reasoning make a project with inspectable evidence a stronger fit than a generic chatbot.

The organizer's announcement identifies the five academia topics. The exact files in the user-supplied `track_2a` folder could not be retrieved here. The concepts below are proposals, not verified challenge requirements. Codex should inspect the local official repository before committing to a dataset, label set, output schema or submission format.

Official reference: https://github.com/HackApertus/project-template/tree/main/track_2a

## Idea 1 — ClaimLens: identify exactly where a claim departs from the evidence

Challenge alignment: OST, checking claims against official voting materials.

### The product

A user selects a proposal and submits a claim. The application separates the claim into checkable parts and displays each part beside the strongest relevant passages. It identifies what is supported, contradicted, or unresolved by the available documents.

The main feature is not a fluent answer. It is a clear explanation of **which words are justified and which words overstate the source**.

### Hypothetical example — not actual voting material

Claim: “The proposal charges every household CHF 200 starting in 2027.”

An invented source passage describes an annual CHF 200 fee for commercial properties starting in 2028.

The interface would distinguish:

- Amount: the source states CHF 200.
- Who pays: commercial properties, not every household.
- Start date: 2028, not 2027.

It should not merely return one unsupported confidence score for the whole sentence.

### What makes this more interesting than a generic document chatbot?

**Two-sided evidence search.** Look for passages that could contradict the claim, not only passages that sound supportive. This is a design choice, not a guarantee of completeness.

**Attribution-aware explanations.** Distinguish proposed legal text, government interpretation, campaign arguments and forecasts. A document reporting someone's prediction does not prove the prediction.

**Numbers, dates and scope.** Focus on altered amounts, start dates, “all” versus “some”, proposals versus existing rules, and “may” versus “must”. Structured checks could complement the model's interpretation.

**A visible evidence trail.** Show the original source, page and exact excerpt. Make missing or conflicting evidence visible rather than forcing a verdict.

### Why this suits you

This uses the habit of identifying a specific failure and showing reproducible evidence, which connects to your security background. It also gives you an algorithmic problem—finding and comparing relevant evidence—without making model training the entire project.

### First version

One proposal, one language, its permitted documents, a claim input field, and an evidence panel. Apertus interprets retrieved passages; ordinary code preserves provenance and handles predictable structure.

Start with German or English, subject to the supplied data. A second language is an extension, not an initial requirement.

### Avoid initially

A broad internet fact-checker, political recommendations, autonomous browsing, speech support, multiple agent roles, fine-tuning, or a large document collection. Do not treat lack of evidence as proof that a statement is false.

## Idea 2 — InterviewMirror: coach the reasoning behind an answer

Challenge alignment: FHGR's SmartStart interview-coaching topic.

### The product

A candidate supplies a role description and, optionally, their CV. Apertus conducts a short interview, responds to the candidate's actual answer, and shows specific ways to improve the reasoning and communication.

A useful angle for you would be CS and quantitative internship preparation, provided this specialisation is allowed by the brief.

### The distinguishing idea

Build an **answer map**, not just an answer score. Break an answer into claim, supporting example, personal contribution, outcome and reflection. Show what is missing.

For a technical answer, identify an unexplained assumption and ask a follow-up about it. For an experience-based answer, distinguish what the team did from what the candidate personally contributed.

Example feedback: “You explained the system, but not the trade-off you personally chose. Explain the alternative and why you rejected it.”

### First version

Text only. One target role, three questions, adaptive follow-ups and a compact debrief quoting the candidate's own answers. An optional retry lets the candidate improve the answer without having the system invent achievements.

### Why choose it?

I expect this to be the simplest route to a visible, personally useful demo. It connects to your own interview preparation. The challenge is making the feedback specific and defensible rather than producing polished but generic advice.

### Avoid initially

Video, emotion detection, personality profiling, candidate ranking, hireability predictions and complicated voice infrastructure. Treat uploaded CVs as private; do not retain them by default.

## Idea 3 — MeaningDiff: a semantic diff viewer for multilingual documents

Challenge alignment: UZH's SwissGov-RSD topic.

### The product

Display two related documents in different languages side by side and highlight meaning that is present on only one side or differs between them.

Instead of translating both texts and giving one similarity score, point to the specific phrase responsible for the difference and explain its consequence.

### Interesting cases

A date differs; one language omits an exception; “may apply” becomes “must apply”; the translation narrows the people covered; a recommendation becomes an obligation.

These are illustrative product targets, not claims about errors in the official dataset.

### Why this direction is credible

UZH publishes the SwissGov-RSD dataset and a repository with token-level task descriptions and evaluation utilities. Its annotation format is more specific than a paragraph-level comparison. Codex must inspect and preserve the actual official contract.

### First version

One language pair, short paired passages, highlighted differences and a short explanation per difference. Preserve original spans rather than inventing replacement wording.

### Trade-off

This is the most attractive option for a research-style portfolio piece, but token alignment and mapping explanations onto the required output make it more demanding than a basic chat interface.

## Two additional ideas

### ParliamentJSON — structured extraction with traceable origins

Challenge alignment: OpenParlData/BFH's parliamentary PDF extraction topic.

Convert documents into a consistent structured representation while attaching source-page and source-span references to every extracted field. A side-by-side review screen would show the PDF passage behind the extracted title, identifier, date or body text.

The distinguishing feature should be provenance and visible uncertainty, not just “PDF in, JSON out”. Let the official schema determine fields. Start with one document layout; scanned pages, tables and mixed reading order can expand the work significantly.

### GroundedPick — ask before acting on an ambiguous instruction

Challenge alignment: ZHAW's robot-arm language/vision topic.

Given an instruction such as “pick the red item”, resolve it against the scene. When multiple objects match, ask a clarifying question rather than choosing one arbitrarily. Show the selected object and the reason before execution.

This is an appealing interaction idea, but I would not select it first without confirming the provided robot or simulator, perception interface and safety constraints. Hardware access must not be assumed.

## Concept-level implementation direction

For ClaimLens, propose a Python application with a single-page interface and a configurable, permitted Apertus inference endpoint. Begin with the official corpus, simple file storage and a small retrieval component. Add infrastructure only when a concrete requirement justifies it.

Suggested flow:

Claim and proposal ID → relevant passages → claim decomposition and interpretation → evidence-backed result → human-readable review panel.

The model should not be given shell tools or unrestricted browsing. Imported document text is evidence, not instructions. Any displayed “supported” or “contradicted” label must be scoped to the available evidence and aligned with the actual challenge's label definitions.

Leave dependency versions, implementation, local experiments and validation to Codex in the user's project environment.

## Prompt to paste into Codex

```text
I want to develop one project for Hack Apertus Track 2A.
Read the official project-template repository, especially track_2a, before implementation:
https://github.com/HackApertus/project-template/tree/main/track_2a

My preferred concept is ClaimLens for the OST claim-verification challenge.
This is an idea brief, not a verified interpretation of every official requirement.
First identify the actual OST task, permitted data, model requirements, output schema
and submission format from the repository. Do not invent missing requirements.

Product idea:
A user selects a proposal and enters a claim. Break the claim into checkable parts,
retrieve relevant official passages, and show what is supported, contradicted or
unresolved, using the official label definitions. Display exact excerpts and source
pages. Distinguish factual evidence from attributed opinions or predictions.

Prioritise three features:
1. Find evidence that challenges the claim as well as evidence that supports it.
2. Explain differences in numbers, dates, population scope and qualifications.
3. Keep a visible source trail; abstain when the evidence is inadequate.

Start with one proposal, one language and a small permitted corpus. Use Apertus for
interpretation and ordinary code for provenance and structured handling. Prefer a
simple Python application and a small interface. Do not begin with fine-tuning,
a GPU-serving stack, multiple agents or broad internet crawling.

Use my local development environment for implementation and validation. Start by
summarising the verified requirements and your minimal implementation plan, then
build incrementally. Do not claim a result that you have not observed.
Ask before paid inference or significant downloads. Never print or commit credentials.
Do not silently switch to another challenge if the official brief conflicts with this idea.
```

## Source collection

Organizer-authored challenge announcement, visible as a repost on an OST provider's profile:
https://ch.linkedin.com/in/abinas-k-712760190

Official Track 2A folder supplied by the user; detailed contents not retrieved in this session:
https://github.com/HackApertus/project-template/tree/main/track_2a

UZH task repository:
https://github.com/ZurichNLP/SwissGov-RSD

UZH dataset:
https://huggingface.co/datasets/ZurichNLP/SwissGov-RSD

Official Codex IDE documentation:
https://developers.openai.com/codex/ide/

The proposed product names, features, scope and ranking are original suggestions. They are not advertised official deliverables or established performance claims.
