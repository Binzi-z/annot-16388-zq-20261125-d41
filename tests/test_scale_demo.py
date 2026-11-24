import unittest

import scale_demo


class ScaleDemoTests(unittest.TestCase):
    def test_generate_update_and_verify_fifty_thousand_paragraphs(self):
        exit_code = scale_demo.main()
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
