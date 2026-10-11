"""Direction-aware comparison of readings with CPCB criteria."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from .models import Criterion, Reading

MEETS, FAILS, MISSING, NOT_COMPARED, NO_CRITERION = "meets", "does_not_meet", "missing", "not_compared", "no_criterion"


def fmt(x: float) -> str:
    return f"{x:g}"


def unit_suffix(unit: str) -> str:
    return f" {unit}" if unit else ""


def available_classes(criteria: Iterable[Criterion]) -> List[str]:
    return sorted({c.cpcb_class for c in criteria})


def criteria_for_class(criteria: Iterable[Criterion], cls: str) -> List[Criterion]:
    return [c for c in criteria if c.cpcb_class == cls]


def criteria_map(criteria: Iterable[Criterion], cls: str, measured_parameters: Iterable[str]) -> Dict[str, Criterion]:
    """dataset parameter -> criterion, only for criteria whose parameter was actually measured."""
    measured = set(measured_parameters)
    return {c.dataset_parameter: c for c in criteria_for_class(criteria, cls) if c.dataset_parameter in measured}


def limit_text(c: Criterion) -> str:
    u = unit_suffix(c.unit)
    if c.limit_type == "min":
        return f"minimum of {fmt(c.lower)}{u}"
    if c.limit_type == "max":
        return f"maximum of {fmt(c.upper)}{u}"
    return f"range of {fmt(c.lower)}–{fmt(c.upper)}{u}"


def limit_phrase(c: Criterion) -> str:
    return f"Class {c.cpcb_class} {limit_text(c)}"


def criterion_to_dict(c: Criterion) -> dict:
    return {"cpcb_class": c.cpcb_class, "designated_best_use": c.designated_best_use, "parameter": c.parameter,
            "dataset_parameter": c.dataset_parameter, "limit_type": c.limit_type, "limit": c.limit_raw,
            "lower": c.lower, "upper": c.upper, "unit": c.unit or None, "description": limit_phrase(c)}


def severity_scale(c: Criterion) -> float:
    if c.limit_type == "min":
        return c.lower
    if c.limit_type == "max":
        return c.upper
    return (c.upper - c.lower) / 2


@dataclass(frozen=True)
class Comparison:
    status: str
    criterion: Optional[Criterion]
    explanation: str
    deviation: Optional[str] = None   # below_min | above_max | below_range | above_range
    gap: Optional[float] = None
    severity: Optional[float] = None  # min(gap / scale, 1)

    def to_dict(self) -> dict:
        d = {"status": self.status, "explanation": self.explanation}
        if self.criterion is not None:
            c = self.criterion
            d["criterion"] = {"cpcb_class": c.cpcb_class, "limit_type": c.limit_type, "limit": c.limit_raw,
                              "unit": c.unit or None}
        if self.status == FAILS:
            d.update(deviation=self.deviation, gap=round(self.gap, 4), severity=round(self.severity, 3))
        return d


def compare(reading: Reading, c: Criterion) -> Comparison:
    p = reading.parameter
    if reading.measurement_status == "missing":
        return Comparison(MISSING, c, f"{p}: not sampled / no value in the report. Not counted as meeting or failing the {limit_phrase(c)}.")
    if reading.measurement_status == "below_detection":
        return Comparison(NOT_COMPARED, c, f"{p}: reported below detection limit ({reading.value_as_printed.strip() or reading.flag}). The detection limit is not stated, so it is not compared.")
    v = reading.value
    shown = f"{p} {fmt(v)}{unit_suffix(reading.unit_assumed)}"
    phrase = limit_phrase(c)
    if c.limit_type == "min":
        if v >= c.lower:
            return Comparison(MEETS, c, f"{shown} is at or above the {phrase} (meets the criterion).")
        gap, dev, text = c.lower - v, "below_min", f"{shown} is below the {phrase}."
    elif c.limit_type == "max":
        if v <= c.upper:
            return Comparison(MEETS, c, f"{shown} is at or below the {phrase} (meets the criterion).")
        gap, dev, text = v - c.upper, "above_max", f"{shown} exceeds the {phrase}."
    else:
        if c.lower <= v <= c.upper:
            return Comparison(MEETS, c, f"{shown} is within the {phrase} (meets the criterion).")
        if v < c.lower:
            gap, dev, text = c.lower - v, "below_range", f"{shown} is below the {phrase}."
        else:
            gap, dev, text = v - c.upper, "above_range", f"{shown} is above the {phrase}."
    scale = severity_scale(c)
    severity = min(gap / scale, 1.0) if scale > 0 else 1.0
    return Comparison(FAILS, c, text, dev, gap, severity)


def no_criterion(reading: Reading, cls: str) -> Comparison:
    return Comparison(NO_CRITERION, None, f"CPCB Class {cls} sets no limit for {reading.parameter}; the value is reported without comparison.")


def compare_with_class(reading: Reading, cmap: Dict[str, Criterion], cls: str) -> Comparison:
    c = cmap.get(reading.parameter)
    return compare(reading, c) if c else no_criterion(reading, cls)
