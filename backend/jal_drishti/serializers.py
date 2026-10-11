from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable, List, Optional

from .config import (GLOBAL_CAVEATS, PHASE_LABELS_EN, READINGS_FILENAME, SITE_CAVEATS,
                     SITE_NAMES_HI, SOURCE_REPORTS)
from .criteria import compare_with_class
from .models import Criterion, Dataset, Reading


def source_ref(r: Reading) -> dict:
    rep = SOURCE_REPORTS.get(r.year, {})
    return {"report": rep.get("title"), "url": rep.get("url"), "page": r.source_page,
            "csv_file": f"data/{READINGS_FILENAME}", "csv_line": r.line}


def reading_to_dict(r: Reading, comparison: Optional[dict] = None) -> dict:
    return {
        "year": r.year, "festival": r.festival, "site": r.site, "site_id": r.site_id, "water_body": r.water_body,
        "phase": r.phase, "phase_label": PHASE_LABELS_EN[r.phase], "parameter": r.parameter,
        "value": r.value, "unit_assumed": r.unit_assumed or None, "unit_is_assumed": True,
        "measurement_status": r.measurement_status, "flag": r.flag or None,
        "value_as_printed": r.value_as_printed, "parameter_as_printed": r.parameter_as_printed,
        "site_as_printed": r.site_as_printed, "site_match_confidence": r.site_match_confidence,
        "source": source_ref(r), "comparison": comparison,
    }


def reading_with_comparison(r: Reading, cmap: Dict[str, Criterion], cls: str) -> dict:
    return reading_to_dict(r, compare_with_class(r, cmap, cls).to_dict())


def site_caveats(ds: Dataset, site: str) -> List[str]:
    info = ds.catalog.sites[site]
    out = []
    if site in SITE_CAVEATS:
        out.append(SITE_CAVEATS[site])
    elif "medium" in info.confidences:
        out.append("Site match confidence is medium: the standard name may not map cleanly to one place.")
    for y, f in ds.catalog.events:
        if (y, f) not in info.events:
            out.append(f"No {f} {y} table for this ghat in the report: those readings are missing, not clean.")
    return out


def caveats_for(ds: Dataset, sites: Iterable[str]) -> List[str]:
    out = list(GLOBAL_CAVEATS)
    for s in sites:
        out.extend(f"{s}: {c}" for c in site_caveats(ds, s))
    return out


def ghat_info(ds: Dataset, site: str) -> dict:
    info = ds.catalog.sites[site]
    rows = [r for r in ds.readings if r.site == site]
    counts = Counter(r.measurement_status for r in rows)
    ev = lambda e: {"year": e[0], "festival": e[1]}
    return {
        "site": site, "site_id": info.site_id, "name_hi": SITE_NAMES_HI.get(site, site),
        "water_body": ", ".join(sorted(info.water_bodies)),
        "site_match_confidence": ", ".join(sorted(info.confidences)),
        "names_as_printed": sorted(info.names_as_printed),
        "events_with_table": [ev(e) for e in ds.catalog.events if e in info.events],
        "events_without_table": [ev(e) for e in ds.catalog.events if e not in info.events],
        "reading_counts": {"rows": len(rows), "measured": counts["measured"],
                           "below_detection": counts["below_detection"], "missing": counts["missing"]},
        "caveats": site_caveats(ds, site),
    }
