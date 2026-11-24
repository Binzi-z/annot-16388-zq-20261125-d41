import contextlib
import io
import json
import unittest

from desens_review.cli import main


class CliTests(unittest.TestCase):
    def test_enumerate_command_emits_verified_alignments(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(
                [
                    "enumerate",
                    "--source",
                    "aa",
                    "--target",
                    "a",
                    "--alignment-model",
                    "transport",
                ]
            )
        self.assertEqual(code, 0)
        data = json.loads(buffer.getvalue())
        self.assertEqual(data["alignment_count"], 2)
        self.assertEqual(data["lattice_alignment_count"], 2)
        for alignment in data["alignments"]:
            self.assertTrue(alignment["verification"]["valid"])
            self.assertTrue(alignment["verification"]["is_minimum"])


if __name__ == "__main__":
    unittest.main()
