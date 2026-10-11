"""Expected-reading grid and missing-data accounting.

A slot is one (event, phase, parameter) that the report's table for that event covers (the parameter was
reported for at least one ghat in that event). For each ghat a slot is:
  measured | below_detection | not_sampled (row present, no value)
  | no_table_for_site (ghat has no table for that event) | row_absent (ghat has a table but not this row)
"""
from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass
from typing import Iterable, List, Optional

from .config import PHASES
from .filters import Filters
from .models import Dataset, Event, Reading

MEASURED, BDL, NOT_SAMPLED, NO_TABLE, ROW_ABSENT = "measured", "below_detection", "not_sampled", "no_table_for_site", "row_absent"
MISSING_STATUSES = (NOT_SAMPLED, NO_TABLE, ROW_ABSENT)
MISSING_REASONS_EN = {NOT_SAMPLED: "not sampled", NO_TABLE: "no table for this ghat in the report",
                      ROW_ABSENT: "not printed in the report table"}


@dataclass(frozen=True)
class Slot:
    year: int
    festival: str
    phase: str
    parameter: str
    status: str
    reading: Optional[Reading]

    @property
    def event(self) -> Event:
        return (self.year, self.festival)


def scope_events(ds: Dataset, f: Filters) -> List[Event]:
    return [e for e in ds.catalog.events if f.matches_event(*e)]


def scope_phases(f: Filters) -> List[str]:
    return [p for p in PHASES if f.phases is None or p in f.phases]


def scope_parameters(ds: Dataset, f: Filters, restrict: Optional[Iterable[str]] = None) -> List[str]:
    r = None if restrict is None else set(restrict)
    return [p for p in ds.catalog.parameters
            if (f.parameters is None or p in f.parameters) and (r is None or p in r)]


def scope_sites(ds: Dataset, f: Filters) -> List[str]:
    return [s for s in ds.catalog.sites if f.sites is None or s in f.sites]


def site_slots(ds: Dataset, site: str, events: List[Event], phases: List[str], params: List[str]) -> List[Slot]:
    info = ds.catalog.sites[site]
    slots = []
    for (year, fest) in events:
        has_table = (year, fest) in info.events
        reported = ds.catalog.event_parameters.get((year, fest), set())
        for phase in phases:
            for p in params:
                if p not in reported:
                    continue  # parameter not in that event's tables at all (e.g. suspended solids, Durga 2023)
                r = ds.index.get((year, fest, site, phase, p))
                if r is None:
                    status = ROW_ABSENT if has_table else NO_TABLE
                elif r.measurement_status == "missing":
                    status = NOT_SAMPLED
                else:
                    status = r.measurement_status
                slots.append(Slot(year, fest, phase, p, status, r))
    return slots


def coverage_level(reported: int, expected: int) -> str:
    if expected == 0 or reported == 0:
        return "none"
    ratio = reported / expected
    return "high" if ratio >= 0.9 else "medium" if ratio >= 0.6 else "low"


def summarize_slots(slots: List[Slot]) -> dict:
    c = Counter(s.status for s in slots)
    expected = len(slots)
    reported = c[MEASURED] + c[BDL]
    return {"expected_readings": expected, "reported_readings": reported, "measured": c[MEASURED],
            "below_detection": c[BDL], "missing": expected - reported,
            "missing_breakdown": {k: c[k] for k in MISSING_STATUSES},
            "coverage_ratio": round(reported / expected, 3) if expected else None,
            "coverage_level": coverage_level(reported, expected)}


def event_breakdown(slots: List[Slot]) -> List[dict]:
    groups = OrderedDict()
    for s in slots:
        groups.setdefault(s.event, []).append(s)
    out = []
    for (year, fest), ev in groups.items():
        summ = summarize_slots(ev)
        if all(s.status == NO_TABLE for s in ev):
            status = "no_table_in_report"
        elif summ["missing"] == 0:
            status = "complete"
        elif summ["reported_readings"] == 0:
            status = "none_reported"
        else:
            status = "partial"
        entry = {"year": year, "festival": fest, "status": status, **summ}
        if status == "no_table_in_report":
            entry["note"] = f"No {fest} {year} table for this ghat in the report. Missing, not clean."
        else:
            entry["missing_slots"] = [{"phase": s.phase, "parameter": s.parameter, "reason": s.status}
                                      for s in ev if s.status in MISSING_STATUSES]
        out.append(entry)
    return out


def site_coverage(ds: Dataset, site: str, f: Filters) -> dict:
    slots = site_slots(ds, site, scope_events(ds, f), scope_phases(f), scope_parameters(ds, f))
    return {**summarize_slots(slots), "events": event_breakdown(slots)}


def build_coverage(ds: Dataset, f: Filters) -> dict:
    events, phases, params = scope_events(ds, f), scope_phases(f), scope_parameters(ds, f)
    sites_out, all_slots = [], []
    for site in scope_sites(ds, f):
        slots = site_slots(ds, site, events, phases, params)
        all_slots.extend(slots)
        info = ds.catalog.sites[site]
        sites_out.append({"site": site, "site_id": info.site_id,
                          "water_body": ", ".join(sorted(info.water_bodies)),
                          "site_match_confidence": ", ".join(sorted(info.confidences)),
                          **summarize_slots(slots), "events": event_breakdown(slots)})
    return {"scope": {"events": [{"year": y, "festival": fe} for y, fe in events], "phases": phases,
                      "parameters": params},
            "totals": summarize_slots(all_slots), "sites": sites_out}
