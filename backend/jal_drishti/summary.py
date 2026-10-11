from __future__ import annotations

from collections import Counter
from statistics import median

from .config import PARAMETER_LABELS_EN
from .coverage import scope_events, scope_parameters, scope_phases, scope_sites, site_slots, summarize_slots
from .criteria import FAILS, MEETS, MISSING, NOT_COMPARED, compare, criteria_map, criterion_to_dict, limit_phrase
from .filters import Filters
from .models import Dataset


def _headline(param, c, fails, compared, missing):
    label = PARAMETER_LABELS_EN.get(param, param)
    verb = {"min": "below", "max": "above", "range": "outside"}[c.limit_type]
    text = f"{fails} of {compared} measured {label} readings are {verb} the {limit_phrase(c)}."
    if missing:
        text += f" {missing} missing readings are not counted."
    return text


def build_summary(ds: Dataset, f: Filters, cls: str) -> dict:
    cat = ds.catalog
    rows = [r for r in ds.readings if f.matches(r)]
    cmap = criteria_map(ds.criteria, cls, cat.parameters)
    params_out, headlines = [], []
    for p in cat.parameters:
        prow = [r for r in rows if r.parameter == p]
        if not prow:
            continue
        vals = [r.value for r in prow if r.measurement_status == "measured"]
        sc = Counter(r.measurement_status for r in prow)
        entry = {"parameter": p, "unit_assumed": cat.parameter_units.get(p) or None, "rows": len(prow),
                 "measured": sc["measured"], "below_detection": sc["below_detection"], "missing": sc["missing"],
                 "min": min(vals) if vals else None, "max": max(vals) if vals else None,
                 "median": round(median(vals), 4) if vals else None}
        c = cmap.get(p)
        if c:
            cc = Counter(compare(r, c).status for r in prow)
            compared = cc[MEETS] + cc[FAILS]
            entry["criterion"] = criterion_to_dict(c)
            entry["comparison"] = {"compared": compared, "meets": cc[MEETS], "does_not_meet": cc[FAILS],
                                   "not_compared_below_detection": cc[NOT_COMPARED], "missing": cc[MISSING],
                                   "share_not_meeting": round(cc[FAILS] / compared, 3) if compared else None}
            if compared:
                headlines.append(_headline(p, c, cc[FAILS], compared, cc[MISSING]))
        else:
            entry["criterion"] = None
            entry["comparison"] = {"status": "no_criterion",
                                   "note": f"CPCB Class {cls} sets no limit for {p}; values are reported without comparison."}
        params_out.append(entry)

    events, phases, params = scope_events(ds, f), scope_phases(f), scope_parameters(ds, f)
    slots = [s for site in scope_sites(ds, f) for s in site_slots(ds, site, events, phases, params)]
    sc = Counter(r.measurement_status for r in rows)
    return {"scope": {"events": [{"year": y, "festival": fe} for y, fe in events], "phases": phases,
                      "sites": scope_sites(ds, f)},
            "counts": {"rows": len(rows), "measured": sc["measured"], "below_detection": sc["below_detection"],
                       "missing": sc["missing"]},
            "coverage": summarize_slots(slots), "headlines": headlines, "parameters": params_out}
