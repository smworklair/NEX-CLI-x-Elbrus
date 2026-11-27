"""File excerpt window for the agent: pure functions from code_screen."""

import unittest

from vliw.tui.screens.code_screen import excerpt_center, file_excerpt


class TestFileExcerpt(unittest.TestCase):
    TEXT = "\n".join(f"line {i}" for i in range(1, 101))

    def test_number_from_question_wins(self):
        self.assertEqual(excerpt_center("what is on line 536", 12, 1000), 536)

    def test_cursor_fallback(self):
        self.assertEqual(excerpt_center("why is it slow", 12, 100), 12)

    def test_clamp(self):
        self.assertEqual(excerpt_center("line 9999", 1, 100), 100)
        self.assertEqual(excerpt_center("", 1, 100), 1)

    def test_window_marks_center(self):
        out = file_excerpt("README.md", self.TEXT, 50, window=2)
        self.assertTrue(out[0].startswith("open file README.md"))
        self.assertIn(">>> 50: line 50", out)
        self.assertIn("    48: line 48", out)
        self.assertNotIn("45:", "\n".join(out))

    def test_empty(self):
        self.assertEqual(file_excerpt("x.md", "   \n ", 1),
                         ["open file x.md: empty"])


if __name__ == "__main__":
    unittest.main()
