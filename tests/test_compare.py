import unittest

from workhorse.compare import Options, compare
from workhorse.imports import Submission


CODE = """def accumulate(values):
    total = 0
    previous = -7
    for value in values:
        if value > previous:
            total += value * 13
        else:
            total -= value * 3
        previous = value
    return total
print(accumulate([1, 5, 2]))
"""


def submission(id, source=CODE, author=None, task="sample", language="python"):
    return Submission(id, author or id, task, language, id + ".py", source)


class CompareTests(unittest.TestCase):
    def test_renamed_copy_has_line_evidence(self):
        other = CODE.replace("total", "score").replace("previous", "last")
        report = compare([submission("a"), submission("b", other)])
        finding = report["findings"][0]
        self.assertEqual(finding["containment"], 1)
        self.assertIn("score", finding["evidence"][0]["right"]["excerpt"])
        self.assertEqual(report["summary"]["candidate_pairs"], 1)
        self.assertFalse(report["additional_candidates"])

    def test_no_cross_task_or_language_pairs(self):
        report = compare([submission("a"), submission("b", task="other"),
                          submission("c", language="java")])
        self.assertEqual(report["findings"], [])

    def test_same_author_revisions_not_flagged(self):
        report = compare([submission("a", author="one"), submission("b", author="one")])
        self.assertEqual(report["findings"], [])

    def test_short_source_skipped(self):
        report = compare([submission("a", "print(1)"), submission("b", "print(1)")])
        self.assertEqual(report["groups"][0]["short_sources"], 2)
        self.assertFalse(report["findings"])

    def test_known_baseline_removed(self):
        report = compare([submission("a"), submission("b")], baselines=[submission("template")])
        self.assertFalse(report["findings"])
        self.assertGreater(report["groups"][0]["excluded_common_fingerprints"], 0)
        self.assertFalse(report["additional_candidates"])

    def test_task_specific_baseline_does_not_hide_other_tasks(self):
        items = [submission("a", task="other"), submission("b", task="other")]
        report = compare(items, baselines=[submission("base", task="sample")])
        self.assertTrue(report["findings"])

    def test_global_baseline_requires_explicit_wildcard(self):
        report = compare([submission("a"), submission("b")], baselines=[submission("base", task="*")])
        self.assertFalse(report["findings"])
        self.assertFalse(report["additional_candidates"])

    def test_common_corpus_content_removed(self):
        report = compare([submission(str(i)) for i in range(5)])
        self.assertFalse(report["findings"])
        self.assertGreater(report["groups"][0]["excluded_common_fingerprints"], 0)

    def test_capacity_is_explicit_not_silent(self):
        with self.assertRaisesRegex(ValueError, "Candidate limit"):
            compare([submission(str(i)) for i in range(4)], Options(max_candidates=2))

    def test_widespread_matches_visible_without_corpus_filter(self):
        report = compare([submission(str(i)) for i in range(5)], Options(corpus_filter=False))
        self.assertEqual(len(report["findings"]), 10)

    def test_invalid_settings_rejected(self):
        with self.assertRaises(ValueError):
            compare([], Options(k=0))

    def test_complementary_signals_do_not_replace_scores(self):
        other = CODE.replace("total", "score").replace("previous", "last")
        finding = compare([submission("a"), submission("b", other)])["findings"][0]
        self.assertEqual(finding["containment"], 1)
        self.assertLess(finding["signals"]["raw_containment"], 1)
        self.assertEqual(finding["signals"]["rarity_basis_authors"], 2)
        self.assertTrue(finding["cautions"])

    def test_crowded_postings_recorded(self):
        report = compare([submission(str(i)) for i in range(4)], Options(max_posting=2))
        self.assertFalse(report["findings"])
        self.assertGreater(report["groups"][0]["excluded_crowded_fingerprints"], 0)
