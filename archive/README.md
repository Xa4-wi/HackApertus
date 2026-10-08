# Development archive

This directory preserves retired tools, upstream templates, and completed local
experiments. The active application is in `../track_2a/`. Release history is in
[`../VERSION_HISTORY.md`](../VERSION_HISTORY.md); final delivery files are described
in the root [README](../README.md#validation-and-delivery). The final report source
and PDF are directly in `../track_2a/`.

| Location | Contents | Included in Git / delivery? |
| --- | --- | --- |
| `template/track_2a/` | Original organizer README and technical-report template, pinned to commit `7f2382275461baf3fa6c8855d157d86abffe9f0e` | Git only; reference material |
| `track_2a/scripts/build_report.py` | Retired V2 report builder | Git only; historical code |
| `track_2a/scripts/prepare_submission.py`, `track_2a/submission-files.txt`, `track_2a/tests/test_submission_package.py` | Retired generated-export packager, allowlist and associated tests | Git only; historical tooling |
| `track_2a/dependencies/` | Retired optional requirements files, consolidated into the active `requirements-dev.txt` | Git only; historical configuration |
| `legacy-submission/` | Former root submission directory, including its generated project copy and report-review records | Local archive only; superseded by the active Track 2A directory |
| `track_2a/data/ost-sample.jsonl` | Earlier attributed dataset excerpt, used only for inspection | Git only; not inference data |
| `track_2a/reports/` | Report Markdown saved before the documentation cleanup | Local archive only |
| `track_2a/output/` | Completed evaluations, failed experiments, source snapshots, earlier PDFs and their visual checks | Local archive only |
| `relocation-manifest.json` | Original/new locations and file hashes checked during the move | Local archive only |
| `layout-relocation.json` | File hashes documenting the preservation of the former root submission directory | Local archive only |

Completed run directories were moved intact from `track_2a/output/`; their contents
and hashes were preserved. Paths written inside old records describe the original
run environment and are not rewritten. Do not resume a historical run with current
code or present old scores as measurements of the current implementation.

`track_2a/output/v7-final/` contains the current fixed nine-case full-context comparison,
complete prompt/source traces, semantic reviews and real HTTP presentation rehearsal.
Its prefix candidate preserved labels but lost supporting evidence and was rejected.
`track_2a/output/v6-efficiency/` contains the earlier nine-case baseline, five tuning
variants, locked confirmation, paired token/time comparisons and evidence reviews.
The faster candidate failed confirmation and was not made the default.
`track_2a/output/v5-latency-context/` preserves the earlier retrieval measurement.
Despite its name, `track_2a/output/v5-fast-final/` is a rejected citation experiment.
Read the version history for their interpretation.

The evaluation preparation tools can explicitly read archived cohort metadata to
avoid reusing previously tested cases. Inference, Docker builds and the final
source package do not require this archive. New work goes into
`track_2a/output/evaluations/`, not here. Large local archives are intentionally
ignored by Git and excluded from final delivery. Instructions inside archived
records describe their original layout and may name retired export commands.
