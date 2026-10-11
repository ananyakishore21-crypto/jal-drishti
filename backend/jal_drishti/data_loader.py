"""Load and validate the CSV source-of-truth files. Fails loudly with useful messages."""
from __future__ import annotations

import csv
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

from .config import (CRITERIA_FILENAME, CRITERIA_TO_DATASET_PARAMETER, FESTIVALS, PHASES,
                     READINGS_FILENAME)
from .models import Catalog, Criterion, Dataset, Event, Reading, SiteInfo

READINGS_REQUIRED_COLUMNS = (
    "year", "festival", "site", "water_body", "phase", "parameter", "value", "unit_assumed", "flag",
    "value_as_printed", "parameter_as_printed", "site_as_printed", "site_match_confidence", "source_page",
)
CRITERIA_REQUIRED_COLUMNS = ("class", "designated_best_use", "parameter", "limit_type", "limit", "unit")
BELOW_DETECTION_CODES = frozenset({"BDL", "ND"})
MAX_REPORTED_ERRORS = 20
_RANGE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*$")


class DataFileError(Exception):
    def __init__(self, message: str, *, path: Optional[str] = None, details: Optional[List[str]] = None):
        super().__init__(message)
        self.message = message
        self.path = path
        self.details = details or []

    def to_dict(self) -> dict:
        return {"message": self.message, "path": self.path, "details": self.details}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def classify_measurement(value: Optional[float], flag: str, value_as_printed: str) -> str:
    """measured | below_detection (BDL/ND, never zero) | missing (blank, _, -, *, **, not sampled)."""
    if value is not None:
        return "measured"
    codes = {flag.strip().upper(), value_as_printed.strip().upper()}
    if codes & BELOW_DETECTION_CODES:
        return "below_detection"
    return "missing"


def _cell(row: dict, key: str) -> str:
    v = row.get(key)
    return v.strip() if isinstance(v, str) else ""


def _raw(row: dict, key: str) -> str:
    v = row.get(key)
    return v if isinstance(v, str) else ""


def _read_rows(path: Path, required: Sequence[str]) -> List[dict]:
    if not path.is_file():
        raise DataFileError(
            f"Data file not found: {path}. Put it in the data/ folder or set JAL_DRISHTI_DATA_DIR.",
            path=str(path))
    try:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            header = [h.strip() for h in (reader.fieldnames or [])]
            missing = [c for c in required if c not in header]
            if missing:
                raise DataFileError(
                    f"{path.name} is missing required column(s): {', '.join(missing)}.",
                    path=str(path), details=[f"found columns: {', '.join(header) or '(none)'}"])
            reader.fieldnames = header
            rows = list(reader)
    except UnicodeDecodeError as exc:
        raise DataFileError(f"{path.name} is not valid UTF-8 text: {exc}", path=str(path)) from exc
    except csv.Error as exc:
        raise DataFileError(f"{path.name} could not be parsed as CSV: {exc}", path=str(path)) from exc
    except OSError as exc:
        raise DataFileError(f"{path.name} could not be read: {exc}", path=str(path)) from exc
    if not rows:
        raise DataFileError(f"{path.name} has a header but no data rows.", path=str(path))
    return rows


def _parse_reading(line: int, row: dict) -> Reading:
    year_text = _cell(row, "year")
    try:
        year = int(year_text)
    except ValueError:
        raise ValueError(f"year {year_text!r} is not a whole number") from None
    festival_text = _cell(row, "festival")
    festival = next((f for f in FESTIVALS if f.lower() == festival_text.lower()), None)
    if festival is None:
        raise ValueError(f"festival {festival_text!r} is not one of {', '.join(FESTIVALS)}")
    phase = _cell(row, "phase").lower()
    if phase not in PHASES:
        raise ValueError(f"phase {phase!r} is not one of {', '.join(PHASES)}")
    site = _cell(row, "site")
    if not site or not slugify(site):
        raise ValueError("site is empty")
    parameter = _cell(row, "parameter")
    if not parameter:
        raise ValueError("parameter is empty")

    value_text = _cell(row, "value")
    value: Optional[float] = None
    if value_text:
        try:
            value = float(value_text)
        except ValueError:
            raise ValueError(f"value {value_text!r} is not a number") from None
        if not math.isfinite(value):
            raise ValueError(f"value {value_text!r} is not a finite number")

    page_text = _cell(row, "source_page")
    page: Optional[int] = None
    if page_text:
        try:
            page_f = float(page_text)
        except ValueError:
            raise ValueError(f"source_page {page_text!r} is not a number") from None
        if page_f < 1 or page_f != int(page_f):
            raise ValueError(f"source_page {page_text!r} is not a positive whole number")
        page = int(page_f)

    flag = _cell(row, "flag")
    printed = _raw(row, "value_as_printed")  # preserved exactly
    return Reading(
        line=line, year=year, festival=festival, site=site, site_id=slugify(site),
        water_body=_cell(row, "water_body"), phase=phase, parameter=parameter, value=value,
        unit_assumed=_cell(row, "unit_assumed"), flag=flag, value_as_printed=printed,
        parameter_as_printed=_raw(row, "parameter_as_printed"), site_as_printed=_raw(row, "site_as_printed"),
        site_match_confidence=_cell(row, "site_match_confidence").lower(), source_page=page,
        measurement_status=classify_measurement(value, flag, printed),
    )


