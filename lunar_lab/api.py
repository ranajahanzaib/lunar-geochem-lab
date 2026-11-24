"""Read-only, parameterized HTTP API over the local DuckDB/Parquet dataset."""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data/processed/lunar_geochem.duckdb"
MANIFEST = ROOT / "data/processed/manifest.json"
REE_ORDER = ["La", "Ce", "Pr", "Nd", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu"]
REE_COLUMNS = [f"{symbol} (ppm)" for symbol in REE_ORDER]
BASELINES = {
    "bulk_mare_basalt": "a.source_sample_subtype IN ('ILMENITE BASALT','OLIVINE BASALT','PIGEONITE BASALT') AND a.analyzed_material = 'WHOLE ROCK'",
}


def _db():
    import duckdb

    conn = duckdb.connect(str(DATABASE), read_only=True)
    conn.execute("SET threads=2")
    return conn


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class ApiHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def _send_json(self, value: Any, status: int = 200) -> None:
        body = json.dumps(value, ensure_ascii=False, default=_json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str, code: str) -> None:
        self._send_json({"error": {"code": code, "message": message}}, status)

    def _params(self) -> tuple[str, dict[str, list[str]]]:
        parsed = urllib.parse.urlsplit(self.path)
        return parsed.path, urllib.parse.parse_qs(parsed.query, keep_blank_values=True)

    @staticmethod
    def _one(params: dict[str, list[str]], name: str, default: str = "") -> str:
        return params.get(name, [default])[0]

    def _all(self, sql: str, args: list[Any] | tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        conn = _db()
        try:
            cursor = conn.execute(sql, args)
            names = [column[0] for column in cursor.description]
            return [dict(zip(names, row)) for row in cursor.fetchall()]
        finally:
            conn.close()

    def _one_row(self, sql: str, args: list[Any] | tuple[Any, ...] = ()) -> dict[str, Any] | None:
        result = self._all(sql, args)
        return result[0] if result else None

    def do_GET(self) -> None:
        path, params = self._params()
        try:
            if path == "/api/v1/health":
                self._send_json({"ok": True, "dataset_loaded": DATABASE.is_file(), "api_version": "v1"})
            elif path == "/api/v1/datasets":
                self._send_json([json.loads(MANIFEST.read_text())] if MANIFEST.is_file() else [])
            elif path == "/api/v1/overview":
                self._overview()
            elif path == "/api/v1/samples":
                self._samples(params)
            elif path.startswith("/api/v1/samples/"):
                self._sample_detail(path, params)
            elif path == "/api/v1/species":
                self._species(params)
            elif path == "/api/v1/facets":
                self._facets()
            elif path == "/api/v1/query/observations":
                self._observations(params)
            elif path == "/api/v1/analysis/ree":
                self._ree(params)
            elif path == "/api/v1/analysis/basalts":
                self._basalts(params)
            elif path == "/api/v1/data-quality":
                self._data_quality()
            else:
                super().do_GET()
        except ValueError as exc:
            self._error(400, str(exc), "invalid_request")
        except Exception as exc:  # API boundary: provide a structured, non-sensitive error.
            self._error(500, "The local analytical query failed.", "query_failed")
            print(f"API error: {type(exc).__name__}: {exc}")

    def _overview(self) -> None:
        if not DATABASE.is_file():
            manifest = json.loads(MANIFEST.read_text()) if MANIFEST.is_file() else None
            self._send_json({"dataset_loaded": False, "dataset": manifest, "counts": None})
            return
        row = self._one_row("""SELECT (SELECT count(*) FROM samples) samples,
            (SELECT count(*) FROM analyses) analyses,
            (SELECT count(*) FROM measurements) measurements,
            (SELECT count(*) FROM chemical_species) species,
            (SELECT count(*) FROM publications) publications""")
        units = self._all("SELECT unit, count(*) measurement_count FROM measurements GROUP BY unit ORDER BY measurement_count DESC")
        subtype = self._all("SELECT coalesce(nullif(source_sample_subtype,''),'Unclassified') label, count(*) analysis_count FROM analyses GROUP BY 1 ORDER BY analysis_count DESC LIMIT 12")
        self._send_json({"dataset_loaded": True, "dataset": json.loads(MANIFEST.read_text()) if MANIFEST.is_file() else None, "counts": row, "units": units, "material_types": subtype})

    def _samples(self, params: dict[str, list[str]]) -> None:
        q = self._one(params, "q").strip()[:160]
        subtype = self._one(params, "subtype").strip()[:120]
        material = self._one(params, "material").strip()[:80]
        species = self._one(params, "species").strip()[:180]
        page = max(1, min(int(self._one(params, "page", "1")), 100000))
        size = max(1, min(int(self._one(params, "page_size", "25")), 100))
        where, args = [], []
        if q:
            where.append("contains(lower(s.original_sample_id), lower(?))")
            args.append(q)
        if subtype:
            where.append("s.material_class = ?")
            args.append(subtype)
        if species:
            where.append("EXISTS (SELECT 1 FROM analyses aa JOIN measurements mm USING (analysis_id) WHERE aa.sample_id=s.sample_id AND mm.variable=?)")
            args.append(species)
        if material:
            where.append("EXISTS (SELECT 1 FROM analyses aa WHERE aa.sample_id=s.sample_id AND aa.analyzed_material=?)")
            args.append(material)
        clause = " WHERE " + " AND ".join(where) if where else ""
        total = self._one_row(f"SELECT count(*) total FROM samples s{clause}", args)["total"]
        sql = f"""SELECT s.sample_id, s.original_sample_id, s.sample_url, s.material_class, s.sample_type, s.sample_subtype,
            (SELECT count(*) FROM analyses a WHERE a.sample_id=s.sample_id) analysis_count,
            (SELECT count(*) FROM measurements m JOIN analyses a USING(analysis_id) WHERE a.sample_id=s.sample_id) measurement_count,
            (SELECT count(DISTINCT p.citation_id) FROM analyses p WHERE p.sample_id=s.sample_id AND p.citation_id <> '') publication_count
            FROM samples s{clause} ORDER BY s.original_sample_id LIMIT ? OFFSET ?"""
        rows = self._all(sql, [*args, size, (page - 1) * size])
        self._send_json({"rows": rows, "page": page, "page_size": size, "total": total, "pages": (total + size - 1) // size})

    def _sample_detail(self, path: str, params: dict[str, list[str]]) -> None:
        suffix = path[len("/api/v1/samples/"):]
        parts = suffix.split("/")
        if not parts or not re.fullmatch(r"AST-LUNAR-[a-f0-9]{16}", parts[0]):
            self._error(404, "Sample not found.", "not_found")
            return
        sample_id = parts[0]
        if len(parts) == 1:
            sample = self._one_row("SELECT * FROM samples WHERE sample_id=?", [sample_id])
            if not sample:
                self._error(404, "Sample not found.", "not_found"); return
            counts = self._one_row("""SELECT count(*) analysis_count,
                count(DISTINCT citation_id) FILTER(WHERE citation_id <> '') publication_count,
                (SELECT count(*) FROM measurements m JOIN analyses a USING(analysis_id) WHERE a.sample_id=?) measurement_count
                FROM analyses WHERE sample_id=?""", [sample_id, sample_id])
            self._send_json({"sample": sample, "counts": counts})
        elif len(parts) == 2 and parts[1] == "analyses":
            limit = max(1, min(int(self._one(params, "limit", "100")), 500))
            rows = self._all("""SELECT a.analysis_id, a.source_row_number, a.citation_id, a.citation, a.citation_url,
                a.analysis_type, a.analyzed_material, a.mineral, a.analysis_comment, a.calc_avg,
                a.number_of_replicates, a.source_sample_subtype,
                count(m.measurement_id) measurement_count
                FROM analyses a LEFT JOIN measurements m USING(analysis_id)
                WHERE a.sample_id=? GROUP BY ALL ORDER BY a.source_row_number LIMIT ?""", [sample_id, limit])
            self._send_json({"rows": rows, "total_returned": len(rows), "limit": limit})
        elif len(parts) == 2 and parts[1] == "measurements":
            limit = max(1, min(int(self._one(params, "limit", "1000")), 5000))
            analysis_id = self._one(params, "analysis_id")
            args: list[Any] = [sample_id]
            condition = "a.sample_id=?"
            if analysis_id:
                condition += " AND a.analysis_id=?"; args.append(analysis_id)
            rows = self._all("""SELECT m.measurement_id, m.analysis_id, m.variable, m.unit, m.original_value,
                m.standardized_value, m.standardized_unit, m.method, m.method_comment, m.laboratory,
                m.uncertainties_json, m.measurement_status, a.analyzed_material, a.mineral, a.citation_id
                FROM measurements m JOIN analyses a USING(analysis_id) WHERE """ + condition + " ORDER BY m.variable LIMIT ?", [*args, limit])
            self._send_json({"rows": rows, "limit": limit})
        else:
            self._error(404, "Sample endpoint not found.", "not_found")

    def _species(self, params: dict[str, list[str]]) -> None:
        q = self._one(params, "q").strip()[:120]
        where, args = (" WHERE contains(lower(variable), lower(?))", [q]) if q else ("", [])
        unit = self._one(params, "unit")
        if unit:
            where += (" AND " if where else " WHERE ") + "unit=?"; args.append(unit)
        rows = self._all("""SELECT species_id, variable, unit, count(*) measurement_count,
            count(DISTINCT analysis_id) analysis_count FROM measurements""" + where + " GROUP BY species_id, variable, unit ORDER BY variable, unit LIMIT 800", args)
        self._send_json({"rows": rows})

    def _facets(self) -> None:
        subtypes = self._all("SELECT DISTINCT material_class value FROM samples WHERE material_class IS NOT NULL AND material_class <> '' ORDER BY value")
        materials = self._all("SELECT DISTINCT analyzed_material value FROM analyses WHERE analyzed_material IS NOT NULL AND analyzed_material <> '' ORDER BY value")
        units = self._all("SELECT DISTINCT unit value FROM measurements WHERE unit IS NOT NULL AND unit <> '' ORDER BY value")
        self._send_json({"subtypes": [row["value"] for row in subtypes], "materials": [row["value"] for row in materials], "units": [row["value"] for row in units]})

    def _observations(self, params: dict[str, list[str]]) -> None:
        x_id = self._one(params, "x")
        y_id = self._one(params, "y")
        if not x_id or not y_id:
            raise ValueError("x and y species IDs are required")
        if not re.fullmatch(r"AST-SP-[a-f0-9]{16}", x_id) or not re.fullmatch(r"AST-SP-[a-f0-9]{16}", y_id):
            raise ValueError("Invalid species identifier")
        limit = max(1, min(int(self._one(params, "limit", "5000")), 20000))
        subtype = self._one(params, "subtype")
        material = self._one(params, "material")
        where, args = [], [x_id, y_id]
        if subtype:
            where.append("a.source_sample_subtype=?"); args.append(subtype)
        if material:
            where.append("a.analyzed_material=?"); args.append(material)
        condition = " AND " + " AND ".join(where) if where else ""
        sql = f"""SELECT a.analysis_id, a.sample_id, s.original_sample_id, a.source_sample_subtype,
            a.analyzed_material, a.mineral, a.citation_id, x.variable x_variable, x.unit x_unit,
            x.original_value x_original_value, x.standardized_value x_value, y.variable y_variable,
            y.unit y_unit, y.original_value y_original_value, y.standardized_value y_value
            FROM measurements x JOIN measurements y ON x.analysis_id=y.analysis_id
            JOIN analyses a ON a.analysis_id=x.analysis_id JOIN samples s ON s.sample_id=a.sample_id
            WHERE x.species_id=? AND y.species_id=?{condition}
            ORDER BY a.analysis_id LIMIT ?"""
        rows = self._all(sql, [*args, limit])
        self._send_json({"rows": rows, "limit": limit, "visual_aggregation": "none"})

    def _ree(self, params: dict[str, list[str]]) -> None:
        ids = [x for x in self._one(params, "analysis_ids").split(",") if x]
        if not ids or len(ids) > 20 or any(not re.fullmatch(r"AST-LUNAR-A\d{6}", x) for x in ids):
            raise ValueError("Select 1–20 valid analysis IDs")
        placeholders = ",".join("?" for _ in ids)
        columns = ",".join("?" for _ in REE_COLUMNS)
        sql = f"""SELECT a.analysis_id, a.sample_id, s.original_sample_id, a.analyzed_material,
            a.mineral, a.citation_id, m.variable, m.unit, m.original_value, m.standardized_value,
            m.method, m.laboratory FROM measurements m JOIN analyses a USING(analysis_id)
            JOIN samples s USING(sample_id) WHERE a.analysis_id IN ({placeholders})
            AND m.variable IN ({columns}) AND m.unit='ppm' ORDER BY a.analysis_id, m.variable"""
        self._send_json({"order": REE_ORDER, "normalization": "raw", "rows": self._all(sql, [*ids, *REE_COLUMNS]), "interpolation": "none"})

    def _basalts(self, params: dict[str, list[str]]) -> None:
        group = self._one(params, "group", "published")
        if group not in {"published", "exploratory"}:
            raise ValueError("group must be published or exploratory")
        subtype = self._one(params, "subtype")
        material = self._one(params, "material", "WHOLE ROCK")
        mission = self._one(params, "mission")
        # No mission field exists in this compilation. Reject it rather than guessing from labels.
        if mission:
            raise ValueError("Mission is not supplied in this source release and cannot be inferred from sample labels.")
        if group == "published":
            basalt_filter = BASELINES["bulk_mare_basalt"]
        else:
            basalt_filter = "(a.source_sample_subtype LIKE '%BASALT%' AND a.source_sample_subtype NOT LIKE '%FELDSPATHIC%') AND a.analyzed_material = 'WHOLE ROCK'"
        args: list[Any] = []
        if subtype:
            basalt_filter += " AND a.source_sample_subtype=?"; args.append(subtype)
        sql = f"""SELECT a.analysis_id, a.sample_id, s.original_sample_id, a.source_sample_subtype,
            a.analyzed_material, a.citation_id, v.variable, v.standardized_value, v.original_value,
            v.unit, v.method, v.laboratory FROM analyses a JOIN samples s USING(sample_id)
            JOIN measurements v USING(analysis_id)
            WHERE {basalt_filter} AND v.variable IN ('TiO2 (wt%)','FeOT (wt%)','FeO (wt%)','MgO (wt%)','Al2O3 (wt%)','SiO2 (wt%)')
            ORDER BY a.analysis_id"""
        rows = self._all(sql, args)
        # Bundle by source analysis; repeated analyses remain explicit and are not pseudo-replicated.
        bundled: dict[str, dict[str, Any]] = {}
        for row in rows:
            record = bundled.setdefault(row["analysis_id"], {k: row[k] for k in ("analysis_id", "sample_id", "original_sample_id", "source_sample_subtype", "analyzed_material", "citation_id")})
            record[row["variable"]] = {"value": row["standardized_value"], "original_value": row["original_value"], "unit": row["unit"], "method": row["method"], "laboratory": row["laboratory"]}
        observations = []
        for record in bundled.values():
            titania = record.get("TiO2 (wt%)", {}).get("value")
            if titania is not None:
                record["ti_class"] = "Very low-Ti" if titania < 1 else "Low-Ti" if titania <= 6 else "High-Ti"
                record["classification_scheme"] = "Neal & Taylor (1992), DOI 10.1016/0016-7037(92)90184-K" if group == "published" else "Exploratory subtype filter; no published classification claim"
                observations.append(record)
        self._send_json({"observations": observations, "analysis_count": len(observations), "sample_count": len({x['sample_id'] for x in observations}), "grouping": group, "sample_level_aggregation": "not applied", "mission_filter_available": False, "exclusions": {"missing_tio2": len(bundled) - len(observations)}, "classification_note": "Published tiers are restricted to whole-rock ILMENITE BASALT, OLIVINE BASALT, and PIGEONITE BASALT labels. Filter is conservative and exploratory results remain explicitly labeled."})

    def _data_quality(self) -> None:
        counts = self._one_row("""SELECT count(*) measurement_count,
            count(*) FILTER (WHERE standardized_value IS NULL) invalid_numeric_count,
            count(*) FILTER (WHERE standardized_value=0) measured_zero_count
            FROM measurements""")
        units = self._all("SELECT unit, count(*) measurement_count, count(DISTINCT species_id) species_count FROM measurements GROUP BY unit ORDER BY measurement_count DESC")
        methods = self._all("SELECT coalesce(nullif(method,''),'Not reported') method, count(*) measurement_count FROM measurements GROUP BY 1 ORDER BY measurement_count DESC LIMIT 30")
        flags = self._all("SELECT flag_type, severity, count(*) count FROM quality_flags GROUP BY 1,2 ORDER BY severity, count DESC")
        warnings = json.loads(MANIFEST.read_text()).get("validation_warnings", []) if MANIFEST.exists() else []
        self._send_json({"counts": counts, "units": units, "methods": methods, "flags": flags, "warnings": warnings})


def handler_class() -> type[ApiHandler]:
    return ApiHandler
