import unittest

from workhorse.tokens import fingerprints, normalize


class TokenTests(unittest.TestCase):
    def values(self, text, language):
        return [t.value for t in normalize(text, language)]

    def test_python_renaming_and_comments(self):
        self.assertEqual(self.values("x = 7 # first\nprint(x)\n", "python"),
                         self.values("item=7\nprint(item) # changed\n", "python"))

    def test_preserve_literals(self):
        self.assertNotEqual(self.values("x=7", "python"), self.values("x=8", "python"))

    def test_comment_markers_in_strings_preserved(self):
        values = self.values('String a="https://example.test/*x*/"; // note\n', "java")
        self.assertIn('"https://example.test/*x*/"', values)
        self.assertNotIn("note", values)

    def test_cpp_raw_string_not_treated_as_comment(self):
        values = self.values('auto s = R"tag(// text /* comment */)tag";', "cpp")
        self.assertIn('R"tag(// text /* comment */)tag"', values)

    def test_source_line_mapping(self):
        tokens = normalize("/* first\nsecond */\nint value=3;\n", "c")
        self.assertEqual(tokens[0].line, 3)

    def test_python_indentation_kept(self):
        self.assertIn("INDENT", self.values("if True:\n    print(1)\n", "python"))

    def test_deterministic_fingerprints(self):
        a = normalize("int x=2; while(x>0){x--;}", "c")
        b = normalize("int renamed=2; while(renamed>0){renamed--;}", "c")
        self.assertEqual(fingerprints(a), fingerprints(b))

    def test_short_sources_have_no_fingerprints(self):
        self.assertEqual(fingerprints(normalize("x=1", "python")), {})
