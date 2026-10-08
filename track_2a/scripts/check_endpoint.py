#!/usr/bin/env python3
"""Make a real Apertus request through the production JSONL CLI.

Uses the configured endpoint and credentials. This checks one synthetic,
cross-language reference case; it is not an accuracy benchmark.
"""

import argparse
import json
from pathlib import Path
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from claimlens.cli import main as cli_main
from claimlens.config import Settings, load_dotenv
from claimlens.models import ClaimLensError, ValidationError


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        load_dotenv()
        settings = Settings.from_env()
        if not settings.base_url:
            raise ValidationError("Set BASE_URL and, if required, API_KEY before checking the endpoint.")
        case = {
            "id": "endpoint-smoke",
            "reference": {"text": "Die jährliche Gebühr beträgt genau 200 Franken."},
            "claim": {"text": "La redevance annuelle est de 200 francs."},
        }
        print("Checking the configured endpoint with one real Apertus reference prediction.", file=sys.stderr)
        with tempfile.TemporaryDirectory(prefix="claimlens-endpoint-") as directory:
            root = Path(directory)
            input_path, output_path = root / "input.jsonl", root / "predictions.jsonl"
            input_path.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
            status = cli_main(["--input", str(input_path), "--output", str(output_path),
                               "--data-root", str(root)])
            if status:
                return status
            records = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()
                       if line.strip()]
            if len(records) != 1 or records[0].get("id") != case["id"]:
                raise ValidationError("Endpoint check did not produce its expected prediction record.")
            prediction = records[0]
        report = {
            "contract_ok": True,
            "model": settings.model,
            "endpoint_kind": "local" if settings.local_model_configured else "configured_api",
            "label": prediction["label"],
            "label_name": prediction["label_name"],
            "expected_label": 0,
            "matches_synthetic_example": prediction["label"] == 0,
            "metrics": prediction["metrics"],
            "scope": "One synthetic reference case; not a held-out accuracy or PDF evidence evaluation.",
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except ClaimLensError as error:
        print("Endpoint check: " + str(error), file=sys.stderr)
    except (OSError, UnicodeError, ValueError, KeyError):
        print("Endpoint check could not read or validate its temporary prediction files.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
