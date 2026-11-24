import itertools
import unittest

from desens_review.align import (
    Lattice,
    enumerate_optimal_alignments,
    verify_alignment,
)
from desens_review.model import character_atoms


class EnumerationTests(unittest.TestCase):
    def test_copy_has_exactly_two_minimum_alignments(self):
        source = character_atoms("a")
        target = character_atoms("aa")
        alignments = enumerate_optimal_alignments(source, target)

        self.assertEqual(len(alignments), 2)
        self.assertEqual({a.cost for a in alignments}, {1})
        link_sets = {tuple(a.links) for a in alignments}
        self.assertEqual(link_sets, {((0, 0),), ((0, 1),)})
        for alignment in alignments:
            verdict = verify_alignment(source, target, alignment)
            self.assertTrue(verdict["valid"], verdict["errors"])
            self.assertTrue(verdict["is_minimum"])

    def test_repeated_source_has_exactly_two_minimum_alignments(self):
        source = character_atoms("aa")
        target = character_atoms("a")
        alignments = enumerate_optimal_alignments(source, target)

        self.assertEqual(len(alignments), 2)
        self.assertEqual({tuple(a.links) for a in alignments}, {((0, 0),), ((1, 0),)})

    def test_every_short_lattice_matches_complete_enumeration(self):
        alphabet = "ab"
        strings = [
            "".join(chars)
            for length in range(4)
            for chars in itertools.product(alphabet, repeat=length)
        ]
        for source_text in strings:
            for target_text in strings:
                with self.subTest(source=source_text, target=target_text):
                    source = character_atoms(source_text)
                    target = character_atoms(target_text)
                    lattice = Lattice(source, target)
                    alignments = enumerate_optimal_alignments(source, target)

                    self.assertEqual(lattice.total_paths, len(alignments))
                    choices = lattice.choices_for_targets()
                    self.assertEqual(len(choices), len(target))
                    for target_choices in choices:
                        self.assertGreater(len(target_choices), 0)
                        self.assertEqual(
                            sum(ch.through_count for ch in target_choices),
                            lattice.total_paths,
                        )
                        for choice in target_choices:
                            witness = lattice.witness_for_choice(choice)
                            verdict = verify_alignment(source, target, witness)
                            self.assertTrue(verdict["valid"], verdict["errors"])
                            self.assertTrue(verdict["is_minimum"])
                            self.assertEqual(witness.cost, lattice.total_cost)


if __name__ == "__main__":
    unittest.main()
