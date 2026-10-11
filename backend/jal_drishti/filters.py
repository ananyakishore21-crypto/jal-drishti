"""Query-filter parsing and validation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Iterable, List, Mapping, Optional

from .config import DEFAULT_CPCB_CLASS, FESTIVALS, PHASES
from .data_loader import slugify
from .models import Catalog, Reading

FILTER_FIELDS = ("year", "festival", "phase", "site", "parameter")


class FilterError(ValueError):
    def __init__(self, field: str, message: str, allowed: Optional[list] = None):
        super().__init__(message)
        self.field, self.message, self.allowed = field, message, allowed

    def to_dict(self) -> dict:
        d = {"field": self.field}
        if self.allowed is not None:
            d["allowed"] = self.allowed
        return d


@dataclass(frozen=True)
class Filters:
    years: Optional[FrozenSet[int]] = None
    festivals: Optional[FrozenSet[str]] = None
    phases: Optional[FrozenSet[str]] = None
    sites: Optional[FrozenSet[str]] = None
    parameters: Optional[FrozenSet[str]] = None

    def matches_event(self, year: int, festival: str) -> bool:
        return (self.years is None or year in self.years) and (self.festivals is None or festival in self.festivals)

    def matches(self, r: Reading) -> bool:
        return (self.matches_event(r.year, r.festival)
                and (self.phases is None or r.phase in self.phases)
                and (self.sites is None or r.site in self.sites)
                and (self.parameters is None or r.parameter in self.parameters))

    def with_sites(self, sites: Iterable[str]) -> "Filters":
        return Filters(self.years, self.festivals, self.phases, frozenset(sites), self.parameters)

    def as_dict(self) -> dict:
        def s(v, key=None):
            return None if v is None else sorted(v, key=key)
        return {"year": s(self.years), "festival": s(self.festivals, FESTIVALS.index),
                "phase": s(self.phases, PHASES.index), "site": s(self.sites), "parameter": s(self.parameters)}


def split_values(raw: Optional[str]) -> List[str]:
    return [] if raw is None else [p.strip() for p in raw.split(",") if p.strip()]


def resolve_site(token: str, catalog: Catalog) -> Optional[str]:
    t = token.strip()
    for name in catalog.sites:
        if name.lower() == t.lower():
            return name
    return catalog.site_ids.get(slugify(t))


def parse_filters(raw: Mapping[str, Optional[str]], catalog: Catalog,
                  allowed_fields: Iterable[str] = FILTER_FIELDS) -> Filters:
    allowed_fields = set(allowed_fields)
    years = festivals = phases = sites = params = None

    if "year" in allowed_fields and split_values(raw.get("year")):
        out = set()
        for v in split_values(raw.get("year")):
            try:
                y = int(v)
            except ValueError:
                raise FilterError("year", f"year must be a whole number such as 2024; got {v!r}.", catalog.years) from None
            if y not in catalog.years:
                raise FilterError("year", f"No readings for year {y}.", catalog.years)
            out.add(y)
        years = frozenset(out)

    if "festival" in allowed_fields and split_values(raw.get("festival")):
        present = [f for f in FESTIVALS if any(e[1] == f for e in catalog.events)]
        out = set()
        for v in split_values(raw.get("festival")):
            match = next((f for f in present if f.lower() == v.lower()), None)
            if match is None:
                raise FilterError("festival", f"Unknown festival {v!r}.", present)
            out.add(match)
        festivals = frozenset(out)

    if "phase" in allowed_fields and split_values(raw.get("phase")):
        out = set()
        for v in split_values(raw.get("phase")):
            if v.lower() not in PHASES:
                raise FilterError("phase", f"Unknown phase {v!r}. Use pre (before), during or after (one week after).", list(PHASES))
            out.add(v.lower())
        phases = frozenset(out)

    if "site" in allowed_fields and split_values(raw.get("site")):
        out = set()
        for v in split_values(raw.get("site")):
            name = resolve_site(v, catalog)
            if name is None:
                raise FilterError("site", f"Unknown ghat {v!r}. Use a name or id from /api/ghats.",
                                  [{"site": n, "site_id": i.site_id} for n, i in catalog.sites.items()])
            out.add(name)
        sites = frozenset(out)

    if "parameter" in allowed_fields and split_values(raw.get("parameter")):
        out = set()
        for v in split_values(raw.get("parameter")):
            match = next((p for p in catalog.parameters if p.lower() == v.lower() or slugify(p) == slugify(v)), None)
            if match is None:
                raise FilterError("parameter", f"Unknown parameter {v!r}.", catalog.parameters)
            out.add(match)
        params = frozenset(out)

    return Filters(years, festivals, phases, sites, params)


def parse_cpcb_class(raw: Optional[str], classes: List[str], default: Optional[str] = DEFAULT_CPCB_CLASS) -> Optional[str]:
    vals = split_values(raw)
    if not vals:
        return default
    if len(vals) > 1:
        raise FilterError("cpcb_class", "Give one CPCB class, e.g. B.", classes)
    v = vals[0].upper()
    if v not in classes:
        raise FilterError("cpcb_class", f"Unknown CPCB class {vals[0]!r}.", classes)
    return v


def parse_int(raw: Optional[str], field: str, default: int, minimum: int, maximum: Optional[int]) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        v = int(raw.strip())
    except ValueError:
        raise FilterError(field, f"{field} must be a whole number; got {raw!r}.") from None
    if v < minimum or (maximum is not None and v > maximum):
        rng = f"{minimum}–{maximum}" if maximum is not None else f">= {minimum}"
        raise FilterError(field, f"{field} must be in {rng}; got {v}.")
    return v
