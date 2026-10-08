#!/usr/bin/env python3
"""Prepare the pinned Apertus v1.5 8B text GGUF, verifying its size and SHA256."""

import argparse
import hashlib
import os
import sys
import tempfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODEL_REPOSITORY = "Colby/apertus-v1.5-8b-text-Q4_K_M-GGUF"
MODEL_REVISION = "248ec68a63e219e3f061e4c946fc8a20d63b9975"
MODEL_FILENAME = "apertus-v1.5-8b-text-q4_k_m.gguf"
MODEL_SHA256 = "a037df8d87ff6caacee794ee85f55342f2152e0d359b7389033300c3bee5f299"
MODEL_BYTES = 5_059_027_136
MODEL_URL = (
    "https://huggingface.co/" + MODEL_REPOSITORY + "/resolve/"
    + MODEL_REVISION + "/" + MODEL_FILENAME
)
DEFAULT_OUTPUT = REPOSITORY_ROOT / ".cache/models/apertus-v1.5-8b-q4_k_m.gguf"
DEFAULT_DMR_BLOB = REPOSITORY_ROOT / ".cache/docker-models/blobs/sha256" / MODEL_SHA256
CHUNK_BYTES = 4 * 1024 * 1024


def verify_model(path):
    """Reject incomplete or changed weights before making them available."""
    if not path.is_file():
        raise ValueError("Model file does not exist: " + str(path))
    if path.stat().st_size != MODEL_BYTES:
        raise ValueError("Unexpected model size: " + str(path))
    digest = hashlib.sha256()
    with path.open("rb") as model:
        for chunk in iter(lambda: model.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    if digest.hexdigest() != MODEL_SHA256:
        raise ValueError("Model SHA256 mismatch: " + str(path))


def link_verified_blob(blob, output):
    """Reuse verified Docker Model Runner weights without duplicating 5GB."""
    verify_model(blob)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".model-link-", dir=output.parent) as temporary:
        link = Path(temporary) / "model.gguf"
        # The target must be relative to the final link's parent, not the temp dir.
        link.symlink_to(os.path.relpath(blob.resolve(), output.parent.resolve()))
        os.replace(link, output)


def download_model(output):
    """Publish a download only after verifying every byte; remove partial files."""
    output.parent.mkdir(parents=True, exist_ok=True)
    request = Request(MODEL_URL, headers={"User-Agent": "ClaimLens-local-model/1.0"})
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="." + output.name + ".", suffix=".part", dir=output.parent, delete=False
        ) as model:
            temporary = Path(model.name)
            digest, received, next_progress = hashlib.sha256(), 0, 256 * 1024 * 1024
            with urlopen(request, timeout=60) as response:
                while True:
                    chunk = response.read(CHUNK_BYTES)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > MODEL_BYTES:
                        raise ValueError("Download exceeded the pinned model size.")
                    model.write(chunk)
                    digest.update(chunk)
                    if received >= next_progress:
                        print("Downloaded {:.0%}".format(received / MODEL_BYTES), file=sys.stderr)
                        next_progress = received + 256 * 1024 * 1024
            if received != MODEL_BYTES or digest.hexdigest() != MODEL_SHA256:
                raise ValueError("Downloaded model failed size or SHA256 verification.")
            model.flush()
            os.fsync(model.fileno())
        os.replace(temporary, output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dmr-blob", type=Path, default=DEFAULT_DMR_BLOB,
                        help="Existing DMR blob to verify and reuse before downloading")
    parser.add_argument("--offline", action="store_true", help="Reuse local files only; never download")
    parser.add_argument("--verify-only", action="store_true", help="Verify --output without creating files or downloading")
    args = parser.parse_args(argv)
    # Keep the destination symlink intact: resolve() here would follow its target.
    output = Path(os.path.abspath(args.output.expanduser()))
    blob = args.dmr_blob.expanduser().resolve()
    try:
        if output.exists() or output.is_symlink() or args.verify_only:
            verify_model(output)
            print("Verified model: " + str(output))
        elif blob.is_file():
            print("Verifying cached Docker Model Runner weights...", file=sys.stderr)
            link_verified_blob(blob, output)
            print("Reused verified model: " + str(output))
        elif args.offline:
            raise ValueError("No local model found. Run this script without --offline to download it.")
        else:
            print("Downloading the pinned 5.06GB Apertus v1.5 text GGUF...", file=sys.stderr)
            download_model(output)
            print("Downloaded and verified model: " + str(output))
    except (OSError, URLError, ValueError) as error:
        print("Local model setup failed: " + str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Local model setup interrupted; no partial model was published.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
