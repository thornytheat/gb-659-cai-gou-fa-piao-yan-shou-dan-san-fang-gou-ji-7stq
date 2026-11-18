from decimal import Decimal, InvalidOperation
from .money import decimal_value, normalize_rate

CORRECTION_REQUIRED = ("correction_no", "source_run_id", "doc_no", "sku", "tax_rate", "old_tax", "new_tax")


def _quarantine(line_no: int, reason_code: str, row: dict) -> dict:
    return {"line_no": line_no, "reason_code": reason_code, "raw": dict(row)}


def _business_key(row: dict) -> str:
    return f"{str(row['sku']).strip()}|{normalize_rate(row['tax_rate'])}"


def parse_correction_note(row: dict, line_no: int, closed_batch_getter) -> tuple[dict | None, dict | None]:
    """Validate one correction note against the immutable closing snapshot.

    The original batch's audited numbers are only read, never rewritten. A note
    whose old tax does not match the closing snapshot is quarantined.
    """
    missing = [key for key in CORRECTION_REQUIRED if not str(row.get(key, "")).strip()]
    if missing:
        return None, _quarantine(line_no, "EMPTY_VALUE", row)

    try:
        old_tax = decimal_value(row["old_tax"])
        new_tax = decimal_value(row["new_tax"])
        rate = normalize_rate(row["tax_rate"])
    except (ValueError, InvalidOperation):
        return None, _quarantine(line_no, "BAD_FORMAT", row)

    if old_tax < 0 or new_tax < 0 or rate < 0:
        return None, _quarantine(line_no, "BAD_FORMAT", row)

    source_run_id = str(row["source_run_id"]).strip()
    closed_batch = closed_batch_getter(source_run_id)
    if closed_batch is None:
        return None, _quarantine(line_no, "UNKNOWN_REFERENCE", row)

    business_key = f"{str(row['sku']).strip()}|{rate}"
    snapshot_tax = closed_batch["snapshot"].get(business_key)
    if snapshot_tax is None or Decimal(str(snapshot_tax)) != old_tax:
        return None, _quarantine(line_no, "CLOSED_BATCH_MISMATCH", row)

    accepted = {
        "line_no": line_no,
        "correction_no": str(row["correction_no"]).strip(),
        "source_run_id": source_run_id,
        "doc_no": str(row["doc_no"]).strip(),
        "business_key": business_key,
        "old_tax_cny": str(old_tax),
        "new_tax_cny": str(new_tax),
        "tax_rate": str(rate),
    }
    return accepted, None


def parse_correction_notes(rows: list[dict], closed_batch_getter) -> tuple[list[dict], list[dict]]:
    accepted, quarantined, seen = [], [], set()
    for line_no, row in enumerate(rows, 2):
        note, bad = parse_correction_note(row, line_no, closed_batch_getter)
        if bad is not None:
            quarantined.append(bad)
            continue
        if note["correction_no"] in seen:
            quarantined.append(_quarantine(line_no, "DUPLICATE_KEY", row))
            continue
        seen.add(note["correction_no"])
        accepted.append(note)
    return accepted, quarantined
