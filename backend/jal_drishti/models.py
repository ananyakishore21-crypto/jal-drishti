from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

Event = Tuple[int, str]                       # (year, festival)
ReadingKey = Tuple[int, str, str, str, str]   # (year, festival, site, phase, parameter)


@dataclass(frozen=True)
class Reading:
    line: int
    year: int
    festival: str
    site: str
    site_id: str
    water_body: str
    phase: str
    parameter: str
    value: Optional[float]
    unit_assumed: str
    flag: str
    value_as_printed: str
    parameter_as_printed: str
    site_as_printed: str
    site_match_confidence: str
    source_page: Optional[int]
    measurement_status: str  # "measured" | "below_detection" | "missing"

    @property
    def key(self) -> ReadingKey:
        return (self.year, self.festival, self.site, self.phase, self.parameter)


@dataclass(frozen=True)
class Criterion:
    cpcb_class: str
    designated_best_use: str
    parameter: str                     # as printed in the criteria CSV
    dataset_parameter: Optional[str]   # matching readings parameter, or None if not measured
    limit_type: str                    # "min" | "max" | "range"
    limit_raw: str
    lower: Optional[float]
    upper: Optional[float]
    unit: str


@dataclass
class SiteInfo:
    name: str
    site_id: str
    water_bodies: Set[str] = field(default_factory=set)
    confidences: Set[str] = field(default_factory=set)
    names_as_printed: Set[str] = field(default_factory=set)
    events: Set[Event] = field(default_factory=set)


@dataclass
class Catalog:
    years: List[int]
    events: List[Event]
    event_parameters: Dict[Event, Set[str]]
    sites: Dict[str, SiteInfo]
    site_ids: Dict[str, str]
    parameters: List[str]
    parameter_units: Dict[str, str]
    classes: List[str]


@dataclass
class Dataset:
    readings: List[Reading]
    criteria: List[Criterion]
    catalog: Catalog
    index: Dict[ReadingKey, Reading]
    readings_path: str
    criteria_path: str
    loaded_at: str
