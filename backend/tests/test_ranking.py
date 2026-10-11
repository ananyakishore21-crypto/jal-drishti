import random

from helpers import site_rows, write_data

from jal_drishti.data_loader import build_dataset, load_dataset
from jal_drishti.filters import Filters
from jal_drishti.ranking import rank_ghats, ranking_to_dict


def _synthetic(tmp_path):
    rows = (site_rows("A worst", [2, 2, 2], [10, 10, 10], [7, 7, 7])
            + site_rows("B mild", [6, 6, 6], [4, 4, 4], [7, 7, 7])
            + site_rows("C meets", [6, 6, 6], [2, 2, 2], [7, 7, 7])
            + site_rows("D sparse", [None, None, None], [10, None, None], [None, None, None])
            + site_rows("E empty", [None] * 3, [None] * 3, [None] * 3))
    return load_dataset(write_data(tmp_path, rows))


def _by_site(ds, f=Filters()):
    return {r["site"]: r for r in ranking_to_dict(rank_ghats(ds, f, "B"), ds)["rankings"]}


def test_more_and_worse_exceedances_rank_higher(tmp_path):
    r = _by_site(_synthetic(tmp_path))
    assert r["A worst"]["rank"] < r["B mild"]["rank"] < r["C meets"]["rank"]
    assert r["C meets"]["score"] == 0


def test_bod_direction_in_ranking(tmp_path):
    r = _by_site(_synthetic(tmp_path))
    assert r["B mild"]["parameters"][1]["does_not_meet"] == 3   # BOD 4 > 3
    assert r["C meets"]["parameters"][1]["does_not_meet"] == 0  # BOD 2 <= 3


def test_missing_not_counted_as_pass_or_fail(tmp_path):
    d = _by_site(_synthetic(tmp_path))["D sparse"]
    assert d["readings_compared"] == 1 and d["readings_missing"] == 8
    assert d["share_outside_criteria"] == 1.0
    assert d["coverage_level"] == "low" and d["low_coverage_warning"] is True


def test_no_data_is_not_ranked(tmp_path):
    e = _by_site(_synthetic(tmp_path))["E empty"]
    assert e["rank"] is None and e["assessable"] is False and e["score"] is None
    assert "not evidence" in e["reasons"][0]


def test_tie_break_by_name(tmp_path):
    rows = site_rows("Beta", [4, 4, 4], [5, 5, 5], [7, 7, 7]) + site_rows("Alpha", [4, 4, 4], [5, 5, 5], [7, 7, 7])
    r = _by_site(load_dataset(write_data(tmp_path, rows)))
    assert r["Alpha"]["rank"] == 1 and r["Beta"]["rank"] == 2


def test_deterministic_regardless_of_row_order(real_dataset):
    base = ranking_to_dict(rank_ghats(real_dataset, Filters(), "B"), real_dataset)
    shuffled = list(real_dataset.readings)
    random.Random(7).shuffle(shuffled)
    ds2 = build_dataset(shuffled, real_dataset.criteria)
    again = ranking_to_dict(rank_ghats(ds2, Filters(), "B"), ds2)
    key = lambda d: [(r["site"], r["rank"], r["score"], r["reasons"]) for r in d["rankings"]]
    assert key(base) == key(again)


def test_real_ranking_evidence_traceable(real_dataset):
    res = ranking_to_dict(rank_ghats(real_dataset, Filters(), "B"), real_dataset)["rankings"]
    assert res[0]["site"] == "Bairagarh (Sant Hirdaram) kund"
    assert res[-1]["site"] == "Prempura ghat"
    top = res[0]
    assert (top["readings_compared"], top["readings_expected"], top["coverage_level"]) == (39, 54, "medium")
    for ev in top["evidence"]:
        assert ev["source"]["page"] and ev["comparison"]["status"] == "does_not_meet"
