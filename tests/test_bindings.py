import unittest
from workhorse.tokens import normalize


class BindingTests(unittest.TestCase):
    def values(self, source, language="python", mode="relationships"):
        return [t.value for t in normalize(source, language, mode)]

    def test_repeated_variables_remain_distinct(self):
        a, b = "x = x + y", "x = y + y"
        self.assertEqual(self.values(a, mode="legacy"), self.values(b, mode="legacy"))
        self.assertNotEqual(self.values(a), self.values(b))

    def test_function_rename_preserves_bindings(self):
        a = "def add(a, b):\n    c = a + b\n    return c\nprint(add(1, 2))"
        b = "def sum_two(x, y):\n    z = x + y\n    return z\nprint(sum_two(1, 2))"
        self.assertEqual(self.values(a), self.values(b))

    def test_shadowed_name_not_same_binding(self):
        values = self.values("x = 1\ndef f(x):\n    return x\nprint(x)")
        self.assertIn("S0:V0", values)
        self.assertIn("S1:V0", values)

    def test_closure_and_nonlocal_rename(self):
        a = "def outer(x):\n    def inner():\n        nonlocal x\n        x += 1\n        return x\n    return inner()"
        b = a.replace("outer", "wrapper").replace("inner", "nested").replace("x", "total")
        self.assertEqual(self.values(a), self.values(b))

    def test_api_attributes_and_external_calls_preserved(self):
        self.assertNotEqual(self.values("items.sort()"), self.values("items.reverse()"))
        self.assertNotEqual(self.values("print(1)"), self.values("input(1)"))

    def test_comprehension_renaming(self):
        self.assertEqual(self.values("values = [x*2 for x in range(5)]"),
                         self.values("items = [n*2 for n in range(5)]"))

    def test_unicode_positions(self):
        self.assertEqual(self.values("résultat = 1\nprint(résultat)"), self.values("answer = 1\nprint(answer)"))

    def test_c_family_relationships(self):
        self.assertNotEqual(self.values("int x=1; int y=2; x=x+y;", "c"),
                            self.values("int x=1; int y=2; x=y+y;", "c"))

    def test_lambda_parameter_shadows_comprehension_target(self):
        a = "values = [(lambda x: x + 1)(2) for x in range(3)]"
        b = "items = [(lambda y: y + 1)(2) for n in range(3)]"
        self.assertEqual(self.values(a), self.values(b))

    def test_ambiguous_same_line_lambdas_declined(self):
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            self.values("f, g = lambda x: x, lambda y: y")
