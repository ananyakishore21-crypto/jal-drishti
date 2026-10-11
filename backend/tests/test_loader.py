import pytest
from helpers import READINGS_HEADER, make_row, write_data

from jal_drishti.data_loader import DataFileError, load_dataset


def test_real_dataset_shape(real_dataset):
    assert len(real_dataset.readings) == 1524
    assert len(real_dataset.catalog.sites) == 7
    assert real_dataset.catalog.events == [(2023, "Ganesh"), (2023, "Durga"), (2024, "Ganesh"),
                                           (2024, "Durga"), (2025, "Ganesh"), (2025, "Durga")]


def test_bdl_is_below_detection_not_zero(real_dataset):
    r = real_dataset.index[(2023, "Ganesh", "Khatlapura ghat", "pre", "Chromium")]
    assert r.value is None and r.measurement_status == "below_detection" and r.value_as_printed == "BDL"


@pytest.mark.parametrize("key,printed", [
    ((2023, "Ganesh", "Khatlapura ghat", "during", "Chromium"), "_"),
    ((2025, "Ganesh", "Malikhedi kund", "pre", "pH"), "*"),
    ((2025, "Ganesh", "Malikhedi kund", "after", "pH"), "**"),
    ((2025, "Ganesh", "Malikhedi kund", "pre", "BOD"), ""),
])
def test_blank_and_star_codes_are_missing(real_dataset, key, printed):
    r = real_dataset.index[key]
    assert r.value is None and r.measurement_status == "missing" and r.value_as_printed == printed


def test_zero_is_a_measurement(real_dataset):
    r = real_dataset.index[(2025, "Ganesh", "Bairagarh (Sant Hirdaram) kund", "during", "Dissolved oxygen")]
    assert r.value == 0.0 and r.measurement_status == "measured"


def test_provenance_preserved(real_dataset):
    r = real_dataset.index[(2025, "Durga", "Shahpura lake ghat", "pre", "Dissolved oxygen")]
    assert (r.value, r.unit_assumed, r.source_page, r.parameter_as_printed) == (2.5, "mg/l", 65, "D.Oxygen")


def test_nd_flag_is_below_detection(tmp_path):
    write_data(tmp_path, [make_row(parameter="Lead", flag="ND")])
    r = load_dataset(tmp_path).readings[0]
    assert r.measurement_status == "below_detection" and r.value is None


def test_missing_file(tmp_path):
    with pytest.raises(DataFileError) as e:
        load_dataset(tmp_path)
    assert "not found" in e.value.message


def test_missing_column(tmp_path):
    write_data(tmp_path, [make_row(value=2)], readings_header=[h for h in READINGS_HEADER if h != "source_page"])
    with pytest.raises(DataFileError) as e:
        load_dataset(tmp_path)
    assert "source_page" in e.value.message


def test_non_numeric_value_reports_line(tmp_path):
    write_data(tmp_path, [make_row(value="abc")])
    with pytest.raises(DataFileError) as e:
        load_dataset(tmp_path)
    assert "malformed" in e.value.message and any("line 2" in d for d in e.value.details)


def test_duplicate_reading_rejected(tmp_path):
    write_data(tmp_path, [make_row(value=2), make_row(value=3)])
    with pytest.raises(DataFileError) as e:
        load_dataset(tmp_path)
    assert "Duplicate" in e.value.message


def test_bad_criteria_range(tmp_path):
    bad = [{"class": "B", "designated_best_use": "x", "parameter": "pH", "limit_type": "range", "limit": "8.5", "unit": ""}]
    write_data(tmp_path, [make_row(value=2)], criteria_rows=bad)
    with pytest.raises(DataFileError):
        load_dataset(tmp_path)
