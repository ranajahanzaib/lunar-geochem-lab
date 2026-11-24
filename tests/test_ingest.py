import csv
import tempfile
import unittest
from pathlib import Path

from lunar_lab.ingest import process


class IngestTests(unittest.TestCase):
    def test_schema_inventory_and_checksum_idempotence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "fixture.csv"
            metadata = ["Sample Name", "Sample URL", "Citation", "Citation URL", "Collection", "Data Source", "Sample Type", "Sample SubType", "Analysis Type", "Analyzed Material", "Mineral", "Analysis Comment", "Calc Avg", "Number Of Replicates", "Inclusion Type", "Inclusion Mineral"]
            with source.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=metadata + ["SiO2 (wt%)", "SiO2 (wt%) Method"])
                writer.writeheader()
                writer.writerow({"Sample Name": "fixture-only", "SiO2 (wt%)": "42", "SiO2 (wt%) Method": "XRF"})
                writer.writerow({"Sample Name": "fixture-only-2", "SiO2 (wt%)": "", "SiO2 (wt%) Method": "XRF"})
            out = root / "out"
            first = process(source, out)
            self.assertEqual(first["record_counts"]["source_analysis_rows"], 2)
            self.assertEqual(first["record_counts"]["samples"], 2)
            self.assertEqual(first["record_counts"]["measurements"], 1)
            self.assertTrue((out / "lunar_geochem.duckdb").is_file())
            self.assertTrue((out / "parquet" / "measurements.parquet").is_file())
            second = process(source, out)
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
