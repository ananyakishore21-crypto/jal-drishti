import pytest

from jal_drishti.criteria import FAILS, MEETS, MISSING, NOT_COMPARED, compare
from jal_drishti.data_loader import classify_measurement
from jal_drishti.models import Criterion, Reading

BOD = Criterion("B", "Outdoor bathing (organised)", "BOD (5 days 20C)", "BOD", "max", "3", None, 3.0, "mg/l")
DO = Criterion("B", "Outdoor bathing (organised)", "Dissolved oxygen", "Dissolved oxygen", "min", "5", 5.0, None, "mg/l")
PH = Criterion("B", "Outdoor bathing (organised)", "pH", "pH", "range", "6.5-8.5", 6.5, 8.5, "")


def reading(param, value, flag="", printed=None):
    printed = printed if printed is not None else ("" if value is None else str(value))
    return Reading(2, 2025, "Durga", "Alpha ghat", "alpha-ghat", "x", "pre", param, value, "mg/l", flag, printed,
                   param, "Alpha ghat", "high", 1, classify_measurement(value, flag, printed))


@pytest.mark.parametrize("v,status,dev", [(2.4, MEETS, None), (3.0, MEETS, None), (3.1, FAILS, "above_max"), (11.2, FAILS, "above_max")])
def test_bod_direction(v, status, dev):
    c = compare(reading("BOD", v), BOD)
    assert c.status == status and c.deviation == dev
    if status == FAILS:
        assert "exceeds" in c.explanation


def test_bod_severity_is_relative_and_capped():
    assert compare(reading("BOD", 4.5), BOD).severity == pytest.approx(0.5)
    assert compare(reading("BOD", 22), BOD).severity == 1.0


@pytest.mark.parametrize("v,status,dev", [(6.4, MEETS, None), (5.0, MEETS, None), (4.9, FAILS, "below_min"), (0.0, FAILS, "below_min")])
def test_do_direction(v, status, dev):
    c = compare(reading("Dissolved oxygen", v), DO)
    assert c.status == status and c.deviation == dev


def test_do_zero_has_full_severity():
    assert compare(reading("Dissolved oxygen", 0.0), DO).severity == 1.0


@pytest.mark.parametrize("v,status,dev", [(6.5, MEETS, None), (8.5, MEETS, None), (6.49, FAILS, "below_range"), (8.92, FAILS, "above_range")])
def test_ph_range(v, status, dev):
    c = compare(reading("pH", v), PH)
    assert c.status == status and c.deviation == dev


def test_missing_is_never_meets():
    c = compare(reading("BOD", None, flag="not sampled", printed="_"), BOD)
    assert c.status == MISSING and c.status != MEETS


def test_bdl_is_not_compared():
    c = compare(reading("BOD", None, flag="BDL", printed="BDL"), BOD)
    assert c.status == NOT_COMPARED


def test_guide_headline_counts(client):
    params = {p["parameter"]: p for p in client.get("/api/summary").json()["data"]["parameters"]}
    do, bod, ph = (params[k]["comparison"] for k in ("Dissolved oxygen", "BOD", "pH"))
    assert (do["does_not_meet"], do["compared"], do["missing"]) == (42, 116, 4)
    assert (bod["does_not_meet"], bod["compared"], bod["missing"]) == (100, 112, 8)
    assert (ph["does_not_meet"], ph["compared"]) == (6, 115)
