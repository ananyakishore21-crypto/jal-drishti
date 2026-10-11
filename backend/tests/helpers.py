import csv
from pathlib import Path

PHASES = ("pre", "during", "after")
READINGS_HEADER = ["year", "festival", "site", "water_body", "phase", "parameter", "value", "unit_assumed", "flag",
                   "value_as_printed", "parameter_as_printed", "site_as_printed", "site_match_confidence", "source_page"]
CRITERIA_HEADER = ["class", "designated_best_use", "parameter", "limit_type", "limit", "unit"]
CRITERIA_ROWS = [
    {"class": "B", "designated_best_use": "Outdoor bathing (organised)", "parameter": "pH", "limit_type": "range", "limit": "6.5-8.5", "unit": ""},
    {"class": "B", "designated_best_use": "Outdoor bathing (organised)", "parameter": "Dissolved oxygen", "limit_type": "min", "limit": "5", "unit": "mg/l"},
    {"class": "B", "designated_best_use": "Outdoor bathing (organised)", "parameter": "BOD (5 days 20C)", "limit_type": "max", "limit": "3", "unit": "mg/l"},
    {"class": "E", "designated_best_use": "Irrigation industrial cooling controlled waste disposal", "parameter": "Electrical conductivity at 25C", "limit_type": "max", "limit": "2250", "unit": "micromhos/cm"},
]


def make_row(**kw):
    row = {"year": "2025", "festival": "Durga", "site": "Alpha ghat", "water_body": "Test lake", "phase": "pre",
           "parameter": "BOD", "value": "", "unit_assumed": "mg/l", "flag": "", "value_as_printed": None,
           "parameter_as_printed": None, "site_as_printed": None, "site_match_confidence": "high", "source_page": "1"}
    row.update({k: (str(v) if isinstance(v, (int, float)) else v) for k, v in kw.items()})
    if row["value_as_printed"] is None:
        row["value_as_printed"] = row["value"] or row["flag"]
    if row["parameter_as_printed"] is None:
        row["parameter_as_printed"] = row["parameter"]
    if row["site_as_printed"] is None:
        row["site_as_printed"] = row["site"]
    return row


def site_rows(site, do, bod, ph, year=2025, festival="Durga"):
    """do/bod/ph: 3 values for pre/during/after; None means 'not sampled'."""
    rows = []
    for param, vals, unit in (("Dissolved oxygen", do, "mg/l"), ("BOD", bod, "mg/l"), ("pH", ph, "")):
        for phase, v in zip(PHASES, vals):
            if v is None:
                rows.append(make_row(site=site, year=year, festival=festival, phase=phase, parameter=param,
                                     unit_assumed=unit, flag="not sampled", value_as_printed="_"))
            else:
                rows.append(make_row(site=site, year=year, festival=festival, phase=phase, parameter=param,
                                     unit_assumed=unit, value=v))
    return rows


def write_data(directory: Path, readings_rows, criteria_rows=CRITERIA_ROWS, readings_header=READINGS_HEADER):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "bhopal_ghats_2023_2025.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=readings_header, extrasaction="ignore")
        w.writeheader()
        w.writerows(readings_rows)
    with (directory / "cpcb_water_quality_criteria.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CRITERIA_HEADER)
        w.writeheader()
        w.writerows(criteria_rows)
    return directory
