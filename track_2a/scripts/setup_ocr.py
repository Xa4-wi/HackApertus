#!/usr/bin/env python3
"""Install only the three pinned OCR language files into the local cache."""

import hashlib
import os
from pathlib import Path
from urllib.request import urlopen

REVISION = "65727574dfcd264acbb0c3e07860e4e9e9b22185"
HASHES = {
    "deu": "19d219bbb6672c869d20a9636c6816a81eb9a71796cb93ebe0cb1530e2cdb22d",
    "fra": "ced037562e8c80c13122dece28dd477d399af80911a28791a66a63ac1e3445ca",
    "ita": "b8f89e1e785118dac4d51ae042c029a64edb5c3ee42ef73027a6d412748d8827",
}


def main():
    root = Path(__file__).resolve().parents[2] / ".cache" / "tessdata"
    root.mkdir(parents=True, exist_ok=True)
    for language, digest in HASHES.items():
        path = root / (language + ".traineddata")
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            print("Verified " + language)
            continue
        url = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{}/{}.traineddata".format(REVISION, language)
        with urlopen(url, timeout=60) as response:
            data = response.read(10_000_001)
        if len(data) > 10_000_000 or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("OCR language checksum verification failed: " + language)
        temporary = path.with_suffix(".part")
        temporary.write_bytes(data)
        os.replace(temporary, path)
        print("Downloaded and verified " + language)
    print("OCR language files: " + str(root))


if __name__ == "__main__":
    main()
