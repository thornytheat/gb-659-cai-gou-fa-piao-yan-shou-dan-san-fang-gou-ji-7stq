import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from app.manifest import build_manifest
from app import store
from app.modules.m1_documents.corrections import parse_correction_notes
from app.modules.m4_tax.adjustment import tax_adjustment_delta, batch_tax_delta

SHANGHAI = timezone(timedelta(hours=8))
REASON_CODE = "TAX_ADJUSTMENT"


def canonical_payload(rows: list[dict]) -> bytes:
    return json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _now_cn() -> str:
    return datetime.now(SHANGHAI).isoformat(timespec="seconds")


def apply_corrections(rows: list[dict]) -> dict:
    """Full correction flow: M1 acceptance -> M4 delta -> M6 difference batch.

    Accepted corrections post tax deltas into a new difference batch. The closed
    batch snapshot is never updated, so audited figures stay identical to
    closing. Re-posting the same correction note reuses its posting.
    """
    payload = canonical_payload(rows)
    accepted, quarantined = parse_correction_notes(rows, store.get_closed_batch)
    manifest = build_manifest(payload, len(accepted), len(quarantined))
    run_id = manifest["run_id"]
    manifest["created"] = store.record_run(manifest)

    postings, reused = [], []
    posted_at = _now_cn()
    for note in accepted:
        if store.is_adjustment_posted(note["correction_no"]):
            reused.append(note["correction_no"])
            continue
        delta = tax_adjustment_delta(note["old_tax_cny"], note["new_tax_cny"])
        entry = {
            "correction_no": note["correction_no"],
            "run_id": run_id,
            "source_run_id": note["source_run_id"],
            "business_key": note["business_key"],
            "line_no": note["line_no"],
            "old_tax_cny": delta["old_tax_cny"],
            "new_tax_cny": delta["new_tax_cny"],
            "tax_delta_cny": delta["tax_delta_cny"],
            "reason_code": REASON_CODE,
            "posted_at": posted_at,
        }
        store.post_tax_adjustment(entry)
        postings.append(entry)

    deltas_by_source: dict[str, list[str]] = {}
    for entry in store.list_adjustments():
        deltas_by_source.setdefault(entry["source_run_id"], []).append(entry["tax_delta_cny"])
    batch_deltas = {
        source_run_id: batch_tax_delta(deltas)
        for source_run_id, deltas in sorted(deltas_by_source.items())
    }

    return {
        **manifest,
        "posted": postings,
        "reused": reused,
        "quarantine_evidence": quarantined,
        "batch_tax_delta_cny": batch_deltas,
    }


def trace_adjustments(source_run_id: str | None = None) -> dict:
    rows = store.list_adjustments(source_run_id)
    sources: dict[str, dict] = {}
    total = Decimal("0")
    for row in rows:
        total += Decimal(row["tax_delta_cny"])
        source = sources.setdefault(
            row["source_run_id"],
            {"source_run_id": row["source_run_id"], "closed_batch": None, "tax_delta_cny": "0.00", "adjustments": []},
        )
        source["adjustments"].append(row)
    for source in sources.values():
        source["closed_batch"] = store.get_closed_batch(source["source_run_id"])
        source["tax_delta_cny"] = batch_tax_delta([row["tax_delta_cny"] for row in source["adjustments"]])
    return {
        "adjustments": rows,
        "source_batches": sorted(sources.values(), key=lambda item: item["source_run_id"]),
        "total_tax_delta_cny": str(total),
    }
