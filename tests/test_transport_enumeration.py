import itertools
import unittest

from desens_review.model import character_atoms
from desens_review.transport import (
    TransportLattice,
    enumerate_transport_alignments,
)


class TransportEnumerationTests(unittest.TestCase):
    def test_pure_reorder_is_zero_cost_and_crossing(self):
        source = character_atoms("ab")
        target = character_atoms("ba")
        lattice = TransportLattice(source, target)
        alignments = enumerate_transport_alignments(source, target)

        self.assertEqual(lattice.total_cost, 0)
        self.assertEqual(len(alignments), 1)
        self.assertEqual(alignments[0].links, [(1, 0), (0, 1)])
        verdict = lattice.verify_alignment(alignments[0])
        self.assertTrue(verdict["valid"], verdict["errors"])
        self.assertTrue(verdict["is_minimum"])

    def test_every_short_transport_lattice_matches_enumeration(self):
        strings = [
            "".join(chars)
            for length in range(4)
            for chars in itertools.product("ab", repeat=length)
        ]
        for source_text in strings:
            for target_text in strings:
                with self.subTest(source=source_text, target=target_text):
                    source = character_atoms(source_text)
                    target = character_atoms(target_text)
                    lattice = TransportLattice(source, target)
                    alignments = enumerate_transport_alignments(source, target)

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
                            verdict = lattice.verify_alignment(witness)
                            self.assertTrue(verdict["valid"], verdict["errors"])
                            self.assertTrue(verdict["is_minimum"])


if __name__ == "__main__":
    unittest.main()
