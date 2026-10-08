"""Claim checking orchestration and independently checked quote provenance."""

import copy
from dataclasses import replace

from .context import analyze_document
from .llm import request_completion
from .models import (ALLOWED_MODELS, CLASSIFICATIONS, DIMENSIONS, LABELS,
                     MAX_CHECKS, MAX_CLAIM_LENGTH, MAX_CONTEXT_CHARACTERS,
                     ValidationError, overall_label)


def _string(value, name, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValidationError("{} must be nonempty text of at most {} characters.".format(name, limit))
    return value


def _neutral_check(claim, explanation):
    return {"text": claim, "start": 0, "end": len(claim), "dimension": "general",
            "label": "neutral", "explanation": explanation, "evidence": []}


def validate_model_result(claim, result, passages):
    """Validate claim spans and quote provenance, not semantic correctness.

    Resolved checks without valid citations become neutral. Structural errors
    reject the response, avoiding silent parsing of an ambiguous model answer.
    """
    if not isinstance(result, dict):
        raise ValidationError("The model result must be a JSON object.")
    summary = _string(result.get("summary"), "Model summary", 2000)
    raw_checks = result.get("checks")
    if not isinstance(raw_checks, list) or not 1 <= len(raw_checks) <= MAX_CHECKS:
        raise ValidationError("The model must return between 1 and {} checks.".format(MAX_CHECKS))
    source_by_id = {passage["id"]: passage for passage in passages}
    checks, warnings = [], []
    for raw_check in raw_checks:
        if not isinstance(raw_check, dict):
            raise ValidationError("Each model check must be a JSON object.")
        text = _string(raw_check.get("text"), "Check text", MAX_CLAIM_LENGTH)
        start = claim.find(text)
        if start < 0:
            raise ValidationError("The model returned check text that is not an exact substring of the claim.")
        label, dimension = raw_check.get("label"), raw_check.get("dimension")
        if not isinstance(label, str) or label not in LABELS:
            raise ValidationError("The model returned an unknown NLI label.")
        if not isinstance(dimension, str) or dimension not in DIMENSIONS:
            raise ValidationError("The model returned an unknown check dimension.")
        explanation = _string(raw_check.get("explanation"), "Check explanation", 2000)
        raw_evidence = raw_check.get("evidence")
        if not isinstance(raw_evidence, list) or len(raw_evidence) > 12:
            raise ValidationError("Check evidence must be a list of at most 12 quotations.")
        evidence, invalid = [], False
        for citation in raw_evidence:
            if not isinstance(citation, dict):
                invalid = True
                continue
            passage_id, quote = citation.get("passage_id"), citation.get("quote")
            if not isinstance(passage_id, str) or not isinstance(quote, str):
                invalid = True
                continue
            source = source_by_id.get(passage_id)
            if not source or not quote.strip() or len(quote) > 5000 or quote not in source["text"]:
                invalid = True
                continue
            evidence.append({"passage_id": passage_id, "quote": quote})
        if invalid or (label != "neutral" and not evidence):
            label = "neutral"
            explanation = "The model's assessment could not be accepted because its evidence was missing or failed exact source-quote validation."
            warnings.append("A check was changed to neutral because its citations could not be verified.")
        end = start + len(text)
        checks.append({"text": text, "start": start, "end": end,
                       "dimension": dimension, "label": label,
                       "explanation": explanation, "evidence": evidence})
    # NLI labels apply to the whole sentence. Aggregating a contradictory part
    # would be logically unsound for disjunctions and conditional statements.
    if checks[0]["text"] != claim or checks[0]["dimension"] != "general":
        checks.insert(0, _neutral_check(claim, "The model did not return the required whole-claim assessment; the full claim remains unresolved."))
        warnings.append("The required first whole-claim general check was missing; the overall verdict is neutral.")
    overall = overall_label(checks)
    if warnings:
        summary = {
            "contradiction": "The whole-claim assessment contradicts the supplied evidence; some diagnostic checks remain unresolved.",
            "neutral": "The available assessment does not resolve the full claim. Review the unresolved checks and quoted evidence.",
            "entailment": "The assessed claim is supported by the supplied evidence.",
        }[overall]
    return {"overall": overall, "summary": summary, "checks": checks,
            "warnings": list(dict.fromkeys(warnings)), "validation_degraded": bool(warnings)}


def check_claim(proposal, claim, model, mode, settings, *, claim_language="auto"):
    """Assess supplied evidence through Apertus; stored answers are never used."""
    claim = _string(claim, "Claim", MAX_CLAIM_LENGTH)
    if model not in ALLOWED_MODELS:
        raise ValidationError("Select one of the configured Apertus models.")
    if settings is None or not settings.base_url:
        raise ValidationError("Configure an Apertus endpoint before checking a claim.")
    settings.model_for_request(model)
    if mode != "live":
        raise ValidationError("Only live Apertus inference is supported.")
    if claim_language not in ("auto", "de", "fr", "it"):
        raise ValidationError("Claim language must be auto, de, fr or it.")
    if not isinstance(proposal, dict) or not isinstance(proposal.get("passages"), list):
        raise ValidationError("The selected proposal does not contain a passage list.")
    seen_ids = set()
    for passage in proposal["passages"]:
        if not isinstance(passage, dict):
            raise ValidationError("Every source passage must be an object.")
        passage_id = _string(passage.get("id"), "Passage ID", 200)
        _string(passage.get("text"), "Passage text", MAX_CONTEXT_CHARACTERS)
        if passage_id in seen_ids:
            raise ValidationError("Source passage IDs must be unique.")
        seen_ids.add(passage_id)
    passages = copy.deepcopy(proposal["passages"])
    if sum(len(passage["text"]) for passage in passages) > MAX_CONTEXT_CHARACTERS:
        raise ValidationError("The booklet exceeds the 300,000-character prototype context limit. The document was not truncated and no model was called.")
    if not passages:
        raise ValidationError("No readable source passages were supplied. Add a readable booklet before checking a claim.")
    # Task B must retain the supplied reference as its whole source. Fast
    # booklet retrieval does not change the reference-task inference contract.
    inference_settings = (replace(settings, document_strategy="exhaustive")
                          if proposal.get("source_kind") == "reference" else settings)
    response, metrics, processing = analyze_document(
        claim, passages, model, inference_settings, claim_language,
        proposal.get("vote", proposal.get("title", "")), request_completion)
    served_model = settings.model_for_request(model)
    try:
        result = validate_model_result(claim, response, passages)
    except ValidationError as error:
        error.metrics = metrics
        raise
    result["warnings"].append("Exact quotes were checked against the source passages. Quote provenance does not independently verify the model's interpretation.")
    if processing.get("strategy") == "retrieval":
        result["warnings"].append(processing["coverage"])
    if metrics["context_tokens"] is None:
        result["warnings"].append("The endpoint does not report source-context token usage separately; context_tokens is null and context_characters is measured locally.")
    if proposal.get("is_fixture"):
        result["warnings"].append("This proposal is a fictional fixture, not official voting material or an evaluation dataset.")
    result.update({"claim": claim, "model": model, "served_model": served_model,
                   "mode": mode, "passages": passages,
                   "classification": CLASSIFICATIONS[result["overall"]],
                   "claim_language": claim_language, "metrics": metrics,
                   "processing": processing})
    return result
