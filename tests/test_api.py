import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb

from lunar_lab import api


class HandlerProbe:
    _all = api.ApiHandler._all
    _one_row = api.ApiHandler._one_row
    _one = staticmethod(api.ApiHandler._one)
    _overview = api.ApiHandler._overview
    _samples = api.ApiHandler._samples
    _observations = api.ApiHandler._observations
    _sample_detail = api.ApiHandler._sample_detail
    _species = api.ApiHandler._species
    _facets = api.ApiHandler._facets
    _ree = api.ApiHandler._ree
    _basalts = api.ApiHandler._basalts
    _data_quality = api.ApiHandler._data_quality

    def _send_json(self, value, status=200):
        self.response, self.status = value, status

    def _error(self, status, message, code):
        self.response, self.status = {"error": {"message": message, "code": code}}, status


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.database = root / "fixture.duckdb"
        self.manifest = root / "manifest.json"
        self.manifest.write_text(json.dumps({"dataset_id": "fixture", "validation_warnings": ["Test note"]}))
        conn = duckdb.connect(str(self.database))
        conn.execute("CREATE TABLE samples(sample_id VARCHAR, original_sample_id VARCHAR, sample_url VARCHAR, material_class VARCHAR, sample_type VARCHAR, sample_subtype VARCHAR)")
        conn.execute("CREATE TABLE analyses(analysis_id VARCHAR, sample_id VARCHAR, source_row_number INTEGER, source_sample_subtype VARCHAR, analyzed_material VARCHAR, mineral VARCHAR, citation_id VARCHAR, citation VARCHAR, citation_url VARCHAR, analysis_type VARCHAR, analysis_comment VARCHAR, calc_avg VARCHAR, number_of_replicates VARCHAR)")
        conn.execute("CREATE TABLE measurements(measurement_id VARCHAR, analysis_id VARCHAR, species_id VARCHAR, variable VARCHAR, unit VARCHAR, original_value VARCHAR, standardized_value DOUBLE, standardized_unit VARCHAR, method VARCHAR, method_comment VARCHAR, laboratory VARCHAR, uncertainties_json VARCHAR, measurement_status VARCHAR, source_column VARCHAR)")
        conn.execute("CREATE TABLE chemical_species(species_id VARCHAR, variable VARCHAR, unit VARCHAR)")
        conn.execute("CREATE TABLE publications(citation_id VARCHAR)")
        conn.execute("CREATE TABLE quality_flags(flag_type VARCHAR, severity VARCHAR, count INTEGER)")
        s1, s2, s3 = "AST-LUNAR-0000000000000001", "AST-LUNAR-0000000000000002", "AST-LUNAR-0000000000000003"
        x, y = "AST-SP-0000000000000001", "AST-SP-0000000000000002"
        conn.executemany("INSERT INTO samples VALUES (?, ?, '', ?, '', '')", [(s1, "A-1", "BASALT"), (s2, "A-2", "BRECCIA"), (s3, "A-3", "OLIVINE BASALT")])
        conn.executemany("INSERT INTO analyses VALUES (?, ?, ?, ?, ?, '', 'CIT-1', '', '', '', '', '', '')", [
            ("AST-LUNAR-A000001", s1, 1, "BASALT", "WHOLE ROCK"),
            ("AST-LUNAR-A000002", s2, 2, "BRECCIA", "WHOLE ROCK"),
            ("AST-LUNAR-A000003", s3, 3, "OLIVINE BASALT", "WHOLE ROCK"),
        ])
        conn.executemany("INSERT INTO measurements VALUES (?, ?, ?, ?, 'wt%', ?, ?, 'wt%', '', '', '', '{}', 'measured', '')", [
            ("m1", "AST-LUNAR-A000001", x, "SiO2 (wt%)", "40", 40),
            ("m2", "AST-LUNAR-A000001", y, "TiO2 (wt%)", "2", 2),
            ("m3", "AST-LUNAR-A000002", x, "SiO2 (wt%)", "45", 45),
            ("m4", "AST-LUNAR-A000003", y, "TiO2 (wt%)", "3.5", 3.5),
            ("m5", "AST-LUNAR-A000003", "AST-SP-0000000000000003", "FeO (wt%)", "18.2", 18.2),
            ("m6", "AST-LUNAR-A000003", "AST-SP-0000000000000004", "MgO (wt%)", "9.1", 9.1),
        ])
        conn.executemany("INSERT INTO measurements VALUES (?, ?, ?, ?, 'ppm', ?, ?, 'ppm', '', '', '', '{}', 'measured', '')", [
            ("m7", "AST-LUNAR-A000003", "AST-SP-0000000000000005", "La (ppm)", "5.2", 5.2),
            ("m8", "AST-LUNAR-A000003", "AST-SP-0000000000000006", "Ce (ppm)", "12.8", 12.8),
        ])
        conn.executemany("INSERT INTO quality_flags VALUES (?, ?, ?)", [("NEGATIVE_CONCENTRATION", "WARNING", 2)])
        conn.close()
        self.handler = HandlerProbe()
        self.db_patch = patch.object(api, "DATABASE", self.database)
        self.manifest_patch = patch.object(api, "MANIFEST", self.manifest)
        self.db_patch.start()
        self.manifest_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.manifest_patch.stop()
        self.temp.cleanup()

    def test_same_analysis_join_and_filters(self):
        self.handler._observations({"x": ["AST-SP-0000000000000001"], "y": ["AST-SP-0000000000000002"], "limit": ["100"]})
        self.assertEqual(len(self.handler.response["rows"]), 1)
        self.assertEqual(self.handler.response["rows"][0]["analysis_id"], "AST-LUNAR-A000001")
        self.assertEqual(self.handler.response["rows"][0]["x_value"], 40)

    def test_sample_filters_pagination_and_parameter_binding(self):
        self.handler._samples({"q": ["A-"], "page": ["1"], "page_size": ["1"]})
        self.assertEqual(self.handler.response["total"], 3)
        self.assertEqual(self.handler.response["page_size"], 1)
        self.handler._samples({"q": ["' OR 1=1 --"], "page": ["1"], "page_size": ["25"]})
        self.assertEqual(self.handler.response["total"], 0)

    def test_invalid_species_identifier_is_rejected(self):
        with self.assertRaises(ValueError):
            self.handler._observations({"x": ["x' OR 1=1 --"], "y": ["AST-SP-0000000000000002"]})

    def test_basalts_endpoint_and_neal_taylor_classification(self):
        self.handler._basalts({"group": ["published"]})
        self.assertEqual(self.handler.response["analysis_count"], 1)
        obs = self.handler.response["observations"][0]
        self.assertEqual(obs["analysis_id"], "AST-LUNAR-A000003")
        self.assertEqual(obs["ti_class"], "Low-Ti")
        self.assertEqual(obs["TiO2 (wt%)"]["value"], 3.5)

    def test_ree_endpoint_validation_and_ordering(self):
        self.handler._ree({"analysis_ids": ["AST-LUNAR-A000003"]})
        self.assertEqual(len(self.handler.response["rows"]), 2)
        self.assertEqual(self.handler.response["normalization"], "raw")
        with self.assertRaises(ValueError):
            self.handler._ree({"analysis_ids": ["INVALID_ID"]})

    def test_data_quality_endpoint(self):
        self.handler._data_quality()
        self.assertEqual(self.handler.response["counts"]["measurement_count"], 8)
        self.assertEqual(len(self.handler.response["flags"]), 1)
        self.assertEqual(self.handler.response["warnings"], ["Test note"])


if __name__ == "__main__":
    unittest.main()
