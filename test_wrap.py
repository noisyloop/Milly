"""test_wrap.py — streaming word-wrap used for model replies in the terminal."""

import io
import unittest

from main import StreamWrapper


def run(chunks, width=20, col=0):
    out = io.StringIO()
    w = StreamWrapper(width, col=col, out=out)
    w.width = width  # allow tiny widths in tests
    for c in chunks:
        w.write(c)
    w.finish()
    return out.getvalue()


class TestStreamWrapper(unittest.TestCase):
    def test_short_text_unchanged(self):
        self.assertEqual(run(["hello ", "there"]), "hello there")

    def test_never_splits_words(self):
        text = run(["the quick brown fox jumps over the lazy dog"], width=12)
        for line in text.split("\n"):
            self.assertLessEqual(len(line), 12)
        self.assertEqual(text.replace("\n", " "), "the quick brown fox jumps over the lazy dog")

    def test_words_split_across_chunks(self):
        self.assertEqual(run(["coff", "ee or ", "tea"], width=8), "coffee\nor tea")

    def test_starting_column_respected(self):
        # "milly> " already takes 7 columns
        self.assertEqual(run(["aaa bbb"], width=10, col=7), "aaa\nbbb")

    def test_model_newlines_and_indent_kept(self):
        self.assertEqual(run(["a\n  b"]), "a\n  b")

    def test_long_word_hard_breaks(self):
        text = run(["x" * 25], width=10)
        self.assertTrue(all(len(l) <= 10 for l in text.split("\n")))
        self.assertEqual(text.replace("\n", ""), "x" * 25)


if __name__ == "__main__":
    unittest.main(verbosity=2)
