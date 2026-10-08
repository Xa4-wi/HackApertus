"""Native prefix citations prefer substantial text without hiding source facts."""

from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from claimlens import llm
from claimlens.config import Settings
from claimlens.models import DEFAULT_MODEL, ValidationError


CONFIGURED = Settings("http://localhost:8081/v1", local_model_id="local-apertus",
                      retrieval_citation_mode="prefix")
CLAIM = "Le financement annuel est de 240 millions de francs."
BODY = ("La nouvelle proposition prévoit des moyens financiers supplémentaires pour la protection "
        "de la biodiversité et des paysages en Suisse. Les moyens annuels supplémentaires sont "
        "de 240 millions de francs. Ils financent des mesures des cantons et de la Confédération.")
FOOTER = "Le Conseil fédéral et le Parlement recommandent de rejeter la proposition."
OMISSION = "\n[... omitted ...]\n"
USAGE = {"input_tokens": 500, "output_tokens": 35, "model_request_attempts": 1}


def passage(text, identifier="body", page=7):
    return {"id": identifier, "page": page, "language": "fr", "text": text}


def schema(passages, settings=CONFIGURED, *, retrieved=True, module=llm):
    return module.response_format(CLAIM, passages, settings, retrieved=retrieved)["json_schema"]["schema"]


def aliases(passages):
    branches = schema(passages)["properties"]["evidence"]["items"]["anyOf"]
    return {branch["properties"]["passage_id"]["const"]: branch["properties"]["quote"]["enum"]
            for branch in branches}


def complete(passages, evidence, settings=CONFIGURED, *, retrieved=True, module=llm):
    raw = {"relation": "supported" if evidence else "not_enough_information",
           "explanation": "Synthetic evidence selection test.", "evidence": evidence}
    with patch.object(module, "request_json", return_value=(raw, USAGE)) as request:
        result, usage = module.request_completion(CLAIM, passages, DEFAULT_MODEL, settings,
                                                 claim_language="de", vote="Proposal", retrieved=retrieved)
    return result, usage, request.call_args.args[0]


