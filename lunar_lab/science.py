"""Small, auditable geochemical calculations. Inputs remain explicit and missing stays missing."""

from __future__ import annotations

from math import sqrt
from typing import Mapping

REE_ORDER = ("La", "Ce", "Pr", "Nd", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu")


def ppm_to_wt_percent(value: float) -> float:
    return value / 10_000


def wt_percent_to_ppm(value: float) -> float:
    return value * 10_000


def normalized_abundance(sample: float | None, reference: float | None) -> float | None:
    if sample is None or reference is None:
        return None
    if reference <= 0:
        raise ValueError("Reference abundance must be positive")
    return sample / reference


def anomaly(center: float | None, left: float | None, right: float | None) -> float | None:
    """Geometric interpolation anomaly; unavailable or nonpositive inputs return None."""
    if center is None or left is None or right is None:
        return None
    if center <= 0 or left <= 0 or right <= 0:
        return None
    return center / sqrt(left * right)


def eu_anomaly(normalized: Mapping[str, float | None]) -> float | None:
    return anomaly(normalized.get("Eu"), normalized.get("Sm"), normalized.get("Gd"))


def ce_anomaly(normalized: Mapping[str, float | None]) -> float | None:
    return anomaly(normalized.get("Ce"), normalized.get("La"), normalized.get("Pr"))


def mg_number(mgo_wt: float | None, feo_total_wt: float | None) -> float | None:
    """Molar Mg# from MgO and total Fe reported as FeO; returns a 0–100 value."""
    if mgo_wt is None or feo_total_wt is None:
        return None
    if mgo_wt < 0 or feo_total_wt < 0:
        raise ValueError("Oxide concentrations cannot be negative")
    moles_mg = mgo_wt / 40.304
    moles_fe = feo_total_wt / 71.844
    total = moles_mg + moles_fe
    return None if total == 0 else 100 * moles_mg / total


def ternary(a: float, b: float, c: float) -> tuple[float, float, float]:
    """Closure to unit sum; caller retains original quantities separately."""
    if min(a, b, c) < 0:
        raise ValueError("Ternary components must be nonnegative")
    total = a + b + c
    if total <= 0:
        raise ValueError("Ternary components must have a positive sum")
    return a / total, b / total, c / total


def ti_classification(tio2_wt: float | None, *, eligible_bulk_mare_basalt: bool) -> str | None:
    """Neal & Taylor (1992) thresholds; caller must establish eligible material context."""
    if tio2_wt is None or not eligible_bulk_mare_basalt or tio2_wt < 0:
        return None
    if tio2_wt < 1:
        return "Very low-Ti"
    if tio2_wt <= 6:
        return "Low-Ti"
    return "High-Ti"
