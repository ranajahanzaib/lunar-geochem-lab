"""Acquire and normalize Astromat's official lunar compilation.

The original ECL archive is retained. Processing is deterministic and streams the wide
source CSV into normalized Parquet tables without constructing compositions across rows.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html.parser
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterator

TITLE = "Astromat Synthesis Compilation: Lunar samples v.1 February 2025"
DOI = "10.60520/IEDA/113696"
ECL_PAGE = "https://ecl.earthchem.org/view.php?id=3696"
ARCHIVE_BASE = "https://ecl.earthchem.org/"
LICENSE = "CC-BY-4.0"
PROCESSING_VERSION = "0.2.2"
META_FIELDS = {
    "sample_name": "Sample Name",
    "sample_url": "Sample URL",
    "citation": "Citation",
    "citation_url": "Citation URL",
    "collection": "Collection",
    "data_source": "Data Source",
    "sample_type": "Sample Type",
    "sample_subtype": "Sample SubType",
    "analysis_type": "Analysis Type",
    "analyzed_material": "Analyzed Material",
    "mineral": "Mineral",
    "analysis_comment": "Analysis Comment",
    "calc_avg": "Calc Avg",
    "number_of_replicates": "Number Of Replicates",
    "inclusion_type": "Inclusion Type",
    "inclusion_mineral": "Inclusion Mineral",
}
UNCERTAINTY_SUFFIXES = (
    "1S-ABS", "2S-ABS", "1S-REL", "2S-REL", "S-ABS", "S-REL", "1S", "2S", "S", "ABS", "REL", "%"
)
UNIT_CANONICAL = {"wt%": "wt%", "ppm": "ppm", "per mil": "per mil", "vol%": "vol%", "area%": "area%", "mol%": "mol%", "at%": "at%"}
CONCENTRATION_UNITS = {"wt%", "ppm"}


class _FormParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_download_form = False
        self.action = "dl_multi.php"
        self.inputs: dict[str, str] = {}
        self.sha1_info_links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "form" and a.get("id") == "formsM":
            self.in_download_form = True
            self.action = a.get("action") or "dl_multi.php"
        elif tag == "form":
            self.in_download_form = False
        if tag == "input" and self.in_download_form:
            name = a.get("name")
            value = a.get("value")
            if name and value is not None and a.get("type") == "hidden":
                self.inputs[name] = value
        if tag == "a" and a.get("href", "").startswith("info.php?info="):
            self.sha1_info_links.append(a["href"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self.in_download_form = False


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor())


def _request_headers() -> dict[str, str]:
    return {"User-Agent": "LunarGeochemLab/0.2 (Astromat research data client)"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _official_sha1(opener: urllib.request.OpenerDirector, info_href: str) -> str:
    url = urllib.parse.urljoin(ARCHIVE_BASE, info_href)
    req = urllib.request.Request(url, headers=_request_headers())
    with opener.open(req, timeout=30) as response:
        text = response.read().decode("utf-8", "replace")
    match = re.search(r"\b[0-9a-f]{40}\b", re.sub(r"<[^>]+>", " ", text), re.I)
    if not match:
        raise RuntimeError("Could not read the official SHA-1 checksum from EarthChem")
    return match.group(0).lower()


def acquire(directory: Path, *, accept_terms: bool = False, archive_format: str = "tar.gz") -> Path:
    """Download through ECL's public form. Requires explicit license acceptance per CLI run."""
    if not accept_terms:
        raise RuntimeError("ECL requires accepting its CC-BY-4.0 terms. Re-run with --accept-terms after reviewing them.")
    if archive_format not in {"tar.gz", "zip"}:
        raise ValueError("archive_format must be 'tar.gz' or 'zip'")
    directory.mkdir(parents=True, exist_ok=True)
    opener = _opener()
    req = urllib.request.Request(ECL_PAGE, headers=_request_headers())
    with opener.open(req, timeout=60) as response:
        page = response.read().decode("utf-8", "replace")
    parser = _FormParser()
    parser.feed(page)
    if not parser.inputs.get("id") or parser.inputs.get("id") != "3696":
        raise RuntimeError("Official ECL download form did not match dataset 3696")
    filename = f"all_dataset_3696.{archive_format}"
    links = parser.sha1_info_links
    if len(links) < 2:
        raise RuntimeError("Could not find ECL's downloadable archive checksums")
    # ECL publishes the ZIP checksum first and TAR.GZ checksum second alongside radios.
    expected_sha1 = _official_sha1(opener, links[0 if archive_format == "zip" else 1])
    target = directory / filename
    if target.is_file() and sha1(target) == expected_sha1:
        print(f"Verified existing {target}; skipping download")
        return target

    payload = dict(parser.inputs)
    payload["dlFormat"] = filename
    post = urllib.request.Request(
        urllib.parse.urljoin(ARCHIVE_BASE, parser.action),
        data=urllib.parse.urlencode(payload).encode(),
        headers={**_request_headers(), "Content-Type": "application/x-www-form-urlencoded", "Referer": ECL_PAGE},
    )
    partial = target.with_suffix(target.suffix + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset:
        post.add_header("Range", f"bytes={offset}-")
    with opener.open(post, timeout=180) as response:
        append = bool(offset and response.status == 206)
        if not append:
            offset = 0
        content_type = (response.headers.get("Content-Type") or "").lower()
        disposition = (response.headers.get("Content-Disposition") or "").lower()
        if not ("application" in content_type or "attachment" in disposition):
            preview = response.read(1200).decode("utf-8", "replace")
            raise RuntimeError(f"ECL returned a non-archive response: {preview[:500]}")
        mode = "ab" if append else "wb"
        with partial.open(mode) as output:
            shutil.copyfileobj(response, output, 1024 * 1024)
    actual_sha1 = sha1(partial)
    if actual_sha1 != expected_sha1:
        raise RuntimeError(f"ECL SHA-1 mismatch: expected {expected_sha1}, received {actual_sha1}; partial kept at {partial}")
    partial.replace(target)
    return target


def _archive_csv(path: Path) -> tuple[BinaryIO, object]:
    """Return a streaming CSV member and its archive owner. Never extract arbitrary paths."""
    if tarfile.is_tarfile(path):
        archive = tarfile.open(path, "r:*")
        members = [m for m in archive.getmembers() if m.isfile() and m.name.lower().endswith(".csv")]
        if len(members) != 1:
            archive.close()
            raise ValueError(f"Expected one source CSV in tar archive, found {len(members)}")
        stream = archive.extractfile(members[0])
        if stream is None:
            archive.close()
            raise ValueError("Unable to stream source CSV from tar archive")
        return stream, archive
    if zipfile.is_zipfile(path):
        archive = zipfile.ZipFile(path)
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            archive.close()
            raise ValueError(f"Expected one source CSV in ZIP archive, found {len(names)}")
        return archive.open(names[0]), archive
    return path.open("rb"), None


def _source_rows(stream: BinaryIO) -> Iterator[list[str]]:
    # ECL release contains Windows-1252 punctuation (e.g. the » grain-size separator).
    decoded = (line.decode("cp1252", "replace") for line in stream)
    return csv.reader(decoded)


def _unit(variable: str) -> str:
    match = re.search(r"\(([^()]*)\)\s*$", variable)
    return match.group(1).strip() if match else ""


def _species_category(variable: str, unit: str) -> str:
    if unit in {"wt%", "ppm", "picomol", "mol/g", "mg/g", "nmol/g", "cc/g", "ccstp/g", "dpm/g", "dpm/kg", "atoms/g", "kg/m3"}:
        return "concentration_or_abundance"
    if unit in {"vol%", "area%", "mol%", "at%"}:
        return "modal_or_compositional_percent"
    if "per mil" in unit.lower() or "_" in variable or "(" not in variable:
        return "ratio_or_isotopic_quantity"
    return "other"


def process(source: Path, out_dir: Path) -> dict:
    """Build normalized samples, analyses, measurements, and Parquet outputs."""
    import duckdb

    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_dir = out_dir / "parquet"
    manifest_path = out_dir / "manifest.json"
    source_sha256 = sha256(source)
    source_sha1 = sha1(source)
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        original = previous.get("original_files", [{}])[0]
        if original.get("sha256") == source_sha256 and previous.get("processing_version") == PROCESSING_VERSION:
            expected = previous.get("outputs", [])
            if expected and all((out_dir / entry["path"]).is_file() for entry in expected):
                print("This exact release and processing version are already built; leaving outputs unchanged.")
                return previous

    stream, archive = _archive_csv(source)
    temp_dir = Path(tempfile.mkdtemp(prefix="lunar-geochem-", dir=out_dir))
    db_path = out_dir / "lunar_geochem.duckdb"
    staging_db_path = temp_dir / "lunar_geochem.duckdb"
    staging_parquet_dir = temp_dir / "parquet"
    staging_parquet_dir.mkdir()
    conn = duckdb.connect(str(staging_db_path))
    warnings: list[str] = []
    malformed_rows = missing_sample_ids = invalid_values = negative_concentrations = duplicate_source_rows = metadata_conflicts = 0
    row_count = measurement_count = 0
    samples: dict[str, dict[str, str]] = {}
    fingerprints: set[str] = set()
    try:
        reader = _source_rows(stream)
        raw_headers = next(reader)
        headers = [value.strip() for value in raw_headers]
        if len(headers) != len(set(headers)):
            raise ValueError("The source CSV contains duplicate column names; cannot map safely")
        index = {name: i for i, name in enumerate(headers)}
        missing_meta = [name for name in META_FIELDS.values() if name not in index]
        if missing_meta:
            raise ValueError(f"Unexpected Astromat schema; missing expected source metadata fields: {missing_meta}")

        method_bases = {name[:-7] for name in headers if name.endswith(" Method")}
        comment_bases = {name[:-16] for name in headers if name.endswith(" Method (comment)")}
        species_names = sorted((method_bases | comment_bases) & set(headers))
        if not species_names:
            raise ValueError("No measurement columns with source method metadata were found")
        methods_idx = {name: index.get(f"{name} Method") for name in species_names}
        comments_idx = {name: index.get(f"{name} Method (comment)") for name in species_names}
        labs_idx = {name: index.get(f"{name} Lab") for name in species_names}
        uncertainty_idx: dict[str, list[tuple[str, int]]] = {}
        for name in species_names:
            related = []
            for suffix in UNCERTAINTY_SUFFIXES:
                pos = index.get(f"{name} {suffix}")
                if pos is not None:
                    related.append((suffix, pos))
            uncertainty_idx[name] = related

        samples_path = temp_dir / "samples.csv"
        analyses_path = temp_dir / "analyses.csv"
        measurements_path = temp_dir / "measurements.csv"
        quality_path = temp_dir / "quality_flags.csv"
        sample_fields = ["sample_id", "original_sample_id", "sample_url", "collection", "data_source", "sample_type", "sample_subtype", "material_class", "source_dataset"]
        analysis_fields = ["analysis_id", "sample_id", "source_row_number", "source_sample_name", "source_sample_url", "source_collection", "source_data_source", "source_sample_type", "source_sample_subtype", "citation_id", "citation", "citation_url", "analysis_type", "analyzed_material", "mineral", "analysis_comment", "calc_avg", "number_of_replicates", "inclusion_type", "inclusion_mineral", "source_row_fingerprint"]
        measurement_fields = ["measurement_id", "analysis_id", "species_id", "variable", "unit", "original_value", "standardized_value", "standardized_unit", "method", "method_comment", "laboratory", "uncertainties_json", "measurement_status", "source_column"]
        quality_fields = ["flag_id", "analysis_id", "sample_id", "flag_type", "severity", "source_column", "raw_value", "explanation"]

        with samples_path.open("w", newline="", encoding="utf-8") as sf, analyses_path.open("w", newline="", encoding="utf-8") as af, measurements_path.open("w", newline="", encoding="utf-8") as mf, quality_path.open("w", newline="", encoding="utf-8") as qf:
            sw, aw, mw, qw = (csv.DictWriter(f, fieldnames=fields) for f, fields in ((sf, sample_fields), (af, analysis_fields), (mf, measurement_fields), (qf, quality_fields)))
            for writer in (sw, aw, mw, qw): writer.writeheader()
            for source_row, row in enumerate(reader, start=1):
                if len(row) != len(headers):
                    malformed_rows += 1
                    continue
                row_count += 1
                values = {key: row[index[column]].strip() for key, column in META_FIELDS.items()}
                sample_name = values["sample_name"]
                sample_url = values["sample_url"]
                if not sample_name:
                    missing_sample_ids += 1
                    continue
                # Exact source sample labels are the conservative identity. The URL is
                # retained as an external reference, but not used to collapse distinct labels.
                identity = f"label:{sample_name}"
                sample_id = "AST-LUNAR-" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]
                analysis_id = f"AST-LUNAR-A{source_row:06d}"
                source_fingerprint = hashlib.sha256("\x1f".join(row).encode("utf-8")).hexdigest()
                if source_fingerprint in fingerprints:
                    duplicate_source_rows += 1
                    qw.writerow({"flag_id": f"Q{source_row}-duplicate", "analysis_id": analysis_id, "sample_id": sample_id, "flag_type": "duplicate_source_row", "severity": "review", "source_column": "*", "raw_value": source_fingerprint, "explanation": "An identical source row was seen earlier; retained as a separate source record."})
                else:
                    fingerprints.add(source_fingerprint)

                sample_row = {
                    "sample_id": sample_id,
                    "original_sample_id": sample_name,
                    "sample_url": sample_url,
                    "collection": values["collection"],
                    "data_source": values["data_source"],
                    "sample_type": values["sample_type"],
                    "sample_subtype": values["sample_subtype"],
                    "material_class": values["sample_subtype"] or values["sample_type"],
                    "source_dataset": DOI,
                }
                existing = samples.get(sample_id)
                if existing is None:
                    samples[sample_id] = sample_row
                elif any(existing.get(k) and sample_row.get(k) and existing[k] != sample_row[k] for k in ("collection", "data_source", "sample_type", "sample_subtype")):
                    metadata_conflicts += 1

                citation = values["citation"]
                citation_url = values["citation_url"]
                citation_id = "AST-PUB-" + hashlib.sha1((citation_url or citation).encode("utf-8")).hexdigest()[:16] if citation or citation_url else ""
                aw.writerow({"analysis_id": analysis_id, "sample_id": sample_id, "source_row_number": source_row, "source_sample_name": sample_name, "source_sample_url": sample_url, "source_collection": values["collection"], "source_data_source": values["data_source"], "source_sample_type": values["sample_type"], "source_sample_subtype": values["sample_subtype"], "citation_id": citation_id, "citation": citation, "citation_url": citation_url, "analysis_type": values["analysis_type"], "analyzed_material": values["analyzed_material"], "mineral": values["mineral"], "analysis_comment": values["analysis_comment"], "calc_avg": values["calc_avg"], "number_of_replicates": values["number_of_replicates"], "inclusion_type": values["inclusion_type"], "inclusion_mineral": values["inclusion_mineral"], "source_row_fingerprint": source_fingerprint})

                for name in species_names:
                    raw = row[index[name]].strip()
                    if raw == "":
                        continue
                    unit = _unit(name)
                    try:
                        number = float(raw.replace(",", ""))
                    except ValueError:
                        invalid_values += 1
                        qw.writerow({"flag_id": f"Q{source_row}-{index[name]}", "analysis_id": analysis_id, "sample_id": sample_id, "flag_type": "invalid_numeric_value", "severity": "error", "source_column": name, "raw_value": raw, "explanation": "The source value is not a parseable number; original source remains preserved in the archive."})
                        continue
                    if number < 0 and unit in CONCENTRATION_UNITS:
                        negative_concentrations += 1
                        qw.writerow({"flag_id": f"Q{source_row}-{index[name]}-negative", "analysis_id": analysis_id, "sample_id": sample_id, "flag_type": "negative_concentration", "severity": "review", "source_column": name, "raw_value": raw, "explanation": "Negative reported concentration retained for scientific review; not automatically removed."})
                    uncertainties = {suffix: row[pos].strip() for suffix, pos in uncertainty_idx[name] if row[pos].strip()}
                    variable_id = "AST-SP-" + hashlib.sha1(f"{name}\x1f{unit}".encode("utf-8")).hexdigest()[:16]
                    mw.writerow({"measurement_id": f"{analysis_id}-M{index[name]:04d}", "analysis_id": analysis_id, "species_id": variable_id, "variable": name, "unit": unit, "original_value": raw, "standardized_value": number, "standardized_unit": UNIT_CANONICAL.get(unit, unit), "method": row[methods_idx[name]].strip() if methods_idx[name] is not None else "", "method_comment": row[comments_idx[name]].strip() if comments_idx[name] is not None else "", "laboratory": row[labs_idx[name]].strip() if labs_idx[name] is not None else "", "uncertainties_json": json.dumps(uncertainties, ensure_ascii=False, separators=(",", ":")), "measurement_status": "measured", "source_column": headers[index[name]]})
                    measurement_count += 1

        with samples_path.open("w", newline="", encoding="utf-8") as sf:
            sw = csv.DictWriter(sf, fieldnames=sample_fields); sw.writeheader()
            for item in samples.values(): sw.writerow(item)

        conn.execute("CREATE TABLE samples AS SELECT * FROM read_csv(?, header=true, all_varchar=true, nullstr='')", [str(samples_path)])
        conn.execute("""CREATE TABLE analyses AS SELECT analysis_id, sample_id,
            TRY_CAST(source_row_number AS INTEGER) source_row_number,
            source_sample_name, source_sample_url, source_collection, source_data_source,
            source_sample_type, source_sample_subtype,
            citation_id, citation, citation_url, analysis_type, analyzed_material, mineral,
            analysis_comment, calc_avg, number_of_replicates,
            inclusion_type, inclusion_mineral, source_row_fingerprint
            FROM read_csv(?, header=true, all_varchar=true, nullstr='')""", [str(analyses_path)])
        conn.execute("""CREATE TABLE measurements AS SELECT measurement_id, analysis_id, species_id,
            variable, unit, original_value, TRY_CAST(standardized_value AS DOUBLE) standardized_value,
            standardized_unit, method, method_comment, laboratory, uncertainties_json,
            measurement_status, source_column FROM read_csv(?, header=true, all_varchar=true, nullstr='')""", [str(measurements_path)])
        conn.execute("CREATE TABLE publications AS SELECT DISTINCT citation_id publication_id, citation title_or_reference, citation_url external_url, regexp_extract(citation, '10\\.[0-9]{4,9}/[^ ]+', 0) doi FROM analyses WHERE citation_id <> ''")
        conn.execute("CREATE TABLE chemical_species AS SELECT DISTINCT species_id, variable, regexp_extract(variable, '\\(([^()]*)\\)\\s*$', 1) source_unit, CASE WHEN regexp_extract(variable, '\\(([^()]*)\\)\\s*$', 1) IN ('wt%', 'ppm', 'picomol', 'mol/g', 'mg/g', 'nmol/g', 'cc/g', 'ccstp/g', 'dpm/g', 'dpm/kg', 'atoms/g', 'kg/m3') THEN 'concentration_or_abundance' WHEN regexp_extract(variable, '\\(([^()]*)\\)\\s*$', 1) IN ('vol%', 'area%', 'mol%', 'at%') THEN 'modal_or_compositional_percent' WHEN contains(variable, '_') OR NOT contains(variable, '(') THEN 'ratio_or_isotopic_quantity' ELSE 'other' END chemical_category FROM measurements")
        conn.execute("CREATE TABLE publications_index AS SELECT publication_id, title_or_reference title, NULL authors, NULL publication_year, NULL journal, doi, external_url from publications")
        conn.execute("CREATE TABLE dataset_releases AS SELECT ?::VARCHAR dataset_id, ?::VARCHAR title, ?::VARCHAR doi, ?::VARCHAR license, ?::VARCHAR source_url, ?::VARCHAR version", ["astromat-lunar-v1-2025-02", TITLE, DOI, LICENSE, ECL_PAGE, "1.0"])
        conn.execute("CREATE TABLE quality_flags AS SELECT * FROM read_csv(?, header=true, all_varchar=true, nullstr='')", [str(quality_path)])

        output_tables = ["samples", "analyses", "measurements", "chemical_species", "publications", "quality_flags"]
        output_entries = []
        for table in output_tables:
            destination = staging_parquet_dir / f"{table}.parquet"
            safe_path = destination.as_posix().replace("'", "''")
            conn.execute(f"COPY {table} TO '{safe_path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
            output_entries.append({"path": f"parquet/{table}.parquet", "size_bytes": destination.stat().st_size, "_staged": str(destination)})

        units = conn.execute("SELECT unit, count(*) n FROM measurements GROUP BY unit ORDER BY n DESC").fetchall()
        sample_count = len(samples)
        species_count = conn.execute("SELECT count(*) FROM chemical_species").fetchone()[0]
        source_columns = headers
        if malformed_rows: warnings.append(f"{malformed_rows} malformed rows with a field-count mismatch were excluded from normalization.")
        if missing_sample_ids: warnings.append(f"{missing_sample_ids} rows without a sample identifier were excluded from normalized tables.")
        if invalid_values: warnings.append(f"{invalid_values} nonnumeric populated measurement values were flagged and excluded from the numeric analytical table.")
        if metadata_conflicts: warnings.append(f"{metadata_conflicts} source rows had sample metadata that conflicted with the first row for the same exact sample label; source-level values are preserved on each analysis.")
        if not any("detection" in h.lower() for h in headers): warnings.append("No explicit detection-limit field was found in the source CSV schema.")
        if not any(h in headers for h in ("Mission", " Mission")): warnings.append("No mission field was present in the source CSV; mission was not inferred from sample labels.")
        if negative_concentrations: warnings.append(f"{negative_concentrations} negative concentration observations were flagged for review and retained.")

        manifest = {
            "manifest_version": 1,
            "dataset_id": "astromat-lunar-v1-2025-02",
            "title": TITLE,
            "release": "Version 1.0 (2025-02-26)",
            "source_doi": DOI,
            "source_urls": [ECL_PAGE, "https://repo.astromat.org/view.php?id=3696&system=astro"],
            "license": LICENSE,
            "download_date": datetime.now(timezone.utc).isoformat(),
            "original_files": [{"name": source.name, "size_bytes": source.stat().st_size, "sha1": source_sha1, "sha256": source_sha256}],
            "source_csv_member": "3696-1_astromat_2_25_2025_11_1_53.csv",
            "source_terms_member": "3696-2_astromat_terms_of_use_2_25_2025_11_1_53.txt",
            "source_column_count": len(source_columns),
            "source_columns": source_columns,
            "processing_version": PROCESSING_VERSION,
            "record_counts": {"source_analysis_rows": row_count, "samples": sample_count, "analyses": row_count - malformed_rows - missing_sample_ids, "measurements": measurement_count, "chemical_species": species_count, "publications": conn.execute("SELECT count(*) FROM publications").fetchone()[0], "quality_flags": conn.execute("SELECT count(*) FROM quality_flags").fetchone()[0]},
            "units_observed": [{"unit": u, "measurement_count": n} for u, n in units],
            "validation_warnings": warnings,
            "validation_metrics": {"malformed_rows": malformed_rows, "missing_sample_ids": missing_sample_ids, "invalid_measurement_values": invalid_values, "negative_concentrations": negative_concentrations, "identical_source_rows_retained": duplicate_source_rows, "sample_metadata_conflicts": metadata_conflicts},
            "transformation_history": [
                "Official ECL archive retained unchanged in data/raw.",
                "Decoded CSV using Windows-1252 after source encoding inspection; preserved source headers and raw value strings.",
                "One normalized analysis created per source row; no analytical rows were aggregated.",
                "Measurements emitted only for source value columns paired with Astromat Method or Method (comment) fields.",
                "Source uncertainty columns attached without assuming a sigma convention; reported unit strings retained and canonical spellings recorded without unit conversion.",
                "Parquet tables written with Zstandard compression; DuckDB tables kept for local query service.",
            ],
            "outputs": [{"path": "lunar_geochem.duckdb", "size_bytes": staging_db_path.stat().st_size}] + output_entries,
        }
        conn.close()
        conn = None
        os.replace(staging_db_path, db_path)
        parquet_dir.mkdir(parents=True, exist_ok=True)
        for entry in output_entries:
            staged = Path(entry.pop("_staged"))
            os.replace(staged, out_dir / entry["path"])
        manifest["outputs"][0]["size_bytes"] = db_path.stat().st_size
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Processed {row_count:,} source analysis rows, {sample_count:,} distinct source sample labels, {measurement_count:,} measurements, {species_count:,} species.")
        print(f"DuckDB: {db_path}\nParquet: {parquet_dir}\nManifest: {manifest_path}")
        return manifest
    finally:
        if conn is not None:
            conn.close()
        stream.close()
        if archive is not None:
            archive.close()
        shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    download = sub.add_parser("download", help="Download the official ECL release")
    download.add_argument("--directory", type=Path, default=Path("data/raw"))
    download.add_argument("--format", choices=("tar.gz", "zip"), default="tar.gz")
    download.add_argument("--accept-terms", action="store_true", help="Explicitly confirm ECL terms and citation requirements")
    process_parser = sub.add_parser("process", help="Normalize a downloaded Astromat archive or source CSV")
    process_parser.add_argument("source", type=Path)
    process_parser.add_argument("--output", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    try:
        if args.command == "download":
            path = acquire(args.directory, accept_terms=args.accept_terms, archive_format=args.format)
            print(f"Verified official release archive: {path} ({path.stat().st_size:,} bytes); SHA-1 {sha1(path)}; SHA-256 {sha256(path)}")
        else:
            process(args.source, args.output)
    except Exception as exc:  # CLI boundary: readable failure and nonzero exit.
        print(f"ingest failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
