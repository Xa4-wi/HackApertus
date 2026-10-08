FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src HOME=/tmp
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils tesseract-ocr tesseract-ocr-deu tesseract-ocr-fra tesseract-ocr-ita \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
# Input and output volumes are supplied by the evaluator. No model download.
ENTRYPOINT ["python", "-m", "claimlens"]

# Only the interactive walkthrough contains prewritten demo judgments.
FROM base AS demo
ENV CLAIMLENS_LIBRARY=/library
COPY data/corpus.json data/corpus.json
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]

# Default build is the predictor: no dataset, gold labels, or demo judgments.
FROM base AS submission
CMD ["--help"]
