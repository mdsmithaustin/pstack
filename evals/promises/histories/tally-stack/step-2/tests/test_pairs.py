import unittest

from tally.__main__ import pair_counts


class PairsTest(unittest.TestCase):
    def test_counts_adjacent_pairs(self):
        self.assertEqual(pair_counts(["a b c"]), {"a b": 1, "b c": 1})

    def test_pairs_ignore_case_like_words(self):
        self.assertEqual(pair_counts(["The cat", "the cat"]), {"the cat": 2})

    def test_single_word_line_has_no_pairs(self):
        self.assertEqual(pair_counts(["alone"]), {})


if __name__ == "__main__":
    unittest.main()