class BodyQuotePrefixTests(unittest.TestCase):
    def test_short_footer_page_is_excluded_when_another_page_has_body_text(self):
        passages = [passage(FOOTER, "footer", 3), passage(BODY)]
        eligible = aliases(passages)
        self.assertEqual(set(eligible), {"body"})
        self.assertTrue(all(BODY.startswith(prefix) for prefix in eligible["body"]))
        # Thresholds apply to the full citation, not the shortened decoder alias.
        self.assertLess(len(eligible["body"][0]), 200)

    def test_short_omission_fragment_is_removed_within_the_same_page(self):
        source = passage(FOOTER + OMISSION + BODY)
        self.assertEqual(aliases([source]), aliases([passage(BODY)]))
        prefix, = aliases([source])["body"]
        result, usage, _ = complete([source], [{"passage_id": "body", "quote": prefix}])
        self.assertEqual(result["checks"][0]["evidence"], [{"passage_id": "body", "quote": BODY}])
        self.assertNotIn(OMISSION, result["checks"][0]["evidence"][0]["quote"])
        self.assertEqual(result["evidence_context_expanded"], 1)
        self.assertIs(usage, USAGE)

    def test_all_short_candidates_remain_available(self):
        passages = [passage(FOOTER, "one"), passage("La taxe est de 200 francs.", "two")]
        self.assertEqual(aliases(passages), {"one": [FOOTER], "two": ["La taxe est de 200 francs."]})

    def test_each_threshold_is_required_and_exact_boundary_is_included(self):
        exactly_200_and_25 = "a " * 24 + "b" * 152
        self.assertEqual((len(exactly_200_and_25), len(exactly_200_and_25.split())), (200, 25))
        few_characters = "mot " * 30
        few_words = "longueproposition " * 20
        passages = [passage(exactly_200_and_25, "boundary"), passage(few_characters, "small"),
                    passage(few_words, "few")]
        self.assertEqual(set(aliases(passages)), {"boundary"})
        self.assertEqual(set(aliases(passages[1:])), {"small", "few"})

    def test_dropped_page_alias_is_rejected_with_complete_provider_usage(self):
        sources = [passage(FOOTER, "footer"), passage(BODY)]
        for quote in (FOOTER, next(iter(llm._context_quote_prefixes(sources[0])))):
            with self.subTest(quote=quote), self.assertRaises(ValidationError) as raised:
                complete(sources, [{"passage_id": "footer", "quote": quote}])
            self.assertIs(raised.exception.metrics, USAGE)

    def test_dropped_same_page_alias_cannot_enter_through_the_binder(self):
        source = passage(FOOTER + OMISSION + BODY)
        self.assertIn(FOOTER, llm._context_quote_prefixes(source))
        with self.assertRaises(ValidationError) as raised:
            complete([source], [{"passage_id": "body", "quote": FOOTER}])
        self.assertIs(raised.exception.metrics, USAGE)

    def test_classifier_messages_source_text_and_relation_schema_are_identical(self):
        sources = [passage(FOOTER, "footer"), passage(BODY)]
        prefix, = aliases(sources)["body"]
        evidence = [{"passage_id": "body", "quote": prefix}]
        actual, _, actual_payload = complete(sources, evidence)
        previous, _, previous_payload = complete(sources, [{"passage_id": "body", "quote": BODY}],
                                                 replace(CONFIGURED, retrieval_citation_mode="full"))
        self.assertEqual(actual["checks"], previous["checks"])
        self.assertEqual(actual_payload["messages"], previous_payload["messages"])
        supplied = json.loads(actual_payload["messages"][1]["content"])
        self.assertEqual([item["text"] for item in supplied["passages"]], [FOOTER, BODY])
        actual_schema = actual_payload.pop("response_format")["json_schema"]["schema"]
        previous_schema = previous_payload.pop("response_format")["json_schema"]["schema"]
        actual_schema["properties"].pop("evidence")
        previous_schema["properties"].pop("evidence")
        self.assertEqual(actual_schema, previous_schema)
        self.assertEqual(actual_payload, previous_payload)

    def test_native_full_and_nonretrieved_modes_keep_short_candidates(self):
        sources = [passage(FOOTER, "footer"), passage(BODY)]
        for settings, retrieved in ((replace(CONFIGURED, retrieval_citation_mode="full"), True),
                                    (CONFIGURED, False)):
            with self.subTest(mode=settings.retrieval_citation_mode, retrieved=retrieved):
                branches = schema(sources, settings, retrieved=retrieved)["properties"]["evidence"]["items"]["anyOf"]
                self.assertEqual({item["properties"]["passage_id"]["const"] for item in branches}, {"footer", "body"})
                self.assertEqual(branches[0]["properties"]["quote"]["enum"], [FOOTER])
                evidence = [{"passage_id": "footer", "quote": FOOTER}]
                result, usage, _ = complete(sources, evidence, settings, retrieved=retrieved)
                self.assertEqual(result["checks"][0]["evidence"], evidence)
                self.assertIs(usage, USAGE)
        self.assertEqual(schema(sources, CONFIGURED, retrieved=False),
                         schema(sources, replace(CONFIGURED, retrieval_citation_mode="full"), retrieved=False))

    def test_generic_json_mode_keeps_short_exact_footer_binding(self):
        settings = replace(CONFIGURED, base_url="https://evaluation.example/v1")
        sources = [passage(FOOTER, "footer"), passage(BODY)]
        self.assertEqual(llm.response_format(CLAIM, sources, settings, retrieved=True), {"type": "json_object"})
        result, usage, payload = complete(sources, [FOOTER], settings)
        self.assertEqual(result["checks"][0]["evidence"], [{"passage_id": "footer", "quote": FOOTER}])
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertIs(usage, USAGE)
        self.assertEqual((result, usage, payload),
                         complete(sources, [FOOTER], replace(settings, retrieval_citation_mode="full")))

    def test_empty_candidates_allow_only_empty_evidence_without_invalid_schema(self):
        for sources in ([], [passage(" \n\t")]):
            with self.subTest(sources=sources):
                evidence_schema = schema(sources)["properties"]["evidence"]
                self.assertEqual(evidence_schema["type"], "array")
                self.assertEqual(evidence_schema["maxItems"], 0)
                self.assertNotIn("anyOf", evidence_schema["items"])
                self.assertNotIn("enum", evidence_schema["items"])
                result, usage, _ = complete(sources, [])
                self.assertEqual(result["checks"][0]["evidence"], [])
                self.assertIs(usage, USAGE)
                with self.assertRaises(ValidationError) as raised:
                    complete(sources, [{"passage_id": "body", "quote": "invented"}])
                self.assertIs(raised.exception.metrics, USAGE)

    def test_schema_and_binder_reuse_one_eligible_mapping_per_request(self):
        sources = [passage(FOOTER, "footer"), passage(BODY)]
        prefix, = aliases(sources)["body"]
        with patch.object(llm, "_eligible_context_quote_prefixes", wraps=llm._eligible_context_quote_prefixes) as eligible:
            complete(sources, [{"passage_id": "body", "quote": prefix}])
        eligible.assert_called_once_with(sources)

    def test_page_order_changes_neither_global_eligibility_nor_source_identity(self):
        sources = [passage(FOOTER, "footer"), passage(BODY), passage(BODY, "repeated", 8)]
        eligible = aliases(sources)
        self.assertEqual(set(eligible), {"body", "repeated"})
        self.assertEqual(eligible, aliases(list(reversed(sources))))
        for identifier, prefixes in eligible.items():
            result, _, _ = complete(sources, [{"passage_id": identifier, "quote": prefixes[0]}])
            self.assertEqual(result["checks"][0]["evidence"], [{"passage_id": identifier, "quote": BODY}])


if __name__ == "__main__":
    unittest.main()
