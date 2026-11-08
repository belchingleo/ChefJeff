"""research_stats: intervals and tests against published reference values."""
import unittest

import research_stats as rs


class IntervalTests(unittest.TestCase):
    def test_wilson_matches_the_reference_values(self):
        # Wilson (1927) score intervals at 95%, as tabulated by Newcombe (1998) and statistics packages.
        self.assertEqual(rs.wilson(5, 10), [0.237, 0.763])
        self.assertEqual(rs.wilson(0, 10), [0.0, 0.278])
        self.assertEqual(rs.wilson(10, 10), [0.722, 1.0])
        self.assertEqual(rs.wilson(1, 20), [0.009, 0.236])
        self.assertIsNone(rs.wilson(0, 0))

    def test_share_writes_the_interval_beside_the_share(self):
        self.assertEqual(rs.share(3, 4), {'k': 3, 'n': 4, 'share': 0.75, 'ci95': rs.wilson(3, 4)})
        self.assertEqual(rs.share(0, 0), {'k': 0, 'n': 0, 'share': None, 'ci95': None})

    def test_bootstrap_is_reproducible_and_covers_the_statistic(self):
        values = [1, 2, 3, 4, 5, 9]
        self.assertEqual(rs.bootstrap(values), rs.bootstrap(values))               # seeded: the same run twice
        low, high = rs.bootstrap(values)
        self.assertLessEqual(low, rs.mean(values))
        self.assertGreaterEqual(high, rs.mean(values))
        low, high = rs.bootstrap(values, statistic=rs.median)
        self.assertLessEqual(low, 3.5)
        self.assertGreaterEqual(high, 3.5)
        self.assertIsNone(rs.bootstrap([]))
        self.assertEqual(rs.bootstrap([4, 4, 4]), [4, 4])

    def test_bootstrap_difference_is_b_minus_a(self):
        low, high = rs.bootstrap_difference([0, 0, 0, 1], [1, 1, 1, 1])
        self.assertGreaterEqual(low, 0)
        self.assertLessEqual(high, 1)
        self.assertEqual(rs.bootstrap_difference([2, 2], [5, 5]), [3, 3])
        self.assertIsNone(rs.bootstrap_difference([], [1]))


class PairedTests(unittest.TestCase):
    def test_exact_mcnemar(self):
        # Two-sided exact binomial test with p = 1/2 on the b + c discordant pairs.
        self.assertEqual(rs.mcnemar(8, 2), 0.1094)       # 2 * (1 + 10 + 45) / 1024
        self.assertEqual(rs.mcnemar(0, 5), 0.0625)       # 2 / 32
        self.assertEqual(rs.mcnemar(3, 3), 1.0)
        self.assertEqual(rs.mcnemar(0, 0), 1.0)

    def test_paired_counts_only_moments_answered_both_ways(self):
        out = rs.paired([True, False, False, None, True], [True, True, True, False, False])
        self.assertEqual(out, {'moments': 4, 'only_second': 2, 'only_first': 1, 'difference': 0.25, 'mcnemar_p': 1.0})
        self.assertEqual(rs.paired([], [])['difference'], None)


class SampleSizeTests(unittest.TestCase):
    def test_per_arm_rounds_matches_the_tables(self):
        # Two-sided alpha .05, power .8, no continuity correction (Fleiss, Statistical Methods for Rates and Proportions).
        self.assertEqual(rs.per_arm_rounds(.5, .8), 39)
        self.assertEqual(rs.per_arm_rounds(.3, .5), 93)
        self.assertIsNone(rs.per_arm_rounds(.4, .4))
        # The floor-share difference the put_where check looked for (0.474 vs 0.6) needs far more than 20 moments.
        self.assertGreater(rs.per_arm_rounds(.474, .6), 200)


if __name__ == '__main__':
    unittest.main()
