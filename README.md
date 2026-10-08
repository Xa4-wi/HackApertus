# ClaimLens

See exactly where a claim departs from its evidence. A Python prototype for **Hack Apertus Track 2A — OST: Multilingual Natural Language Inference over Swiss Official Voting Booklets**.

Select **Apertus v1.5 8B** (default), examine a claim, and trace each assessment to the original passage. This Mac is configured for local inference with a downloaded **Q4_K_M text conversion (5.06 GB)** of Apertus v1.5 8B. No API key is needed. A remote endpoint can also provide 70B. The included offline walkthrough uses one real French OST reference and four prewritten examples in German, French, and Italian; demo mode makes **no model calls**.

## Try it locally

```bash
# Terminal 1: serve the downloaded model (leave running)
make model-serve
# Terminal 2: start ClaimLens
make dev
```

Open **http://localhost:8000**, choose **Live Apertus**, then **Examine claim**. The local API is `http://127.0.0.1:8081/v1`; configuration is in the ignored `track_2a/.env`. This setup uses llama.cpp with Apple Metal because Docker Desktop is not installed. See [local model setup](track_2a/docs/local-model.md) for installation, provenance, and the 8,192-token context limit.

For the offline UI alone, `make dev` needs only Python 3.9+. Select demo mode to use stored answers without starting the model.

The full OST dataset has also been saved locally: **1,488 rows**, all nine DE/FR/IT language combinations. Load it with `datasets.load_from_disk("track_2a/data/local/ost/dataset")`. Prediction inputs and gold labels are exported separately; see [data setup](track_2a/data/README.md).

The template's Docker entry point is:

```bash
make run
```

This builds the interactive demo image for `linux/amd64` and binds the UI to localhost. Docker must be installed and running. It was unavailable in the development environment, so the container build has not yet been executed.

## Project guide

The required `track_2a/` directory remains the project root; the top-level Makefile forwards commands into it. Your original idea brief is retained unchanged.

```text
HackApertus/
├── Hack_Apertus_Ideas_for_Codex.md   Original concept brief
├── Makefile                        Convenience commands
├── LICENSE                         Template's Apache-2.0 license
└── track_2a/
    ├── README.md                   Setup and CLI examples
    ├── technical_report.md         Architecture, validation, limitations
    ├── Makefile / Dockerfile       Demo and submission targets
    ├── requirements.txt            Pinned PDF parser
    ├── requirements-data.txt       Optional dataset download dependencies
    ├── .env.example                Model configuration; no credentials
    ├── src/claimlens/
    │   ├── cli.py                  Official JSONL entry point
    │   ├── booklets.py             Request validation and PDF pages
    │   ├── engine.py               Claim assessment and quote validation
    │   ├── llm.py                  Apertus endpoint adapter and prompt
    │   ├── models.py               Labels, limits, application errors
    │   ├── config.py               Environment configuration
    │   ├── corpus.py               Attributed demo data
    │   ├── server.py               Local HTTP interface
    │   └── static/                 HTML, CSS, JavaScript interface
    ├── scripts/                    Dataset download and local model setup
    ├── data/                       Demo plus ignored local dataset snapshot
    ├── tests/                      Offline unit and integration checks
    └── docs/                       Verified event and API requirements
```

Read [the setup guide](track_2a/README.md), [technical report](track_2a/technical_report.md), and [verified challenge requirements](track_2a/docs/event-requirements.md). There is no frontend build, vector database, or training infrastructure. Model weights and downloaded data stay in ignored local directories and outside the submission image.

## Challenge alignment

The CLI accepts both full booklet PDFs (task A) and supplied reference passages (task B), with independent German/French/Italian source and claim languages. It emits the official classes **0 entailment, 1 neutral, 2 contradiction**, source-language quotes, and actual provider token counts plus measured case duration. Support for all nine language pairs is tested at the interface level; **model quality across those pairs is unmeasured**.

The official submission deadline is **16 October 2026 at 12:00 CEST**. The final OST report must be a PDF of at most six pages. This repository currently contains a prototype and the report's Markdown source, not a completed submission. Sources: [OST API guide](https://hackapertus.notion.site/solution-api-guide-ef5b4fec112a834da43101ede56300f5), [event](https://hackapertus.ch/online-hack), [submission page](https://hackapertus.ch/online-hack/submissions).

Based on the [official template](https://github.com/HackApertus/project-template/tree/7f2382275461baf3fa6c8855d157d86abffe9f0e). Source code: Apache-2.0; project documentation: CC-BY-4.0. The imported OST sample retains its original license and attribution; see [data provenance](track_2a/data/README.md).
