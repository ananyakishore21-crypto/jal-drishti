from fastapi.testclient import TestClient

from jal_drishti.api import create_app


def test_health_ok(client):
    body = client.get("/api/health").json()
    assert body["data"]["status"] == "ok" and body["data"]["row_counts"]["readings"] == 1524


def test_health_and_endpoints_report_missing_data_files(tmp_path):
    c = TestClient(create_app(tmp_path))
    assert c.get("/api/health").status_code == 503
    r = c.get("/api/readings")
    assert r.status_code == 503 and r.json()["error"]["code"] == "data_unavailable"


def test_ghats_list_and_rani_caveat(client):
    data = {g["site"]: g for g in client.get("/api/ghats").json()["data"]}
    assert len(data) == 7
    rani = data["Rani Kamlapati ghat / Kamla Park kund"]
    assert rani["site_match_confidence"] == "medium" and any("two different places" in c for c in rani["caveats"])
    assert {"year": 2025, "festival": "Durga"} in data["Malikhedi kund"]["events_without_table"]


def test_filters(client):
    assert client.get("/api/readings?year=2025").json()["meta"]["total"] == 453
    assert client.get("/api/readings?year=2025&festival=durga").json()["meta"]["total"] == 180
    rows = client.get("/api/readings?site=prempura-ghat&phase=during&parameter=BOD").json()["data"]
    assert rows and all(r["site"] == "Prempura ghat" and r["phase"] == "during" and r["parameter"] == "BOD" for r in rows)
    by_name = client.get("/api/readings", params={"site": "Prempura ghat"}).json()["meta"]["total"]
    assert by_name == client.get("/api/readings?site=prempura-ghat").json()["meta"]["total"]
    assert client.get("/api/readings?year=2023,2024").json()["meta"]["total"] == 1524 - 453


def test_reading_comparisons(client):
    rows = client.get("/api/readings?parameter=Chromium&year=2023").json()["data"]
    assert all(r["comparison"]["status"] == "no_criterion" for r in rows)
    bdl = [r for r in rows if r["measurement_status"] == "below_detection"]
    assert bdl and all(r["value"] is None and r["value_as_printed"] == "BDL" for r in bdl)


def test_summary_bdl_not_zero(client):
    p = client.get("/api/summary?year=2023&parameter=Chromium").json()["data"]["parameters"][0]
    assert (p["measured"], p["below_detection"], p["missing"], p["min"]) == (0, 41, 1, None)


def test_coverage_marks_missing_table(client):
    sites = client.get("/api/coverage?year=2025&festival=Durga").json()["data"]["sites"]
    bair = next(s for s in sites if s["site_id"] == "bairagarh-sant-hirdaram-kund")
    assert bair["events"][0]["status"] == "no_table_in_report" and bair["reported_readings"] == 0


def test_ghat_detail_and_404(client):
    r = client.get("/api/ghats/rani-kamlapati-ghat-kamla-park-kund/readings?festival=Durga")
    assert r.status_code == 200 and r.json()["data"]["assessment"]["readings_compared"] > 0
    r = client.get("/api/ghats/nowhere/readings")
    assert r.status_code == 404 and r.json()["error"]["code"] == "ghat_not_found"


def test_rankings_shape(client):
    rows = client.get("/api/rankings?festival=Durga").json()["data"]["rankings"]
    assert all(r["reasons"] and "readings_missing" in r for r in rows)


def test_brief(client):
    d = client.get("/api/brief?festival=Durga&top=3").json()["data"]
    assert len(d["top_sites"]) == 3
    assert any("\u0900" <= ch <= "\u097F" for ch in d["hi"]["text"])
    assert "health effects" in d["en"]["text"] and "स्वास्थ्य" in d["hi"]["text"]
    assert "hi" not in client.get("/api/brief?lang=en").json()["data"]


def test_errors(client):
    for url, field in [("/api/readings?year=2019", "year"), ("/api/readings?year=abc", "year"),
                       ("/api/readings?phase=later", "phase"), ("/api/readings?site=xyz", "site"),
                       ("/api/readings?parameter=Mercury", "parameter"), ("/api/criteria?cpcb_class=Z", "cpcb_class"),
                       ("/api/brief?top=0", "top"), ("/api/brief?top=abc", "top"), ("/api/brief?lang=fr", "lang"),
                       ("/api/rankings?parameter=Zinc", "parameter")]:
        r = client.get(url)
        assert r.status_code == 400, url
        assert r.json()["error"]["details"]["field"] == field
    r = client.get("/api/readings?festval=Durga")
    assert r.status_code == 400 and r.json()["error"]["code"] == "unknown_query_parameter"
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
