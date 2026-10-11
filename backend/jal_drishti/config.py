"""Static configuration. Every value here comes from the track data pack / participant guide."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR_ENV = "JAL_DRISHTI_DATA_DIR"
FRONTEND_DIR_ENV = "JAL_DRISHTI_FRONTEND_DIR"
CORS_ENV = "JAL_DRISHTI_CORS_ORIGINS"
READINGS_FILENAME = "bhopal_ghats_2023_2025.csv"
CRITERIA_FILENAME = "cpcb_water_quality_criteria.csv"


def resolve_data_dir(override: Optional[Union[str, Path]] = None) -> Path:
    if override is not None:
        return Path(override)
    env = os.environ.get(DATA_DIR_ENV)
    return Path(env) if env else REPO_ROOT / "data"


def resolve_frontend_dir() -> Path:
    env = os.environ.get(FRONTEND_DIR_ENV)
    return Path(env) if env else REPO_ROOT / "frontend"


DEFAULT_CPCB_CLASS = "B"  # organised outdoor bathing
PHASES = ("pre", "during", "after")
FESTIVALS = ("Ganesh", "Durga")  # within a year, Ganesh comes before Durga

PHASE_LABELS_EN = {"pre": "before immersion", "during": "during immersion", "after": "one week after immersion"}
PHASE_LABELS_HI = {"pre": "विसर्जन से पहले", "during": "विसर्जन के दौरान", "after": "विसर्जन के एक सप्ताह बाद"}
PHASE_SHORT_EN = {"pre": "before", "during": "during", "after": "after"}
PHASE_SHORT_HI = {"pre": "पहले", "during": "दौरान", "after": "बाद"}
FESTIVAL_LABELS_HI = {"Ganesh": "गणेश", "Durga": "दुर्गा"}

# CPCB criteria-file parameter name -> parameter name used in the readings file.
CRITERIA_TO_DATASET_PARAMETER = {
    "pH": "pH",
    "Dissolved oxygen": "Dissolved oxygen",
    "BOD (5 days 20C)": "BOD",
    "Electrical conductivity at 25C": "Conductivity",  # micromhos/cm == µS/cm
}

PARAMETER_LABELS_EN = {"Dissolved oxygen": "dissolved oxygen", "BOD": "BOD", "pH": "pH", "Conductivity": "conductivity"}
BRIEF_LABELS_EN = {"Dissolved oxygen": "DO", "BOD": "BOD", "pH": "pH", "Conductivity": "Conductivity"}
PARAMETER_LABELS_HI = {"Dissolved oxygen": "घुलित ऑक्सीजन (DO)", "BOD": "BOD", "pH": "pH", "Conductivity": "चालकता"}
BRIEF_LABELS_HI = {"Dissolved oxygen": "DO", "BOD": "BOD", "pH": "pH", "Conductivity": "चालकता"}

CLASS_USE_HI = {
    "A": "बिना पारंपरिक उपचार, कीटाणुशोधन के बाद पेयजल स्रोत",
    "B": "संगठित बाहरी स्नान",
    "C": "पारंपरिक उपचार और कीटाणुशोधन के बाद पेयजल स्रोत",
    "D": "वन्यजीव और मत्स्य पालन",
    "E": "सिंचाई, औद्योगिक शीतलन, नियंत्रित अपशिष्ट निपटान",
}

# Devanagari transliterations of the standard names. Please have a Hindi speaker check them.
SITE_NAMES_HI = {
    "Bairagarh (Sant Hirdaram) kund": "बैरागढ़ (संत हिरदाराम) कुंड",
    "Khatlapura ghat": "खटलापुरा घाट",
    "Prempura ghat": "प्रेमपुरा घाट",
    "Rani Kamlapati ghat / Kamla Park kund": "रानी कमलापति घाट / कमला पार्क कुंड",
    "Hathaikheda dam / kund": "हथाईखेड़ा डैम / कुंड",
    "Malikhedi kund": "मालीखेड़ी कुंड",
    "Shahpura lake ghat": "शाहपुरा झील घाट",
}

SITE_CAVEATS = {
    "Rani Kamlapati ghat / Kamla Park kund": (
        "Site match confidence is medium. Ganesh tables print a 'Kamla Park ... murti visarjan kund' name and "
        "Durga tables print 'Rani Kamlapati visarjan ghat (lower lake)'. These may be two different places, "
        "so readings under this name may mix two locations."
    ),
}
SITE_CAVEATS_HI = {
    "Rani Kamlapati ghat / Kamla Park kund":
        "'रानी कमलापति घाट / कमला पार्क कुंड' दो अलग स्थान हो सकते हैं (नाम मिलान का विश्वास: मध्यम)।",
}

SOURCE_REPORTS = {
    2023: {"title": "MPPCB Idol Immersion Report 2023 (CPCB format)",
           "url": "https://www.mppcb.mp.gov.in/proc/mon/Idol_immer._Report_23_CPCB.pdf"},
    2024: {"title": "MPPCB Ganesh and Durga Visarjan Report 2024",
           "url": "https://www.mppcb.mp.gov.in/proc/mon/Ganesh_and_Durga_visarjan_report-2024.pdf"},
    2025: {"title": "MPPCB Ganesh and Durga Visarjan Report 2025",
           "url": "https://www.mppcb.mp.gov.in/proc/mon/Ganesh_and_Durga_visarjan_report-2025.pdf"},
}
CRITERIA_SOURCE = {"file": f"data/{CRITERIA_FILENAME}", "url": "https://cpcb.gov.in/water-quality-criteria/"}

GLOBAL_CAVEATS = [
    "Units are assumed: the MPPCB reports print no units, so the standard unit for each test is used.",
    "Blank cells, '_', '-', '*', '**' and 'not sampled' mean the reading is missing. Missing readings are never treated as meeting a criterion.",
    "BDL/ND mean below the detection limit: very low, but not zero and not missing. They are not converted to 0.",
    "Only four metals were tested (chromium, lead, zinc, copper). CPCB Class B sets no limit for them, so they are reported but not compared.",
    "Results compare readings with CPCB limits only. They do not describe health effects.",
    "Source pages are PDF page numbers in that year's MPPCB report.",
]
