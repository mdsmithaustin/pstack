import json
import subprocess
import sys
import unittest
from pathlib import Path

from tally import formats
from tally.__main__ import ranked, tally
from tally.formats import csv_out, html_out, markdown_out

DATA = Path(__file__).parent / "data"
ROOT = Path(__file__).resolve().parents[1]


def corpus_rows(top=20):
    with open(DATA / "corpus.txt", encoding="utf-8") as f:
        return ranked(tally(f), top)


def run_cli(*args):
    done = subprocess.run([sys.executable, "-m", "tally", *args], cwd=ROOT, capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


class CorpusTest(unittest.TestCase):
    def test_top_twenty_matches_the_recorded_counts(self):
        expected = [tuple(pair) for pair in json.loads((DATA / "corpus-top20.json").read_text(encoding="utf-8"))]
        self.assertEqual(corpus_rows(), expected)

    def test_top_cutoff_keeps_the_most_common_words(self):
        self.assertEqual(corpus_rows(top=3), corpus_rows()[:3])


class TextTest(unittest.TestCase):
    def test_text_is_the_original_layout(self):
        self.assertEqual(formats.render("text", [("cat", 2), ("dog", 1)]), "    2  cat\n    1  dog\n")

    def test_text_ignores_a_title(self):
        self.assertEqual(formats.render("text", [("cat", 2)], title="ignored"), "    2  cat\n")


class CsvTest(unittest.TestCase):
    def test_header_then_one_row_per_word(self):
        out = formats.render("csv", [("cat", 2), ("dog", 1)])
        self.assertEqual(out, "rank,word,count\r\n1,cat,2\r\n2,dog,1\r\n")

    def test_round_trip_keeps_commas_and_quotes(self):
        rows = [('say "hi"', 3), ("a,b", 2), ("plain", 1)]
        self.assertEqual(csv_out.parse(formats.render("csv", rows)), rows)

    def test_round_trip_on_the_corpus(self):
        rows = corpus_rows()
        self.assertEqual(csv_out.parse(formats.render("csv", rows)), rows)


class MarkdownTest(unittest.TestCase):
    def test_table_with_heading(self):
        out = formats.render("markdown", [("cat", 2)], title="Top words")
        self.assertEqual(out.splitlines(), ["## Top words", "", markdown_out.HEADER, markdown_out.DELIMITER, "| 1 | cat | 2 |"])

    def test_no_heading_without_a_title(self):
        out = formats.render("markdown", [("cat", 2)])
        self.assertTrue(out.startswith(markdown_out.HEADER))

    def test_empty_report_says_so(self):
        self.assertIn("(no words)", formats.render("markdown", []))

    def test_backslash_is_doubled(self):
        self.assertIn("a\\\\b", formats.render("markdown", [("a\\b", 1)]))


class HtmlTest(unittest.TestCase):
    def test_page_has_title_and_rows(self):
        page = formats.render("html", [("cat", 4), ("dog", 1)], title="Pets")
        self.assertIn("<title>Pets</title>", page)
        self.assertIn('<td class="rank">1</td><td>cat</td><td class="count">4</td>', page)

    def test_default_title(self):
        self.assertIn(f"<h1>{html_out.DEFAULT_TITLE}</h1>", formats.render("html", [("cat", 1)]))

    def test_bar_width_is_a_share_of_the_top_count(self):
        self.assertEqual(html_out.share(4, 4), 100)
        self.assertEqual(html_out.share(1, 4), 25)
        self.assertEqual(html_out.share(1, 1000), 1)

    def test_empty_report_says_so(self):
        self.assertIn("No words found.", formats.render("html", []))

    def test_page_is_complete_for_the_corpus(self):
        page = formats.render("html", corpus_rows(), title="Corpus")
        self.assertTrue(page)


class CliTest(unittest.TestCase):
    def test_default_format_is_text(self):
        code, out, _ = run_cli("sample.txt", "--top", "1")
        self.assertEqual((code, out), (0, "    4  the\n"))

    def test_format_flag_reaches_the_renderer(self):
        code, out, _ = run_cli("sample.txt", "--top", "1", "--format", "csv")
        self.assertEqual((code, out.splitlines()), (0, ["rank,word,count", "1,the,4"]))

    def test_top_below_one_is_refused(self):
        code, _, err = run_cli("sample.txt", "--top", "0")
        self.assertEqual(code, 2)
        self.assertIn("--top must be at least 1", err)


if __name__ == "__main__":
    unittest.main()
