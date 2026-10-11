"""Deterministic, explainable ghat ranking. See README 'Ranking method'."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .config import FESTIVALS, PHASE_LABELS_EN, PHASES, SITE_NAMES_HI
from .coverage import (BDL, MISSING_REASONS_EN, MISSING_STATUSES, Slot, coverage_level, scope_events,
                       scope_parameters, scope_phases, scope_sites, site_slots)
from .criteria import (FAILS, MEETS, NOT_COMPARED, Comparison, compare, criteria_for_class, criteria_map,
                       criterion_to_dict, fmt, limit_phrase, unit_suffix)
from .filters import FilterError, Filters
from .models import Criterion, Dataset, Event, Reading
from .serializers import reading_to_dict, site_caveats

EVIDENCE_LIMIT = 5


def _chron(r: Reading):
    return (r.year, FESTIVALS.index(r.festival), PHASES.index(r.phase))


def _badness(v: float, c: Criterion) -> float:
    if c.limit_type == "min":
        return -v
    if c.limit_type == "max":
        return v
    return abs(v - (c.lower + c.upper) / 2)


@dataclass
class ParamStats:
    parameter: str
    criterion: Criterion
    expected: int = 0
    compared: int = 0
    meets: int = 0
    does_not_meet: int = 0
    not_compared: int = 0
    missing: int = 0
    points: float = 0.0
    max_severity: float = 0.0
    items: List[Tuple[Reading, Comparison]] = field(default_factory=list)

    @property
    def worst(self) -> Optional[Tuple[Reading, Comparison]]:
        if not self.items:
            return None
        return sorted(self.items, key=lambda it: (-_badness(it[0].value, self.criterion), _chron(it[0])))[0]

    @property
    def failures(self) -> List[Tuple[Reading, Comparison]]:
        return [it for it in self.items if it[1].status == FAILS]


@dataclass
class SiteAssessment:
    site: str
    site_id: str
    stats: List[ParamStats]
    slots: List[Slot]
    rank: Optional[int] = None

    compared = property(lambda s: sum(p.compared for p in s.stats))
    expected = property(lambda s: sum(p.expected for p in s.stats))
    does_not_meet = property(lambda s: sum(p.does_not_meet for p in s.stats))
    not_compared = property(lambda s: sum(p.not_compared for p in s.stats))
    missing = property(lambda s: sum(p.missing for p in s.stats))
    points = property(lambda s: sum(p.points for p in s.stats))
    max_severity = property(lambda s: max([p.max_severity for p in s.stats] or [0.0]))

    @property
    def score(self) -> Optional[float]:
        return self.points / self.compared if self.compared else None

    @property
    def coverage_level(self) -> str:
        return coverage_level(self.compared, self.expected)


@dataclass
class RankingResult:
    cpcb_class: str
    criteria: List[Criterion]
    events: List[Event]
    phases: List[str]
    assessments: List[SiteAssessment]


def assess_site(ds: Dataset, site: str, events, phases, params, cmap: Dict[str, Criterion]) -> SiteAssessment:
    slots = site_slots(ds, site, events, phases, params)
    stats = OrderedDict((p, ParamStats(p, cmap[p])) for p in params)
    for s in slots:
        st = stats[s.parameter]
        st.expected += 1
        if s.reading is None or s.reading.measurement_status == "missing":
            st.missing += 1
            continue
        cmp = compare(s.reading, st.criterion)
        if cmp.status == NOT_COMPARED:
            st.not_compared += 1
            continue
        st.compared += 1
        st.items.append((s.reading, cmp))
        if cmp.status == MEETS:
            st.meets += 1
        else:
            st.does_not_meet += 1
            st.points += 1.0 + cmp.severity
            st.max_severity = max(st.max_severity, cmp.severity)
    return SiteAssessment(site, ds.catalog.sites[site].site_id, list(stats.values()), slots)


def _ranking_scope(ds: Dataset, f: Filters, cls: str):
    cmap = criteria_map(ds.criteria, cls, ds.catalog.parameters)
    params = scope_parameters(ds, f, restrict=cmap)
    return cmap, params


def rank_ghats(ds: Dataset, f: Filters, cls: str) -> RankingResult:
    cmap, params = _ranking_scope(ds, f, cls)
    if not params:
        raise FilterError("parameter", f"None of the selected parameters has a CPCB Class {cls} criterion, so there is nothing to rank.",
                          sorted(cmap))
    events, phases = scope_events(ds, f), scope_phases(f)
    assessments = [assess_site(ds, s, events, phases, params, cmap) for s in scope_sites(ds, f)]
    ranked = sorted((a for a in assessments if a.score is not None),
                    key=lambda a: (-round(a.score, 9), -a.does_not_meet, -round(a.max_severity, 9), a.site))
    unranked = sorted((a for a in assessments if a.score is None), key=lambda a: a.site)
    for i, a in enumerate(ranked, start=1):
        a.rank = i
    return RankingResult(cls, [cmap[p] for p in params], events, phases, ranked + unranked)


# ---------- explanation ----------

def event_text(r: Reading) -> str:
    return f"{r.festival} {r.year}, {PHASE_LABELS_EN[r.phase]}, report p. {r.source_page}"


def param_reason(st: ParamStats) -> str:
    c, label, phrase = st.criterion, st.parameter, limit_phrase(st.criterion)
    if st.compared == 0:
        return f"{label}: no measured readings in this selection ({st.missing} missing), so it could not be compared with the {phrase}."
    if st.does_not_meet == 0:
        return f"{label} met the {phrase} in all {st.compared} measured readings."
    r, _ = st.worst
    verb = {"min": "was below", "max": "was above", "range": "was outside"}[c.limit_type]
    word = {"min": "lowest", "max": "highest", "range": "furthest from the range"}[c.limit_type]
    return (f"{label} {verb} the {phrase} in {st.does_not_meet} of {st.compared} measured readings; "
            f"{word} {fmt(r.value)}{unit_suffix(r.unit_assumed)} ({event_text(r)}).")


def missing_groups(a: SiteAssessment) -> List[dict]:
    groups = OrderedDict()
    for s in a.slots:
        if s.status in MISSING_STATUSES or s.status == BDL:
            key = (s.year, s.festival, s.status)
            groups[key] = groups.get(key, 0) + 1
    return [{"year": y, "festival": f, "reason": st, "count": n} for (y, f, st), n in groups.items()]


def coverage_reason(a: SiteAssessment) -> str:
    if a.expected == 0:
        return "No readings were expected for this selection."
    text = f"Assessed on {a.compared} of {a.expected} expected readings ({round(100 * a.compared / a.expected)}%)."
    parts = [f"{g['festival']} {g['year']}: "
             f"{MISSING_REASONS_EN.get(g['reason'], 'below detection, not compared')} ({g['count']})"
             for g in missing_groups(a)]
    if parts:
        text += " Not compared: " + "; ".join(parts) + "."
    if a.coverage_level in ("medium", "low"):
        text += " With fewer readings the result is less certain; missing readings are not treated as meeting the criteria."
    return text


def reasons(a: SiteAssessment) -> List[str]:
    if a.score is None:
        return ["No comparable readings in this selection. This ghat is not ranked; that is not evidence that its water meets the criteria.",
                coverage_reason(a)]
    failing = sorted((s for s in a.stats if s.does_not_meet), key=lambda s: -s.does_not_meet)
    others = [s for s in a.stats if not s.does_not_meet]
    return [param_reason(s) for s in failing + others] + [coverage_reason(a)]


def param_to_dict(st: ParamStats) -> dict:
    w = st.worst
    return {"parameter": st.parameter, "criterion": criterion_to_dict(st.criterion), "expected": st.expected,
            "compared": st.compared, "meets": st.meets, "does_not_meet": st.does_not_meet, "missing": st.missing,
            "below_detection_not_compared": st.not_compared, "points": round(st.points, 3),
            "worst_reading": reading_to_dict(w[0], w[1].to_dict()) if w else None}


def assessment_to_dict(a: SiteAssessment, ds: Dataset) -> dict:
    info = ds.catalog.sites[a.site]
    fails = sorted((it for st in a.stats for it in st.failures),
                   key=lambda it: (-it[1].severity, _chron(it[0]), it[0].parameter))
    return {
        "rank": a.rank, "assessable": a.score is not None, "site": a.site, "site_id": a.site_id,
        "name_hi": SITE_NAMES_HI.get(a.site, a.site), "water_body": ", ".join(sorted(info.water_bodies)),
        "site_match_confidence": ", ".join(sorted(info.confidences)),
        "score": round(a.score, 3) if a.score is not None else None,
        "score_detail": {"points": round(a.points, 3), "readings_compared": a.compared,
                         "max_single_severity": round(a.max_severity, 3)},
        "readings_compared": a.compared, "readings_outside_criteria": a.does_not_meet,
        "share_outside_criteria": round(a.does_not_meet / a.compared, 3) if a.compared else None,
        "readings_expected": a.expected, "readings_missing": a.missing,
        "readings_below_detection_not_compared": a.not_compared,
        "coverage_ratio": round(a.compared / a.expected, 3) if a.expected else None,
        "coverage_level": a.coverage_level, "low_coverage_warning": a.coverage_level != "high",
        "parameters": [param_to_dict(s) for s in a.stats], "reasons": reasons(a),
        "evidence": [reading_to_dict(r, c.to_dict()) for r, c in fails[:EVIDENCE_LIMIT]],
        "missing": missing_groups(a), "caveats": site_caveats(ds, a.site),
    }


def method_description(ds: Dataset, res: RankingResult) -> dict:
    cls = res.cpcb_class
    crit_all = criteria_for_class(ds.criteria, cls)
    used = {c.dataset_parameter for c in res.criteria}
    return {
        "cpcb_class": cls,
        "designated_best_use": crit_all[0].designated_best_use if crit_all else None,
        "parameters": [criterion_to_dict(c) for c in res.criteria],
        "score": ("Mean points per compared reading. A reading that meets its criterion scores 0. A reading that does "
                  "not meet it scores 1 + severity, where severity = min(gap / scale, 1); gap is the distance beyond "
                  "the limit; scale is the limit itself for minimum/maximum limits (5 mg/l for DO, 3 mg/l for BOD) "
                  "and half the range width for range limits (1 pH unit for 6.5–8.5). Score runs from 0 to 2."),
        "phases": "Before, during and after readings are weighted equally, so water already outside the criteria "
                  "before immersion also raises the score. Use phase=during,after to focus on the immersion period.",
        "missing_data": "Missing readings (not sampled, no table, not printed) are excluded from both numerator and "
                        "denominator; they never count as meeting or failing. BDL/ND readings are not compared "
                        "because the detection limit is not reported.",
        "tie_break": ["higher score", "more readings outside criteria", "larger single worst severity", "site name A–Z"],
        "coverage_levels": {"high": ">= 90% of expected readings compared", "medium": "60–89%", "low": "< 60%",
                            "none": "no comparable readings (not ranked)"},
        "not_scored": [p for p in ds.catalog.parameters if p not in used],
    }


def ranking_to_dict(res: RankingResult, ds: Dataset) -> dict:
    return {"method": method_description(ds, res),
            "scope": {"events": [{"year": y, "festival": f} for y, f in res.events], "phases": res.phases},
            "rankings": [assessment_to_dict(a, ds) for a in res.assessments]}


def assess_one_site(ds: Dataset, site: str, f: Filters, cls: str) -> Optional[dict]:
    cmap, params = _ranking_scope(ds, f, cls)
    if not params:
        return None
    a = assess_site(ds, site, scope_events(ds, f), scope_phases(f), params, cmap)
    d = assessment_to_dict(a, ds)
    d["rank_note"] = "Rank among ghats is only available from /api/rankings."
    return d
