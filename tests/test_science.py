import unittest

from lunar_lab.science import (
    ce_anomaly,
    eu_anomaly,
    mg_number,
    normalized_abundance,
    ppm_to_wt_percent,
    ternary,
    ti_classification,
    wt_percent_to_ppm,
)


class ScienceTests(unittest.TestCase):
    def test_concentration_conversions(self):
        self.assertEqual(ppm_to_wt_percent(12_500), 1.25)
        self.assertEqual(wt_percent_to_ppm(1.25), 12_500)

    def test_normalization_and_missing(self):
        self.assertEqual(normalized_abundance(4, 2), 2)
        self.assertIsNone(normalized_abundance(None, 2))
        with self.assertRaises(ValueError):
            normalized_abundance(1, 0)

    def test_ree_anomalies(self):
        self.assertAlmostEqual(eu_anomaly({"Eu": 2, "Sm": 1, "Gd": 1}), 2)
        self.assertAlmostEqual(ce_anomaly({"Ce": 3, "La": 1, "Pr": 1}), 3)
        self.assertIsNone(eu_anomaly({"Eu": 2, "Sm": 1}))
        self.assertIsNone(ce_anomaly({"Ce": 3, "La": 1, "Pr": 0}))

    def test_mg_number(self):
        expected = 100 * (10 / 40.304) / ((10 / 40.304) + (10 / 71.844))
        self.assertAlmostEqual(mg_number(10, 10), expected)
        self.assertIsNone(mg_number(None, 10))
        with self.assertRaises(ValueError):
            mg_number(-1, 1)

    def test_ternary_closure(self):
        self.assertEqual(ternary(1, 2, 1), (0.25, 0.5, 0.25))
        with self.assertRaises(ValueError):
            ternary(-1, 1, 1)
        with self.assertRaises(ValueError):
            ternary(0, 0, 0)

    def test_neal_taylor_ti_boundaries_and_context(self):
        eligible = {"eligible_bulk_mare_basalt": True}
        self.assertEqual(ti_classification(0.999, **eligible), "Very low-Ti")
        self.assertEqual(ti_classification(1, **eligible), "Low-Ti")
        self.assertEqual(ti_classification(6, **eligible), "Low-Ti")
        self.assertEqual(ti_classification(6.001, **eligible), "High-Ti")
        self.assertIsNone(ti_classification(7, eligible_bulk_mare_basalt=False))
        self.assertIsNone(ti_classification(None, **eligible))


if __name__ == "__main__":
    unittest.main()