def load_readings(path: Path) -> List[Reading]:
    rows = _read_rows(path, READINGS_REQUIRED_COLUMNS)
    readings, errors = [], []
    for line, row in enumerate(rows, start=2):  # line 1 is the header
        try:
            readings.append(_parse_reading(line, row))
        except ValueError as exc:
            errors.append(f"line {line}: {exc}")
    if errors:
        raise DataFileError(f"{len(errors)} malformed row(s) in {path.name}.", path=str(path),
                            details=errors[:MAX_REPORTED_ERRORS])
    return readings


def _parse_criterion(row: dict) -> Criterion:
    cls = _cell(row, "class").upper()
    if not cls:
        raise ValueError("class is empty")
    param = _cell(row, "parameter")
    if not param:
        raise ValueError("parameter is empty")
    limit_type = _cell(row, "limit_type").lower()
    limit = _cell(row, "limit")
    lower = upper = None
    if limit_type in ("min", "max"):
        try:
            v = float(limit)
        except ValueError:
            raise ValueError(f"limit {limit!r} is not a number") from None
        lower, upper = (v, None) if limit_type == "min" else (None, v)
    elif limit_type == "range":
        m = _RANGE_RE.match(limit)
        if not m:
            raise ValueError(f"range limit {limit!r} is not in 'low-high' form")
        lower, upper = float(m.group(1)), float(m.group(2))
        if lower >= upper:
            raise ValueError(f"range limit {limit!r} has low >= high")
    else:
        raise ValueError(f"limit_type {limit_type!r} must be min, max or range")
    return Criterion(cpcb_class=cls, designated_best_use=_cell(row, "designated_best_use"), parameter=param,
                     dataset_parameter=CRITERIA_TO_DATASET_PARAMETER.get(param), limit_type=limit_type,
                     limit_raw=limit, lower=lower, upper=upper, unit=_cell(row, "unit"))


def load_criteria(path: Path) -> List[Criterion]:
    rows = _read_rows(path, CRITERIA_REQUIRED_COLUMNS)
    out, errors, seen = [], [], {}
    for line, row in enumerate(rows, start=2):
        try:
            c = _parse_criterion(row)
        except ValueError as exc:
            errors.append(f"line {line}: {exc}")
            continue
        key = (c.cpcb_class, c.parameter)
        if key in seen:
            errors.append(f"line {line}: duplicate criterion for class {c.cpcb_class} {c.parameter} (first at line {seen[key]})")
            continue
        seen[key] = line
        out.append(c)
    if errors:
        raise DataFileError(f"{len(errors)} malformed row(s) in {path.name}.", path=str(path),
                            details=errors[:MAX_REPORTED_ERRORS])
    return out


def _event_key(e: Event):
    return (e[0], FESTIVALS.index(e[1]))


def build_catalog(readings: List[Reading], criteria: List[Criterion]) -> Catalog:
    sites: Dict[str, SiteInfo] = {}
    event_params: Dict[Event, set] = {}
    param_order: List[str] = []
    units: Dict[str, str] = {}
    for r in readings:
        info = sites.setdefault(r.site, SiteInfo(name=r.site, site_id=r.site_id))
        info.water_bodies.add(r.water_body)
        info.confidences.add(r.site_match_confidence)
        info.names_as_printed.add(r.site_as_printed)
        info.events.add((r.year, r.festival))
        event_params.setdefault((r.year, r.festival), set()).add(r.parameter)
        if r.parameter not in units:
            param_order.append(r.parameter)
            units[r.parameter] = r.unit_assumed
        elif not units[r.parameter] and r.unit_assumed:
            units[r.parameter] = r.unit_assumed
    sites = dict(sorted(sites.items()))
    site_ids: Dict[str, str] = {}
    for name, info in sites.items():
        if info.site_id in site_ids:
            raise DataFileError(f"Site names {site_ids[info.site_id]!r} and {name!r} produce the same id {info.site_id!r}.")
        site_ids[info.site_id] = name
    events = sorted(event_params, key=_event_key)
    return Catalog(years=sorted({y for y, _ in events}), events=events, event_parameters=event_params,
                   sites=sites, site_ids=site_ids, parameters=param_order, parameter_units=units,
                   classes=sorted({c.cpcb_class for c in criteria}))


def build_dataset(readings: List[Reading], criteria: List[Criterion],
                  readings_path: str = "", criteria_path: str = "") -> Dataset:
    index = {}
    for r in readings:
        if r.key in index:
            raise DataFileError(f"Duplicate reading for {r.key} at lines {index[r.key].line} and {r.line}.",
                                path=readings_path or None)
        index[r.key] = r
    return Dataset(readings=list(readings), criteria=list(criteria), catalog=build_catalog(readings, criteria),
                   index=index, readings_path=readings_path, criteria_path=criteria_path,
                   loaded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))


def load_dataset(data_dir: Union[str, Path]) -> Dataset:
    d = Path(data_dir)
    rp, cp = d / READINGS_FILENAME, d / CRITERIA_FILENAME
    return build_dataset(load_readings(rp), load_criteria(cp), str(rp), str(cp))
