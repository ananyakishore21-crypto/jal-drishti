"""Short officer brief in English and Hindi, generated only from the ranking and its evidence."""
from __future__ import annotations

from typing import List

from .config import (BRIEF_LABELS_EN, BRIEF_LABELS_HI, CLASS_USE_HI, FESTIVAL_LABELS_HI, FESTIVALS,
                     PARAMETER_LABELS_EN, PARAMETER_LABELS_HI, PHASE_LABELS_EN, PHASE_LABELS_HI, PHASE_SHORT_EN,
                     PHASE_SHORT_HI, PHASES, SITE_CAVEATS, SITE_CAVEATS_HI, SITE_NAMES_HI)
from .criteria import criteria_for_class, fmt, unit_suffix
from .filters import Filters
from .models import Criterion, Dataset
from .ranking import ParamStats, rank_ghats


def _years_text(years: List[int]) -> str:
    if not years:
        return "—"
    if len(years) > 1 and years == list(range(years[0], years[-1] + 1)):
        return f"{years[0]}–{years[-1]}"
    return ", ".join(str(y) for y in years)


def _std_en(c: Criterion) -> str:
    label, u = PARAMETER_LABELS_EN.get(c.dataset_parameter, c.dataset_parameter), unit_suffix(c.unit)
    if c.limit_type == "min":
        return f"{label} at least {fmt(c.lower)}{u}"
    if c.limit_type == "max":
        return f"{label} at most {fmt(c.upper)}{u}"
    return f"{label} {fmt(c.lower)}–{fmt(c.upper)}"


def _std_hi(c: Criterion) -> str:
    label, u = PARAMETER_LABELS_HI.get(c.dataset_parameter, c.dataset_parameter), unit_suffix(c.unit)
    if c.limit_type == "min":
        return f"{label} कम से कम {fmt(c.lower)}{u}"
    if c.limit_type == "max":
        return f"{label} अधिकतम {fmt(c.upper)}{u}"
    return f"{label} {fmt(c.lower)}–{fmt(c.upper)}"


def _frag_en(st: ParamStats) -> str:
    label, c = BRIEF_LABELS_EN.get(st.parameter, st.parameter), st.criterion
    if st.compared == 0:
        return f"{label} not available"
    if st.does_not_meet == 0:
        return f"{label} within the limit in all {st.compared}"
    r, _ = st.worst
    u = unit_suffix(c.unit)
    lim = {"min": f"below {fmt(c.lower or 0)}{u}", "max": f"above {fmt(c.upper or 0)}{u}",
           "range": f"outside {fmt(c.lower or 0)}–{fmt(c.upper or 0)}"}[c.limit_type]
    word = {"min": "lowest", "max": "highest", "range": "worst"}[c.limit_type]
    return (f"{label} {lim} in {st.does_not_meet} of {st.compared} ({word} {fmt(r.value)}{unit_suffix(r.unit_assumed)}, "
            f"{r.festival} {r.year} {PHASE_SHORT_EN[r.phase]}, p. {r.source_page})")


def _frag_hi(st: ParamStats) -> str:
    label, c = BRIEF_LABELS_HI.get(st.parameter, st.parameter), st.criterion
    if st.compared == 0:
        return f"{label} उपलब्ध नहीं"
    if st.does_not_meet == 0:
        return f"{label} सभी {st.compared} रीडिंग में मानक के भीतर"
    r, _ = st.worst
    u = unit_suffix(c.unit)
    lim = {"min": f"{fmt(c.lower or 0)}{u} से कम", "max": f"{fmt(c.upper or 0)}{u} से अधिक",
           "range": f"{fmt(c.lower or 0)}–{fmt(c.upper or 0)} की सीमा से बाहर"}[c.limit_type]
    word = {"min": "न्यूनतम", "max": "अधिकतम", "range": "सबसे दूर"}[c.limit_type]
    return (f"{label} {st.compared} में से {st.does_not_meet} रीडिंग में {lim} ({word} {fmt(r.value)}{unit_suffix(r.unit_assumed)}, "
            f"{FESTIVAL_LABELS_HI[r.festival]} {r.year} {PHASE_SHORT_HI[r.phase]}, पृष्ठ {r.source_page})")


