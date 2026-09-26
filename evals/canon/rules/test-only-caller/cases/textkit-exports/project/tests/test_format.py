import unittest

from textkit.format import banner, slugify, truncate


class SlugifyTest(unittest.TestCase):
    def test_collapses_punctuation_and_spaces(self):
        self.assertEqual(slugify("  Linen Shirt, Blue! "), "linen-shirt-blue")


class TruncateTest(unittest.TestCase):
    def test_short_text_is_unchanged(self):
        self.assertEqual(truncate("Mug", 10), "Mug")

    def test_long_text_ends_with_suffix(self):
        self.assertEqual(truncate("Handmade ceramic travel mug", 12), "Handmade...")


class BannerTest(unittest.TestCase):
    def test_centers_text_in_stars(self):
        self.assertEqual(banner("Sale", 12), "*** Sale ***")

    def test_wide_text_is_not_padded(self):
        self.assertEqual(banner("Summer clearance", 10), " Summer clearance ")


if __name__ == "__main__":
    unittest.main()
