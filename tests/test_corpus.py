import tempfile
import unittest
from pathlib import Path

from desens_review.corpus import (
    DEFAULT_DOCUMENTS,
    DEFAULT_PARAGRAPHS_PER_DOC,
    generate_corpus,
    update_one_document,
    verify_corpus,
)
from desens_review.model import ReviewCase
from desens_review.corpus import make_paragraph_case
from desens_review.review import compact_markers


class CorpusTests(unittest.TestCase):
    def test_default_configuration_has_at_least_50000_paragraphs(self):
        self.assertGreaterEqual(
            DEFAULT_DOCUMENTS * DEFAULT_PARAGRAPHS_PER_DOC, 50_000
        )

    def test_synthetic_paragraph_round_trips(self):
        case = make_paragraph_case(123)
        restored = ReviewCase.from_dict(case.to_dict())
        self.assertEqual(restored.source_text, case.source_text)
        self.assertEqual(len(restored.spans), len(case.spans))
        self.assertEqual(restored.spans[0].source_id, case.spans[0].source_id)

    def test_long_distance_moved_classified_phrase_is_not_missed(self):
        case = make_paragraph_case(10)  # operation 2: random block move
        marker = compact_markers(case)
        links = {tuple(link) for link in marker["may_links"]}
        self.assertIn((8, 2), links)
        self.assertIn((9, 3), links)
        self.assertEqual(marker["decision"], "BLOCK")
        self.assertTrue(marker["may_intervals"])

    def test_update_one_document_matches_full_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "corpus"
            manifest = generate_corpus(
                root,
                documents=3,
                paragraphs_per_doc=7,
                minimum_paragraphs=0,
            )
            self.assertEqual(manifest["config"]["total_paragraphs"], 21)
            before = verify_corpus(root, minimum_paragraphs=0)
            self.assertTrue(before["ok"], before["errors"])

            local = update_one_document(root, "DOC-0001", paragraph_index=2)
            self.assertEqual(local["local_stats"]["paragraphs"], 7)
            self.assertTrue(local["internal_check"]["stats_match_markers"])
            self.assertTrue(local["internal_check"]["dp_cells_stat_consistent"])
            self.assertGreater(local["local_stats"]["dp_cells"], 0)

            after = verify_corpus(root, minimum_paragraphs=0)
            self.assertTrue(after["ok"], after["errors"])
            self.assertEqual(after["documents_checked"], 3)
            self.assertEqual(after["paragraphs_checked"], 21)


if __name__ == "__main__":
    unittest.main()
