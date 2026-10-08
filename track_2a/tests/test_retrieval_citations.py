"""Retrieved citations retain context without changing other inference paths."""

import unittest
from unittest.mock import patch

from claimlens.config import Settings
from claimlens.llm import (SYSTEM_PROMPT, completion_messages, quote_candidates,
                           request_completion, response_format)
from claimlens.models import DEFAULT_MODEL


LOCAL = Settings("http://127.0.0.1:8080/v1", local_model_id="local-apertus")
REMOTE = Settings("https://evaluation.example/v1")
CLAIM = "La contribution annuelle est de 240 francs."
OMISSION = "\n[... omitted ...]\n"


def passage(text, identifier="page-3"):
    return {"id": identifier, "page": 3, "language": "fr", "text": text}


def schema_quotes(response):
    return response["json_schema"]["schema"]["properties"]["evidence"]["items"]["anyOf"][0]["properties"]["quote"]["enum"]


class RetrievalCitationTests(unittest.TestCase):
    def test_context_excludes_standalone_footer_and_body_line_fragments(self):
        body = ("La contribution annuelle est de 240 francs.\n"
                "Elle finance les dépenses prévues par la nouvelle mesure.\n") * 5
        footer = "Le texte de cette page est fourni par le comité."
        source = passage(body + footer)
        candidates = quote_candidates([source], retrieved=True)
        self.assertEqual(candidates, [source["text"]])
        self.assertNotIn(footer, candidates)
        self.assertNotIn(CLAIM, candidates)

    def test_tiny_trailing_fragment_merges_with_contiguous_preceding_context(self):
        body = "Le montant annuel est fixé à 240 francs. " * 22
        footer = "Ce texte est fourni par les auteurs de la proposition."
        source = passage(body + footer)
        self.assertGreater(len(source["text"]), 900)
        self.assertLess(len(source["text"]), 1200)
        self.assertEqual(quote_candidates([source], retrieved=True), [source["text"]])

    def test_printed_hyphenation_stays_inside_context_quote(self):
        text = ("La nuova misura richiede un finanzia-\nmento supplementare. "
                "La spesa annua aumenta di 240 franchi.\nLa proposta riguarda tutti i Comuni.")
        candidates = quote_candidates([passage(text)], retrieved=True)
        self.assertEqual(candidates, [text])
        self.assertNotIn("La nuova misura richiede un finanzia-", candidates)

    def test_omission_boundaries_are_never_crossed_even_for_short_fragments(self):
        first = "La contribution annuelle est fixée à 240 francs."
        second = "Le comité est responsable de ce texte."
        source = passage(first + OMISSION + second)
        candidates = quote_candidates([source], retrieved=True)
        self.assertEqual(set(candidates), {first, second})
        self.assertTrue(all(OMISSION not in quote for quote in candidates))

    def test_isolated_short_source_remains_citable(self):
        text = "Comité: Association des communes."
        self.assertEqual(quote_candidates([passage(text)], retrieved=True), [text])

    def test_long_context_candidates_are_bounded_exact_source_spans(self):
        text = "Die jährliche Gebühr beträgt 240 Franken unter den genannten Bedingungen.\n" * 60
        candidates = quote_candidates([passage(text)], retrieved=True)
        self.assertTrue(candidates)
        self.assertTrue(all(120 <= len(quote) <= 1200 and quote in text for quote in candidates))

    def test_default_schema_retains_original_sentence_candidates(self):
        first = "Die jährliche Gebühr beträgt für alle Haushalte 240 Franken."
        second = "Diese Bestimmung gilt ab dem kommenden Kalenderjahr für alle Gemeinden."
        source = passage(first + "\n" + second)
        original = response_format(CLAIM, [source], LOCAL)
        explicit = response_format(CLAIM, [source], LOCAL, retrieved=False)
        self.assertEqual(original, explicit)
        self.assertEqual(set(schema_quotes(original)), {first, second, source["text"]})
        contextual = response_format(CLAIM, [source], LOCAL, retrieved=True)
        self.assertEqual(schema_quotes(contextual), [source["text"]])
        original["json_schema"]["schema"]["properties"]["evidence"] = None
        contextual["json_schema"]["schema"]["properties"]["evidence"] = None
        self.assertEqual(original, contextual)

    def test_retrieval_instruction_does_not_change_other_prompts(self):
        source = passage(CLAIM)
        normal = completion_messages(CLAIM, [source])
        self.assertEqual(normal[0]["content"], SYSTEM_PROMPT)
        exhaustive = completion_messages(CLAIM, [source], consolidated=True)
        self.assertNotIn("contextual body quotations", exhaustive[0]["content"])
        retrieved = completion_messages(CLAIM, [source], retrieved=True)
        self.assertIn("contextual body quotations", retrieved[0]["content"])
        self.assertEqual(normal[1], retrieved[1])

    def test_request_forwards_contextual_schema_and_expands_exact_remote_anchor(self):
        source = passage(CLAIM + "\nLe comité est responsable de ce texte.")
        raw = {"explanation": "The source states the amount.", "relation": "supported",
               "evidence": [CLAIM]}
        metrics = {"input_tokens": 100, "output_tokens": 20}
        for settings in (LOCAL, REMOTE):
            with self.subTest(local=settings.local_model_configured), patch(
                    "claimlens.llm.request_json", return_value=(raw, metrics)) as request:
                result, returned_metrics = request_completion(
                    CLAIM, [source], DEFAULT_MODEL, settings, retrieved=True)
            transmitted = request.call_args.args[0]
            if settings.local_model_configured:
                self.assertEqual(schema_quotes(transmitted["response_format"]), [source["text"]])
            else:
                self.assertEqual(transmitted["response_format"], {"type": "json_object"})
            # Expansion retains the exact anchor within the same original source.
            self.assertEqual(result["checks"][0]["evidence"],
                             [{"passage_id": source["id"], "quote": source["text"]}])
            self.assertEqual(result["evidence_context_expanded"], 1)
            self.assertIn(CLAIM, result["checks"][0]["evidence"][0]["quote"])
            self.assertEqual(returned_metrics, metrics)

    def test_remote_footer_expansion_preserves_label_and_same_passage(self):
        footer = "Le comité est responsable de ce texte."
        source = passage(CLAIM + "\n" + footer)
        raw = {"explanation": "Synthetic attribution.", "relation": "refuted",
               "evidence": [{"passage_id": source["id"], "quote": footer}]}
        with patch("claimlens.llm.request_json", return_value=(raw, {})):
            result, _ = request_completion(CLAIM, [source], DEFAULT_MODEL, REMOTE, retrieved=True)
        check = result["checks"][0]
        self.assertEqual(check["label"], "contradiction")
        self.assertEqual(check["evidence"], [{"passage_id": source["id"], "quote": source["text"]}])
        self.assertEqual(result["evidence_context_expanded"], 1)

    def test_wrong_id_invented_and_ambiguous_quotes_are_not_repaired(self):
        sources = [passage(CLAIM + "\nPremière page."), passage(CLAIM + "\nAutre page.", "page-4")]
        evidence = [{"passage_id": "page-4", "quote": "Première page."},
                    {"passage_id": "unknown", "quote": CLAIM},
                    {"passage_id": "page-3", "quote": "La contribution annuelle est de 300 francs."},
                    CLAIM]
        raw = {"explanation": "Invalid citations.", "relation": "supported", "evidence": evidence}
        with patch("claimlens.llm.request_json", return_value=(raw, {})):
            result, _ = request_completion(CLAIM, sources, DEFAULT_MODEL, REMOTE, retrieved=True)
        self.assertEqual(result["checks"][0]["evidence"], evidence)
        self.assertEqual(result["evidence_context_expanded"], 0)

    def test_expansion_does_not_cross_omissions_or_choose_between_repeated_anchors(self):
        first = "Le comité est responsable de ce texte."
        source = passage(first + OMISSION + CLAIM + "\n" + CLAIM)
        evidence = [{"passage_id": source["id"], "quote": first},
                    {"passage_id": source["id"], "quote": CLAIM}]
        raw = {"explanation": "Synthetic citation.", "relation": "supported", "evidence": evidence}
        with patch("claimlens.llm.request_json", return_value=(raw, {})):
            result, _ = request_completion(CLAIM, [source], DEFAULT_MODEL, REMOTE, retrieved=True)
        self.assertEqual(result["checks"][0]["evidence"], evidence)
        self.assertEqual(result["evidence_context_expanded"], 0)

    def test_nonretrieved_remote_quote_is_not_expanded(self):
        source = passage(CLAIM + "\nLe comité est responsable de ce texte.")
        raw = {"explanation": "The source states the amount.", "relation": "supported", "evidence": [CLAIM]}
        with patch("claimlens.llm.request_json", return_value=(raw, {})):
            result, _ = request_completion(CLAIM, [source], DEFAULT_MODEL, REMOTE)
        self.assertEqual(result["checks"][0]["evidence"], [{"passage_id": source["id"], "quote": CLAIM}])
        self.assertNotIn("evidence_context_expanded", result)

if __name__ == "__main__":
    unittest.main()
