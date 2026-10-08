"""Native retrieval can emit short anchors while public evidence stays complete."""

import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from claimlens.config import Settings
from claimlens.llm import (completion_messages, quote_candidates,
                           request_completion, response_format)
from claimlens.models import DEFAULT_MODEL, ValidationError


CLAIM = "La mesure exige des moyens financiers supplémentaires."
OMISSION = "\n[... omitted ...]\n"
USAGE = {"input_tokens": 1234, "output_tokens": 123, "model_request_attempts": 1}
BODY = ("La nouvelle mesure prévoit des moyens financiers supplémentaires pour "
        "la biodiversité. Le coût annuel est de 240 millions de francs. "
        "Ces moyens financent les mesures des cantons et de la Confédération.")


def settings(mode="prefix", *, local=True):
    base = Settings("http://127.0.0.1:8081/v1", local_model_id="local-apertus") if local else Settings("https://evaluation.example/v1")
    return SimpleNamespace(local_model_configured=base.local_model_configured,
                           model_for_request=base.model_for_request,
                           retrieval_citation_mode=mode)


def passage(text=BODY, identifier="page-7"):
    return {"id": identifier, "page": 7, "language": "fr", "text": text,
            "title": "Voting booklet", "attribution": "Federal Council"}


def enum_quotes(source, configured=None):
    schema = response_format(CLAIM, [source], configured or settings(), retrieved=True)
    return schema["json_schema"]["schema"]["properties"]["evidence"]["items"]["anyOf"][0]["properties"]["quote"]["enum"]


def completion(sources, evidence, configured=None, *, retrieved=True, relation="supported"):
    raw = {"explanation": "The source gives the amount.", "relation": relation,
           "evidence": evidence}
    with patch("claimlens.llm.request_json", return_value=(raw, USAGE)):
        return request_completion(CLAIM, sources, DEFAULT_MODEL, configured or settings(), retrieved=retrieved)


