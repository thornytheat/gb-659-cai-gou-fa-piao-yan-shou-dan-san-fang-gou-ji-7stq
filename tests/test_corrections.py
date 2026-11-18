import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import store
from app.modules.m1_documents.corrections import parse_correction_notes
from app.modules.m4_tax.adjustment import tax_adjustment_delta, batch_tax_delta
from app.modules.m6_batches.corrections import apply_corrections, trace_adjustments

CLOSED_RUN = "procurematch-rules-1-closed01"
SNAPSHOT = {"000142|0.13": "130.00", "000777|0.09": "90.00"}

NOTE_DOWN = {
    "correction_no": "CN-001", "source_run_id": CLOSED_RUN, "doc_no": "IV-001",
    "sku": "000142", "tax_rate": "13%", "old_tax": "130.00", "new_tax": "117.00",
}


@pytest.fixture()
def closed(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATABASE_PATH", tmp_path / "db.sqlite")
    store.register_closed_batch(CLOSED_RUN, "2026-10-31T23:59:59+08:00", "220.00", "1720.00", SNAPSHOT)
    return CLOSED_RUN


# ---------- M1 单据采信 ----------

def test_valid_correction_note_accepted(closed):
    accepted, bad = parse_correction_notes([NOTE_DOWN], store.get_closed_batch)
    assert len(accepted) == 1 and not bad
    assert accepted[0]["business_key"] == "000142|0.13" and accepted[0]["line_no"] == 2


def test_unknown_closed_batch_quarantined(closed):
    note = {**NOTE_DOWN, "correction_no": "CN-X", "source_run_id": "missing-batch"}
    accepted, bad = parse_correction_notes([note], store.get_closed_batch)
    assert not accepted and bad[0]["reason_code"] == "UNKNOWN_REFERENCE"


def test_old_tax_must_match_closing_snapshot(closed):
    note = {**NOTE_DOWN, "correction_no": "CN-X", "old_tax": "129.99"}
    accepted, bad = parse_correction_notes([note], store.get_closed_batch)
    assert not accepted and bad[0]["reason_code"] == "CLOSED_BATCH_MISMATCH"


def test_missing_field_and_duplicate_quarantined(closed):
    accepted, bad = parse_correction_notes([NOTE_DOWN, {**NOTE_DOWN}, {"correction_no": "CN-9"}], store.get_closed_batch)
    assert len(accepted) == 1
    assert {item["reason_code"] for item in bad} == {"DUPLICATE_KEY", "EMPTY_VALUE"}


# ---------- M4 税额核验 ----------

def test_downward_tax_delta_is_signed():
    result = tax_adjustment_delta("130.00", "117.00")
    assert result["tax_delta_cny"] == "-13.00"


def test_upward_tax_delta_is_positive():
    assert tax_adjustment_delta("90.00", "95.00")["tax_delta_cny"] == "5.00"


def test_delta_uses_half_up_cent():
    assert tax_adjustment_delta("10.000", "10.005")["tax_delta_cny"] == "0.01"


def test_batch_delta_conserves_signed_deltas():
    assert batch_tax_delta(["-13.00", "5.00"]) == "-8.00"


def test_negative_tax_rejected():
    with pytest.raises(ValueError, match="NEGATIVE_TAX"):
        tax_adjustment_delta("-1.00", "2.00")


# ---------- M6 差异批次：入账、审计不变、追溯、幂等 ----------

def test_closed_batch_snapshot_never_rewritten(closed):
    before = store.get_closed_batch(closed)
    apply_corrections([NOTE_DOWN])
    after = store.get_closed_batch(closed)
    assert before == after
    assert after["snapshot"]["000142|0.13"] == "130.00"


def test_correction_posts_delta_to_difference_batch(closed):
    result = apply_corrections([NOTE_DOWN])
    assert len(result["posted"]) == 1 and result["reused"] == []
    entry = result["posted"][0]
    assert entry["tax_delta_cny"] == "-13.00" and entry["reason_code"] == "TAX_ADJUSTMENT"
    assert entry["source_run_id"] == closed and entry["correction_no"] == "CN-001"
    assert result["batch_tax_delta_cny"][closed] == "-13.00"


def test_trace_finds_original_batch(closed):
    apply_corrections([NOTE_DOWN])
    trace = trace_adjustments(closed)
    assert len(trace["adjustments"]) == 1
    source = trace["source_batches"][0]
    assert source["source_run_id"] == closed
    assert source["closed_batch"]["tax_cny"] == "220.00"  # 关账数字仍可查
    assert source["tax_delta_cny"] == "-13.00"


def test_rerun_same_correction_does_not_double_post(closed):
    first = apply_corrections([NOTE_DOWN])
    second = apply_corrections([NOTE_DOWN])
    assert first["created"]
    assert second["created"] is False and second["reused"] == ["CN-001"] and second["posted"] == []
    assert store.adjustment_count() == 1


def test_multiple_corrections_on_same_batch_aggregate(closed):
    second = {
        "correction_no": "CN-002", "source_run_id": closed, "doc_no": "IV-002",
        "sku": "000777", "tax_rate": "0.09", "old_tax": "90.00", "new_tax": "84.00",
    }
    result = apply_corrections([NOTE_DOWN, second])
    assert result["batch_tax_delta_cny"][closed] == "-19.00"
    assert store.adjustment_count() == 2


def test_quarantined_notes_are_evidence_not_posted(closed):
    bad_note = {**NOTE_DOWN, "correction_no": "CN-BAD", "old_tax": "1.00"}
    result = apply_corrections([bad_note])
    assert result["posted"] == [] and result["quarantined"] == 1
    assert result["quarantine_evidence"][0]["reason_code"] == "CLOSED_BATCH_MISMATCH"
    assert store.adjustment_count() == 0


# ---------- HTTP 接口与页面 ----------

def test_api_end_to_end_correction_flow(closed):
    client = TestClient(app)
    response = client.post("/api/batches/corrections", json={"corrections": [NOTE_DOWN]})
    assert response.status_code == 200 and response.json()["posted"][0]["tax_delta_cny"] == "-13.00"

    trace = client.get(f"/api/batches/corrections?source_run_id={closed}").json()
    assert trace["adjustments"][0]["source_run_id"] == closed

    repeat = client.post("/api/batches/corrections", json={"corrections": [NOTE_DOWN]}).json()
    assert repeat["reused"] == ["CN-001"] and len(repeat["posted"]) == 0


def test_m1_accept_endpoint_quarantines_bad_note(closed):
    client = TestClient(app)
    response = client.post("/api/documents/corrections/accept", json={"corrections": [{**NOTE_DOWN, "old_tax": "9.99"}]})
    body = response.json()
    assert body["accepted"] == 0 and body["evidence"][0]["reason_code"] == "CLOSED_BATCH_MISMATCH"


def test_m4_delta_endpoint(closed):
    client = TestClient(app)
    body = client.post("/api/tax/adjustment-delta", json={"old_tax": "130.00", "new_tax": "117.00"}).json()
    assert body["tax_delta_cny"] == "-13.00"


def test_batches_page_shows_trace_panel(closed):
    client = TestClient(app)
    response = client.get("/batches")
    assert response.status_code == 200 and "税额更正追溯" in response.text


def test_closed_batch_registration_endpoint(closed, tmp_path):
    client = TestClient(app)
    payload = {"run_id": "procurematch-rules-1-other", "closed_at": "2026-10-31T23:59:59+08:00",
               "tax_cny": "10.00", "gross_cny": "110.00", "snapshot": {"S|0.13": "10.00"}}
    body = client.post("/api/batches/closed", json=payload).json()
    assert body["snapshot"]["S|0.13"] == "10.00"
