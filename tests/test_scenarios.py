import unittest

from desens_review.model import Level
from desens_review.review import review_case
from desens_review.scenarios import short_scenarios


class ScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = short_scenarios()
        cls.results = {
            name: review_case(case) for name, case in cls.cases.items()
        }

    def test_every_witness_is_independently_verified(self):
        for name, result in self.results.items():
            with self.subTest(scenario=name):
                for interval in result["may_intervals"]:
                    for key in (
                        "positive_witness",
                        "negative_witness",
                        "lower_watermark_witness",
                    ):
                        witness = interval.get(key)
                        if witness is None:
                            continue
                        verdict = witness["verification"]
                        self.assertTrue(verdict["valid"], verdict["errors"])
                        self.assertTrue(verdict["is_minimum"])
                        self.assertEqual(
                            witness["alignment_cost"], witness["minimum_cost"]
                        )
                for alignment in result.get("all_optimal_alignments", []):
                    self.assertTrue(alignment["verification"]["valid"])
                    self.assertTrue(alignment["verification"]["is_minimum"])

    def test_copied_interval_is_possible_at_both_output_copies(self):
        result = self.results["copied_fragment"]
        self.assertEqual(result["publication_decision"], "BLOCK_POSSIBLE_SENSITIVE")
        self.assertEqual(result["summary"]["optimal_alignment_count"], 2)
        self.assertEqual(result["summary"]["must_sensitive_atoms"], 0)
        self.assertEqual(result["summary"]["may_sensitive_atoms"], 2)
        self.assertEqual(result["may_intervals"][0]["left"], 0)
        self.assertEqual(result["may_intervals"][0]["right"], 2)
        self.assertIsNotNone(result["may_intervals"][0]["positive_witness"])
        self.assertIsNotNone(result["may_intervals"][0]["negative_witness"])

        hull_bounds = {(h["left"], h["right"]) for h in result["hull_intervals"]}
        self.assertEqual(hull_bounds, {(0, 1), (1, 2)})
        self.assertTrue(all(h["necessity"] == "possible" for h in result["hull_intervals"]))

    def test_repeated_interval_and_two_source_level_conflict(self):
        result = self.results["repeated_source_conflict"]
        self.assertEqual(result["summary"]["optimal_alignment_count"], 2)
        self.assertEqual(result["summary"]["level_conflict_count"], 1)
        interval = result["may_intervals"][0]
        self.assertEqual((interval["left"], interval["right"]), (0, 1))
        self.assertEqual(interval["conflicts"][0]["type"], "two_source_level_conflict")
        self.assertEqual(
            interval["conflicts"][0]["effective_levels"],
            [int(Level.PUBLIC), int(Level.SECRET)],
        )
        positive = interval["positive_witness"]
        negative = interval["negative_witness"]
        self.assertEqual(positive["source_index"], 0)
        self.assertEqual(negative["source_index"], 1)
        self.assertEqual(result["publication_decision"], "BLOCK_POSSIBLE_SENSITIVE")

    def test_two_classified_sources_can_conflict_at_different_watermarks(self):
        result = self.results["classified_watermark_conflict"]
        interval = result["may_intervals"][0]
        self.assertEqual(
            interval["conflicts"][0]["effective_levels"],
            [int(Level.CONFIDENTIAL), int(Level.SECRET)],
        )
        self.assertEqual(result["summary"]["level_conflict_count"], 1)
        lower = interval["lower_watermark_witness"]
        self.assertEqual(lower["source_index"], 1)
        self.assertTrue(lower["verification"]["is_minimum"])
        self.assertEqual(
            lower["negates"],
            "higher_watermark_only_interval_remains_classified",
        )
        self.assertEqual(result["publication_decision"], "BLOCK_POSSIBLE_SENSITIVE")

    def test_moved_fragment_has_positive_and_negative_minimum_witness(self):
        result = self.results["moved_fragment"]
        # Crossing-tolerant transport treats a pure reorder as zero-cost.
        self.assertEqual(result["alignment_model"], "transport")
        self.assertEqual(result["alignment"]["optimal_cost"], 0)
        self.assertEqual(result["summary"]["optimal_alignment_count"], 1)
        interval = next(
            i for i in result["must_intervals"] if (i["left"], i["right"]) == (1, 2)
        )
        self.assertEqual(interval["necessity"], "definite")
        self.assertIsNotNone(interval["positive_witness"])
        self.assertIsNotNone(interval["negative_witness"])
        self.assertEqual(interval["positive_witness"]["source_index"], 0)
        self.assertEqual(interval["negative_witness"]["source_index"], 1)
        self.assertEqual(interval["negative_relation"], "outside_left_boundary")
        self.assertTrue(interval["positive_witness"]["verification"]["is_minimum"])
        self.assertTrue(interval["negative_witness"]["verification"]["is_minimum"])

        moved_hull = result["hull_intervals"][0]
        self.assertEqual((moved_hull["left"], moved_hull["right"]), (1, 2))
        self.assertEqual(moved_hull["source_id"], "S-MOVE")
        self.assertEqual(moved_hull["necessity"], "definite")

    def test_split_fragment_reports_complete_hull_and_pieces(self):
        result = self.results["split_fragment"]
        hull = result["hull_intervals"][0]
        self.assertEqual((hull["left"], hull["right"]), (0, 5))
        self.assertTrue(hull["split"])
        self.assertEqual(hull["necessity"], "definite")
        self.assertEqual(len(hull["pieces"]), 3)
        piece_bounds = [(p["left"], p["right"]) for p in hull["pieces"]]
        self.assertEqual(piece_bounds, [(0, 1), (2, 3), (4, 5)])
        self.assertEqual(result["publication_decision"], "BLOCK_POSSIBLE_SENSITIVE")

    def test_scoped_downgrade_respects_declared_source_and_watermark(self):
        result = self.results["scoped_downgrade_watermark"]
        atom = result["atom_risks"][0]
        effective_by_source = {}
        for choice in atom["choices"]:
            for prov in choice["provenances"]:
                effective_by_source[prov["source_id"]] = prov["effective_level"]
        self.assertEqual(effective_by_source["S-DECLARED"], int(Level.INTERNAL))
        self.assertEqual(effective_by_source["S-OTHER"], int(Level.SECRET))
        audit = {a["decl_id"]: a for a in result["downgrade_audit"]}
        self.assertEqual(audit["DG-WATER-1"]["effect"], "active_watermark_cap")
        self.assertEqual(result["publication_decision"], "BLOCK_POSSIBLE_SENSITIVE")

    def test_proxy_downgrade_revocation_restores_blocking(self):
        active = self.results["proxy_downgrade_active"]
        revoked = self.results["proxy_downgrade_revoked"]

        self.assertEqual(active["publication_decision"], "RELEASE")
        active_audit = active["downgrade_audit"][0]
        self.assertEqual(active_audit["effect"], "active_watermark_cap")
        self.assertTrue(active_audit["proxy"])

        self.assertEqual(revoked["publication_decision"], "BLOCK_POSSIBLE_SENSITIVE")
        revoked_audit = revoked["downgrade_audit"][0]
        self.assertEqual(revoked_audit["effect"], "revoked_no_effect")
        self.assertEqual(revoked_audit["revocation_id"], "REVOKE-PROXY-1")
        interval = revoked["may_intervals"][0]
        self.assertIsNotNone(interval["positive_witness"])
        self.assertIsNotNone(interval["negative_witness"])


if __name__ == "__main__":
    unittest.main()