class QuotePrefixTests(unittest.TestCase):
    def test_unique_prefix_finishes_word_between_80_and_160_characters(self):
        source = passage()
        prefix, = enum_quotes(source)
        self.assertTrue(source["text"].startswith(prefix))
        self.assertGreaterEqual(len(prefix), 80)
        self.assertLessEqual(len(prefix), 160)
        self.assertTrue(source["text"][len(prefix)].isspace())
        self.assertLess(len(prefix), len(source["text"]))

    def test_unicode_printed_hyphenation_and_newlines_expand_verbatim(self):
        text = ("7\nLa biodiversità richiede più finanzia-\nmenti per la protezione "
                "dell’ambiente e dei paesaggi. I costi aggiuntivi ammontano a "
                "240 milioni di franchi all’anno. Il testo mantiene accenti e apostrofi.")
        source = passage(text)
        prefix, = enum_quotes(source)
        result, usage = completion([source], [{"passage_id": source["id"], "quote": prefix}])
        self.assertEqual(result["checks"][0]["evidence"], [{"passage_id": source["id"], "quote": text}])
        self.assertEqual(result["checks"][0]["label"], "entailment")
        self.assertEqual(result["evidence_context_expanded"], 1)
        self.assertIs(usage, USAGE)

    def test_prefix_collision_extends_beyond_160_until_unique(self):
        common = "Les communes appliquent les mêmes règles et conditions. " * 4
        first = common + "Le montant est 240 francs chaque année. Une réserve reste disponible."
        second = common + "Le montant est 480 francs chaque année. Une réserve reste disponible."
        source = passage(first + OMISSION + second)
        prefixes = enum_quotes(source)
        self.assertEqual(len(prefixes), 2)
        self.assertTrue(all(len(prefix) > 160 for prefix in prefixes))
        self.assertTrue(all(source["text"].count(prefix) == 1 for prefix in prefixes))
        result, _ = completion([source], [{"passage_id": source["id"], "quote": prefix} for prefix in prefixes])
        self.assertEqual({item["quote"] for item in result["checks"][0]["evidence"]}, {first, second})

    def test_prefix_collision_anywhere_in_body_not_only_at_candidate_start(self):
        repeated = "Cette disposition concerne toutes les communes et prévoit des moyens financiers supplémentaires."
        text = repeated + " Le texte suivant cite à nouveau la règle: " + repeated + " Une précision finale distingue les occurrences."
        source = passage(text)
        prefix, = enum_quotes(source)
        self.assertGreater(len(prefix), len(repeated))
        self.assertEqual(text.count(prefix), 1)

    def test_repeated_complete_candidate_uses_full_quote_without_guessing(self):
        source = passage(BODY + OMISSION + BODY)
        self.assertEqual(enum_quotes(source), [BODY])
        result, _ = completion([source], [{"passage_id": source["id"], "quote": BODY}])
        self.assertEqual(result["checks"][0]["evidence"], [{"passage_id": source["id"], "quote": BODY}])
        self.assertEqual(result["evidence_context_expanded"], 0)

    def test_short_candidate_uses_full_quote(self):
        source = passage("La contribution annuelle est de 240 francs.")
        self.assertEqual(enum_quotes(source), [source["text"]])
        result, _ = completion([source], [{"passage_id": source["id"], "quote": source["text"]}])
        self.assertEqual(result["evidence_context_expanded"], 0)

    def test_distinct_omission_parts_never_expand_across_boundary(self):
        second = "Le comité recommande l’acceptation de la proposition. " + BODY
        source = passage(BODY + OMISSION + second)
        prefixes = enum_quotes(source)
        result, _ = completion([source], [{"passage_id": source["id"], "quote": prefix} for prefix in prefixes])
        quotes = [item["quote"] for item in result["checks"][0]["evidence"]]
        self.assertEqual(set(quotes), {BODY, second})
        self.assertTrue(all(OMISSION not in quote for quote in quotes))

    def test_wrong_passage_id_is_rejected_with_measured_usage(self):
        sources = [passage(), passage("Les cantons refusent cette nouvelle proposition.", "page-8")]
        prefix, = enum_quotes(sources[0])
        with self.assertRaises(ValidationError) as raised:
            completion(sources, [{"passage_id": "page-8", "quote": prefix}])
        self.assertIs(raised.exception.metrics, USAGE)

    def test_invented_unregistered_and_malformed_prefixes_retain_usage(self):
        source = passage()
        prefix, = enum_quotes(source)
        invalid = [None, prefix, [prefix], [{}],
                   [{"passage_id": source["id"], "quote": "Invented statement."}],
                   [{"passage_id": source["id"], "quote": "La nouvelle mesure"}],
                   [{"passage_id": source["id"], "quote": prefix + " inventé"}],
                   [{"passage_id": "missing", "quote": prefix}],
                   [{"passage_id": [], "quote": prefix}],
                   [{"passage_id": source["id"], "quote": []}],
                   [{"passage_id": source["id"], "quote": prefix, "extra": True}]]
        for evidence in invalid:
            with self.subTest(evidence=evidence), self.assertRaises(ValidationError) as raised:
                completion([source], evidence)
            self.assertIs(raised.exception.metrics, USAGE)

    def test_whitespace_normalization_is_not_permitted(self):
        source = passage(BODY.replace(" ", "\n", 3))
        prefix, = enum_quotes(source)
        with self.assertRaises(ValidationError) as raised:
            completion([source], [{"passage_id": source["id"], "quote": prefix.replace("\n", " ")}])
        self.assertIs(raised.exception.metrics, USAGE)

    def test_neutral_empty_evidence_is_unchanged(self):
        result, usage = completion([passage()], [], relation="not_enough_information")
        self.assertEqual(result["checks"][0]["label"], "neutral")
        self.assertEqual(result["checks"][0]["evidence"], [])
        self.assertEqual(result["evidence_context_expanded"], 0)
        self.assertIs(usage, USAGE)

    def test_native_full_mode_and_nonretrieved_schemas_are_unchanged(self):
        source = passage()
        local = Settings("http://127.0.0.1:8081/v1", local_model_id="local-apertus")
        self.assertEqual(response_format(CLAIM, [source], local, retrieved=True),
                         response_format(CLAIM, [source], settings("full"), retrieved=True))
        self.assertEqual(enum_quotes(source, settings("full")), quote_candidates([source], retrieved=True))
        self.assertEqual(response_format(CLAIM, [source], settings("prefix")),
                         response_format(CLAIM, [source], settings("full")))

    def test_only_quote_enums_change_not_messages_or_relation_schema(self):
        source = passage()
        payloads = []
        for mode in ("full", "prefix"):
            configured = settings(mode)
            quote, = enum_quotes(source, configured)
            raw = {"explanation": "The source gives the amount.", "relation": "refuted",
                   "evidence": [{"passage_id": source["id"], "quote": quote}]}
            with patch("claimlens.llm.request_json", return_value=(raw, USAGE)) as request:
                result, _ = request_completion(CLAIM, [source], DEFAULT_MODEL, configured,
                                                claim_language="it", vote="Proposal", retrieved=True)
            self.assertEqual(result["checks"][0]["label"], "contradiction")
            payload = copy.deepcopy(request.call_args.args[0])
            self.assertEqual(payload["messages"], completion_messages(CLAIM, [source], "it", vote="Proposal", retrieved=True))
            citation = payload["response_format"]["json_schema"]["schema"]["properties"]["evidence"]["items"]["anyOf"][0]
            citation["properties"]["quote"]["enum"] = []
            payloads.append(payload)
        self.assertEqual(payloads[0], payloads[1])

    def test_generic_json_provider_keeps_original_exact_anchor_binding(self):
        configured = settings(local=False)
        source = passage()
        self.assertEqual(response_format(CLAIM, [source], configured, retrieved=True), {"type": "json_object"})
        anchor = "Le coût annuel est de 240 millions de francs."
        result, _ = completion([source], [anchor], configured)
        self.assertEqual(result["checks"][0]["evidence"], [{"passage_id": source["id"], "quote": BODY}])
        self.assertEqual(result["evidence_context_expanded"], 1)

    def test_nonretrieved_call_does_not_expand_prefixes(self):
        source = passage()
        anchor = "Le coût annuel est de 240 millions de francs."
        result, _ = completion([source], [anchor], retrieved=False)
        self.assertEqual(result["checks"][0]["evidence"], [{"passage_id": source["id"], "quote": anchor}])
        self.assertNotIn("evidence_context_expanded", result)


if __name__ == "__main__":
    unittest.main()
