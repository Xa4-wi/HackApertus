"""Lexical retrieval keeps exact source provenance and safe reusable caches."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from claimlens import retrieval
from claimlens.context import consolidate, source_units


def passage(identifier, text, page=1, language="fr"):
    return {"id": identifier, "text": text, "page": page, "language": language,
            "title": "Official booklet", "attribution": "Source explanation"}


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.cache = Path(self.directory.name) / "cache"
        self.patch = patch.object(retrieval, "CACHE_DIRECTORY", self.cache)
        self.patch.start()
        retrieval._MEMORY_CACHE.clear()

    def tearDown(self):
        retrieval._MEMORY_CACHE.clear()
        self.patch.stop()
        self.directory.cleanup()

    def selected(self, result):
        indexed = {unit["id"]: unit for unit in result["units"]}
        return [indexed[identifier] for identifier in result["ranked_ids"]]

    def test_german_french_italian_rank_topic_above_unrelated_identical_number(self):
        examples = {
            "de": ("Die jährliche Gebühr beträgt 200 Franken.", "Die jährliche Gebühr beträgt 300 Franken.",
                   "Der Ausbau der Nationalstrasse kostet 300 Millionen Franken."),
            "fr": ("La redevance annuelle est de 200 francs.", "La redevance annuelle est de 300 francs.",
                   "La construction de la route coûte 300 millions de francs."),
            "it": ("La tassa annuale ammonta a 200 franchi.", "La tassa annuale ammonta a 300 franchi.",
                   "La costruzione della strada costa 300 milioni di franchi."),
        }
        for language, (source, query, unrelated) in examples.items():
            with self.subTest(language=language):
                passages = [passage("fee", source, 4, language), passage("road", unrelated, 10, language)]
                result = retrieval.search(passages, [query], [], limit=1)
                self.assertEqual(self.selected(result)[0]["passage_id"], "fee")
                self.assertEqual(self.selected(result)[0]["text"], source)

    def test_cross_language_expansion_finds_exact_source_without_translating_evidence(self):
        passages = [passage("other", "La politique agricole prévoit une nouvelle aide aux exploitations.", 4),
                    passage("fee", "La redevance annuelle sera de 200 francs dès 2028.", 20)]
        result = retrieval.search(passages,
            ["Die jährliche Gebühr beträgt 300 Franken.", "La redevance annuelle sera de 300 francs."], [], limit=1)
        self.assertEqual(self.selected(result)[0]["passage_id"], "fee")
        self.assertEqual(self.selected(result)[0]["language"], "fr")
        self.assertIn("200 francs", self.selected(result)[0]["text"])
        self.assertNotIn("Franken", self.selected(result)[0]["text"])

    def test_accents_and_inflections_are_searchable_but_never_rewrite_quotes(self):
        passages = [passage("health", "Les coûts supplémentaires concernent les prestations médicales.", 7),
                    passage("other", "Des règles agricoles différentes sont proposées.", 20)]
        result = retrieval.search(passages, ["cout supplementaire prestation medicale"], [], limit=1)
        self.assertEqual(self.selected(result)[0]["passage_id"], "health")
        self.assertEqual(self.selected(result)[0]["text"], passages[0]["text"])

    def test_vote_is_a_soft_boost_and_cannot_remove_other_relevant_pages(self):
        passages = [passage("first", "Climate Act. The funding amount is 200 million francs.", 4, "de"),
                    passage("second", "The funding amount is 400 million francs for medical services.", 20, "de")]
        result = retrieval.search(passages, ["funding amount million francs"], ["Climate Act"], limit=2)
        self.assertEqual({unit["passage_id"] for unit in self.selected(result)}, {"first", "second"})
        self.assertEqual(self.selected(result)[0]["passage_id"], "first")

    def test_german_ohne_negation_remains_searchable(self):
        passages = [passage("limited", "Die Unterstützung gilt mit Einkommensgrenze.", 4, "de"),
                    passage("unlimited", "Die Unterstützung gilt ohne Einkommensgrenze.", 20, "de")]
        result = retrieval.search(passages, ["Unterstützung ohne Einkommensgrenze"], [], limit=1)
        self.assertEqual(self.selected(result)[0]["passage_id"], "unlimited")
        self.assertIn("ohne", self.selected(result)[0]["text"])

    def test_exact_units_cover_every_character_and_consolidate_on_original_pages(self):
        passages = [passage("page-four", "Avant. La redevance annuelle est de 200 francs.\n" * 60, 4),
                    passage("page-twenty", "Dès 2028 la redevance entre en vigueur.", 20)]
        result = retrieval.search(passages, ["redevance 2028"], [], limit=6)
        self.assertEqual(result["units"], source_units(passages))
        for source in passages:
            units = [unit for unit in result["units"] if unit["passage_id"] == source["id"]]
            self.assertEqual("".join(unit["text"] for unit in units), source["text"])
            for unit in units:
                self.assertEqual(unit["text"], source["text"][unit["start"]:unit["end"]])
                self.assertEqual(unit["page"], source["page"])
        self.assertEqual(len(result["ranked_ids"]), len(set(result["ranked_ids"])))
        self.assertLessEqual(len(result["ranked_ids"]), 6)
        selected = consolidate(passages, result["units"], set(result["ranked_ids"]))
        self.assertEqual({item["page"] for item in selected}, {4, 20})
        for item in selected:
            original = next(source for source in passages if source["id"] == item["id"])
            for span in item["text"].split("\n[... omitted ...]\n"):
                self.assertIn(span, original["text"])

    def test_neighbors_include_cross_page_qualification_without_invented_page_adjacency(self):
        passages = [passage("scope", "Cette catégorie comprend uniquement les personnes déjà assurées.", 4),
                    passage("fee", "La redevance annuelle est de 200 francs.", 5),
                    passage("distant", "Une disposition distincte concerne la construction routière.", 20)]
        result = retrieval.search(passages, ["redevance annuelle"], [], limit=3)
        selected = {unit["passage_id"] for unit in self.selected(result)}
        self.assertIn("fee", selected)
        self.assertIn("scope", selected)
        self.assertNotIn("distant", selected)

    def test_page_diversity_keeps_distributed_matching_facts(self):
        passages = [passage("repeated", "The eligibility benefit description applies to workers.\n" * 100, 4, "de"),
                    passage("amount", "Eligible workers receive a benefit of 200 francs from 2028.", 20, "de")]
        result = retrieval.search(passages, ["eligibility benefit workers 200 2028"], [], limit=6)
        self.assertIn("amount", {unit["passage_id"] for unit in self.selected(result)})
        self.assertLessEqual(len(result["ranked_ids"]), 6)

    def test_cache_memory_and_disk_hits_preserve_identical_rankings(self):
        passages = [passage("fee", "La redevance annuelle est de 200 francs.")]
        first = retrieval.search(passages, ["redevance"], [], limit=1)
        second = retrieval.search(passages, ["redevance"], [], limit=1)
        retrieval._MEMORY_CACHE.clear()
        with patch.object(retrieval, "_build_index", side_effect=AssertionError("Disk cache should be reused")):
            third = retrieval.search(passages, ["redevance"], [], limit=1)
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertTrue(third["cache_hit"])
        self.assertEqual(first["ranked_ids"], third["ranked_ids"])
        self.assertEqual(first["units"], third["units"])

    def test_cache_invalidates_changed_ocr_text_pages_and_metadata(self):
        original = [passage("fee", "La redevance annuelle est de 200 francs.")]
        key = retrieval.search(original, ["redevance"], [], limit=1)["index_key"]
        for field, replacement in (("text", "OCR recovered: la redevance annuelle est de 200 francs."),
                                   ("page", 2), ("language", "it"), ("attribution", "OCR transcription")):
            changed = copy.deepcopy(original)
            changed[0][field] = replacement
            with self.subTest(field=field):
                result = retrieval.search(changed, ["redevance"], [], limit=1)
                self.assertFalse(result["cache_hit"])
                self.assertNotEqual(result["index_key"], key)

    def test_corrupt_and_oversized_disk_cache_recompute_safely(self):
        passages = [passage("fee", "La redevance annuelle est de 200 francs.")]
        original = retrieval.search(passages, ["redevance"], [], limit=1)
        path = self.cache / (original["index_key"] + ".json")
        for corruption in (b"not JSON", b'{"key": "wrong"}', b"x" * 2048):
            path.write_bytes(corruption)
            retrieval._MEMORY_CACHE.clear()
            with self.subTest(corruption=corruption[:20]), patch.object(retrieval, "MAX_CACHE_BYTES", 1024):
                result = retrieval.search(passages, ["redevance"], [], limit=1)
            self.assertFalse(result["cache_hit"])
            self.assertEqual(result["ranked_ids"], original["ranked_ids"])

    def test_cache_checksum_detects_modified_statistics(self):
        passages = [passage("fee", "La redevance annuelle est de 200 francs.")]
        original = retrieval.search(passages, ["redevance"], [], limit=1)
        path = self.cache / (original["index_key"] + ".json")
        envelope = json.loads(path.read_text())
        envelope["index"]["terms"].clear()
        path.write_text(json.dumps(envelope))
        retrieval._MEMORY_CACHE.clear()
        result = retrieval.search(passages, ["redevance"], [], limit=1)
        self.assertFalse(result["cache_hit"])
        self.assertEqual(result["ranked_ids"], original["ranked_ids"])

    def test_read_only_or_unavailable_disk_cache_does_not_block_search(self):
        passages = [passage("fee", "La redevance annuelle est de 200 francs.")]
        with patch.object(Path, "mkdir", side_effect=PermissionError("read-only cache")):
            result = retrieval.search(passages, ["redevance"], [], limit=1)
        self.assertFalse(result["cache_hit"])
        self.assertEqual(self.selected(result)[0]["passage_id"], "fee")
        self.assertFalse(self.cache.exists())

    def test_cache_directory_symlink_is_not_followed(self):
        elsewhere = Path(self.directory.name) / "elsewhere"
        elsewhere.mkdir()
        self.cache.symlink_to(elsewhere, target_is_directory=True)
        result = retrieval.search([passage("fee", "La redevance annuelle est de 200 francs.")], ["redevance"], [], limit=1)
        self.assertEqual(self.selected(result)[0]["passage_id"], "fee")
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_memory_cache_is_bounded_and_returned_units_are_not_cached_answers(self):
        with patch.object(retrieval, "MAX_MEMORY_ENTRIES", 2):
            for number in range(3):
                retrieval.search([passage("fee", "Annual fee {} francs.".format(number))], ["fee"], [], limit=1)
        self.assertEqual(len(retrieval._MEMORY_CACHE), 2)
        source = [passage("fee", "La redevance annuelle est de 200 francs.")]
        first = retrieval.search(source, ["redevance"], [], limit=1)
        first["units"][0]["text"] = "A forged cached answer."
        second = retrieval.search(source, ["redevance"], [], limit=1)
        self.assertEqual(second["units"][0]["text"], source[0]["text"])

    def test_no_query_or_no_match_returns_no_fabricated_evidence(self):
        source = [passage("fee", "La redevance annuelle est de 200 francs.")]
        for queries in ([], ["xylophone zeppelin"]):
            with self.subTest(queries=queries):
                result = retrieval.search(source, queries, [], limit=4)
                self.assertEqual(result["ranked_ids"], [])
                self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(retrieval.search([], ["redevance"], [], limit=4)["units"], [])
        self.assertEqual(retrieval.search(source, ["redevance"], [], limit=0)["ranked_ids"], [])


if __name__ == "__main__":
    unittest.main()