def build_brief(ds: Dataset, f: Filters, cls: str, top: int) -> dict:
    res = rank_ghats(ds, f, cls)
    ranked = [a for a in res.assessments if a.rank is not None]
    unassessed = [a for a in res.assessments if a.rank is None]
    chosen = ranked[:top]
    limited = [a for a in ranked if a.coverage_level in ("medium", "low")]
    years = sorted({y for y, _ in res.events})
    fests = [x for x in FESTIVALS if any(e[1] == x for e in res.events)]
    yt = _years_text(years)
    all_phases = len(res.phases) == len(PHASES)
    scope_en = f"{' and '.join(fests)} visarjan, {yt}, " + ("all phases" if all_phases else ", ".join(PHASE_LABELS_EN[p] for p in res.phases))
    scope_hi = f"{' और '.join(FESTIVAL_LABELS_HI[x] for x in fests)} विसर्जन, {yt}, " + ("सभी चरण" if all_phases else ", ".join(PHASE_LABELS_HI[p] for p in res.phases))
    crit_all = criteria_for_class(ds.criteria, cls)
    use_en = crit_all[0].designated_best_use if crit_all else ""
    use_hi = CLASS_USE_HI.get(cls, use_en)
    total = sum(a.compared for a in ranked)
    name_hi = lambda a: SITE_NAMES_HI.get(a.site, a.site)

    en = [f"Based on MPPCB visarjan test reports ({yt}): {total} readings at {len(ranked)} ghats compared with "
          f"CPCB Class {cls} ({use_en}): " + ", ".join(_std_en(c) for c in res.criteria) + ".",
          "Ghats in order of priority for attention (how often and how far readings fall outside the criteria):"]
    hi = [f"आधार: MPPCB विसर्जन जाँच रिपोर्ट ({yt}); {len(ranked)} घाटों की {total} रीडिंग की तुलना CPCB श्रेणी {cls} "
          f"({use_hi}) मानक से: " + ", ".join(_std_hi(c) for c in res.criteria) + "।",
          "प्राथमिकता क्रम में घाट (मानक से बाहर रीडिंग कितनी बार और कितनी दूर):"]
    for a in chosen:
        en.append(f"{a.rank}. {a.site}: " + "; ".join(_frag_en(s) for s in a.stats)
                  + f". Data: {a.compared} of {a.expected} expected readings.")
        hi.append(f"{a.rank}. {name_hi(a)}: " + "; ".join(_frag_hi(s) for s in a.stats)
                  + f"। आँकड़े: {a.expected} में से {a.compared} अपेक्षित रीडिंग उपलब्ध।")
    if limited:
        en.append("Limited data: " + ", ".join(f"{a.site} ({a.compared} of {a.expected})" for a in limited)
                  + ". Missing readings are not counted as clean, and a lower rank is not evidence of better water.")
        hi.append("सीमित आँकड़े: " + ", ".join(f"{name_hi(a)} ({a.expected} में से {a.compared})" for a in limited)
                  + "। अनुपलब्ध रीडिंग को 'साफ़' नहीं माना गया है; निचली रैंक बेहतर पानी का प्रमाण नहीं है।")
    if unassessed:
        en.append("No comparable readings, not assessed: " + ", ".join(a.site for a in unassessed) + ".")
        hi.append("तुलना योग्य रीडिंग नहीं, आकलन नहीं हुआ: " + ", ".join(name_hi(a) for a in unassessed) + "।")
    for a in chosen:
        if a.site in SITE_CAVEATS:
            en.append(f"Note: {SITE_CAVEATS[a.site]}")
            hi.append(f"ध्यान दें: {SITE_CAVEATS_HI.get(a.site, SITE_CAVEATS[a.site])}")
    en.append("This brief compares measured values with CPCB limits only; it does not assess health effects. "
              "Units are assumed (the reports print none).")
    hi.append("यह सारांश केवल मापे गए मानों की तुलना CPCB मानकों से करता है; यह स्वास्थ्य प्रभाव का आकलन नहीं है। "
              "इकाइयाँ मानी गई हैं (रिपोर्ट में इकाइयाँ नहीं छपी हैं)।")
    en.append(f"Source: MPPCB visarjan reports {yt}; 'p.' = PDF page of that year's report.")
    hi.append(f"स्रोत: MPPCB विसर्जन रिपोर्ट {yt}; 'पृष्ठ' = उस वर्ष की रिपोर्ट का PDF पृष्ठ।")

    title_en, title_hi = f"Jal Drishti ghat brief — {scope_en}", f"जल दृष्टि घाट सारांश — {scope_hi}"
    return {
        "scope": {"label_en": scope_en, "label_hi": scope_hi, "cpcb_class": cls,
                  "events": [{"year": y, "festival": x} for y, x in res.events], "phases": res.phases},
        "top_sites": [a.site_id for a in chosen],
        "en": {"title": title_en, "lines": en, "text": "\n".join([title_en] + en)},
        "hi": {"title": title_hi, "lines": hi, "text": "\n".join([title_hi] + hi)},
        "notes": ["Generated from /api/rankings for the same filters.",
                  "Hindi text is template-generated; have a Hindi speaker review before forwarding."],
    }
