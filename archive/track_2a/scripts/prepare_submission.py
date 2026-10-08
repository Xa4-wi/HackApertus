#!/usr/bin/env python3
"""Stage an allowlisted source handover alongside the current reviewed report."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[2]
DENIED_PARTS = {"archive", "history", "output", "submission", "dataset", "datasets",
                "model", "models", "weights", "gold", "local", ".git", ".venv", "venv",
                ".cache", ".local", "dist", "build", "__pycache__", "node_modules",
                ".aws", ".codex", ".agents"}
DENIED_SUFFIXES = {".gguf", ".safetensors", ".bin", ".ckpt", ".pt", ".pth", ".arrow",
                   ".parquet", ".jsonl", ".pdf", ".pyc", ".pyo"}
HANDOVER_README = """# ClaimLens — Hack Apertus Track 2A

Start with [the application guide](track_2a/README.md) for setup, the local
Apertus model, the prediction CLI and the input/output contract.
For the two-minute presentation, use the [timed script](track_2a/docs/video-script.md)
and [recording walkthrough](track_2a/docs/presentation-walkthrough.md).

From this directory:

```sh
make run                 # build and start the application
make submission          # build the linux/amd64 judging image
make verify-submission   # verify the image contract
```

The final technical report is delivered separately as `technical_report.pdf`.
This copy contains the active application, setup tools, tests and documentation.
Archives, version history, evaluation outputs, downloaded data, model weights,
credentials and local environments are excluded. Configure your own `.env`
using `track_2a/.env.example`; follow the application guide before starting.
"""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def plain_path(root, relative):
    """Reject symlink files and directories before reading any staged inputs."""
    path = root
    for part in PurePosixPath(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Symlinks are not allowed: {}".format(path))
    return path


def read_object(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object: {}".format(path))
    return value


def approved_sources(root):
    allowlist = plain_path(root, "track_2a/submission-files.txt")
    raw = allowlist.read_bytes()
    sources, seen = [], set()
    for line in raw.decode("utf-8").splitlines():
        name = line.strip()
        if not name or name.startswith("#"):
            continue
        relative = PurePosixPath(name)
        if (relative.is_absolute() or ".." in relative.parts or "\\" in name
                or str(relative) != name or name in (".", "README.md")):
            raise ValueError("Invalid allowlist path: {}".format(name))
        parts = {part.casefold() for part in relative.parts}
        if (parts & DENIED_PARTS or "version_history.md" in parts
                or relative.suffix.casefold() in DENIED_SUFFIXES
                or any(part.startswith(".env") and part != ".env.example" for part in parts)
                or ("data" in parts and name != "track_2a/data/README.md")):
            raise ValueError("Excluded content in allowlist: {}".format(name))
        if name.casefold() in seen:
            raise ValueError("Duplicate allowlist path: {}".format(name))
        seen.add(name.casefold())
        source = plain_path(root, name)
        if not source.is_file():
            raise ValueError("Allowlisted source is missing or not a file: {}".format(name))
        sources.append((name, source))
    if not sources:
        raise ValueError("The submission allowlist is empty.")
    return sources, digest(raw)


def verified_report(root):
    report = plain_path(root, "submission/technical_report.pdf")
    build = read_object(plain_path(root, "submission/technical_report.build.json"))
    review = read_object(plain_path(root, "submission/technical_report.visual-review.json"))
    source_hash = digest(plain_path(root, "track_2a/technical_report.md").read_bytes())
    builder_hash = digest(plain_path(root, "track_2a/scripts/build_submission_report.py").read_bytes())
    pdf_hash = digest(report.read_bytes())
    expected = {"source_sha256": source_hash, "builder_sha256": builder_hash, "pdf_sha256": pdf_hash}
    if any(build.get(key) != value for key, value in expected.items()):
        raise ValueError("Report build metadata is stale; rebuild the current technical report.")
    pages = build.get("pages")
    if type(pages) is not int or not 1 <= pages <= 6:
        raise ValueError("The report must contain between one and six pages.")
    reviewed = review.get("pages_visually_reviewed")
    if (review.get("verdict") != "pass" or review.get("source_sha256") != source_hash
            or review.get("pdf_sha256") != pdf_hash or type(review.get("pages")) is not int
            or review["pages"] != pages or not isinstance(reviewed, list)
            or any(type(page) is not int for page in reviewed) or sorted(reviewed) != list(range(1, pages + 1))):
        raise ValueError("A current passing visual review of every report page is required.")
    return {**expected, "pages": pages}


def project_hashes(project):
    hashes = {}
    for path in sorted(project.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlink in existing handover: {}".format(path))
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("Unexpected file type in existing handover: {}".format(path))
        hashes["project/" + path.relative_to(project).as_posix()] = digest(path.read_bytes())
    return hashes


def verify_previous(submission):
    project, manifest = submission / "project", submission / "manifest.json"
    if project.is_symlink() or manifest.is_symlink():
        raise ValueError("Symlinks are not allowed in the handover destination.")
    if not project.exists() and not manifest.exists():
        return
    if not project.is_dir() or not manifest.is_file():
        raise ValueError("Existing handover lacks its project or manifest; preserve it before regenerating.")
    files = read_object(manifest).get("files")
    if not isinstance(files, dict):
        raise ValueError("Existing handover manifest has no valid file inventory.")
    expected = {name: value for name, value in files.items() if name.startswith("project/")}
    if not expected or project_hashes(project) != expected:
        raise ValueError("Existing handover source was changed, removed or extended; preserve those edits before regenerating.")


def prepare(root=ROOT):
    root = Path(root).resolve()
    submission = plain_path(root, "submission")
    sources, allowlist_hash = approved_sources(root)
    report = verified_report(root)
    verify_previous(submission)
    submission.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".handover-", dir=submission) as temporary:
        stage = Path(temporary)
        project = stage / "project"
        project.mkdir()
        for name, source in sources:
            destination = project / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        (project / "README.md").write_text(HANDOVER_README, encoding="utf-8")
        files = project_hashes(project)
        files["technical_report.pdf"] = report["pdf_sha256"]
        manifest = {"schema_version": 1, "files": files, "report": report,
                    "allowlist_sha256": allowlist_hash}
        staged_manifest = stage / "manifest.json"
        staged_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if verified_report(root) != report or digest((root / "track_2a/submission-files.txt").read_bytes()) != allowlist_hash:
            raise ValueError("The report or allowlist changed during staging; retry from stable inputs.")
        verify_previous(submission)
        destination, backup = submission / "project", stage / "previous-project"
        installed = False
        try:
            if destination.exists():
                destination.replace(backup)
            project.replace(destination)
            installed = True
            staged_manifest.replace(submission / "manifest.json")
        except OSError:
            if installed:
                shutil.rmtree(destination)
            if backup.exists():
                backup.replace(destination)
            raise
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root")
    args = parser.parse_args()
    try:
        manifest = prepare(args.root)
    except (OSError, ValueError) as error:
        parser.exit(2, "Handover error: {}\n".format(error))
    print("Staged {} source files and the reviewed report in submission/.".format(len(manifest["files"]) - 1))


if __name__ == "__main__":
    main()
