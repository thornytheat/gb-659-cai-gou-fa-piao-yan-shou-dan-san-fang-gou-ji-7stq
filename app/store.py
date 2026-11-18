import json
import sqlite3
from app.config import DATABASE_PATH

def connect():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DATABASE_PATH)

def init_db():
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, input_sha256 TEXT NOT NULL, accepted INTEGER NOT NULL, quarantined INTEGER NOT NULL)")
        db.execute(
            "CREATE TABLE IF NOT EXISTS closed_batches ("
            "run_id TEXT PRIMARY KEY, closed_at TEXT NOT NULL, "
            "tax_cny TEXT NOT NULL, gross_cny TEXT NOT NULL, snapshot TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS tax_adjustments ("
            "correction_no TEXT PRIMARY KEY, run_id TEXT NOT NULL, source_run_id TEXT NOT NULL, "
            "business_key TEXT NOT NULL, line_no INTEGER NOT NULL, "
            "old_tax_cny TEXT NOT NULL, new_tax_cny TEXT NOT NULL, tax_delta_cny TEXT NOT NULL, "
            "reason_code TEXT NOT NULL, posted_at TEXT NOT NULL)"
        )

def record_run(manifest: dict) -> bool:
    init_db()
    with connect() as db:
        before = db.total_changes
        db.execute("INSERT OR IGNORE INTO runs VALUES (?, ?, ?, ?)", (manifest["run_id"], manifest["input_sha256"], manifest["accepted"], manifest["quarantined"]))
        return db.total_changes > before

def run_count() -> int:
    init_db()
    with connect() as db:
        return db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

def register_closed_batch(run_id: str, closed_at: str, tax_cny: str, gross_cny: str, snapshot: dict) -> None:
    """Freeze the closing numbers of a batch. Audit figures are never rewritten later."""
    init_db()
    with connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO closed_batches VALUES (?, ?, ?, ?, ?)",
            (run_id, closed_at, str(tax_cny), str(gross_cny), json.dumps(snapshot, ensure_ascii=False, sort_keys=True)),
        )

def get_closed_batch(run_id: str) -> dict | None:
    init_db()
    with connect() as db:
        row = db.execute("SELECT run_id, closed_at, tax_cny, gross_cny, snapshot FROM closed_batches WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    return {"run_id": row[0], "closed_at": row[1], "tax_cny": row[2], "gross_cny": row[3], "snapshot": json.loads(row[4])}

def post_tax_adjustment(entry: dict) -> bool:
    """Insert one tax adjustment. Returns False when the correction note was already posted."""
    init_db()
    with connect() as db:
        before = db.total_changes
        db.execute(
            "INSERT OR IGNORE INTO tax_adjustments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry["correction_no"], entry["run_id"], entry["source_run_id"], entry["business_key"],
                entry["line_no"], entry["old_tax_cny"], entry["new_tax_cny"], entry["tax_delta_cny"],
                entry["reason_code"], entry["posted_at"],
            ),
        )
        return db.total_changes > before

def is_adjustment_posted(correction_no: str) -> bool:
    init_db()
    with connect() as db:
        return db.execute("SELECT 1 FROM tax_adjustments WHERE correction_no = ?", (correction_no,)).fetchone() is not None

def list_adjustments(source_run_id: str | None = None) -> list[dict]:
    init_db()
    sql = "SELECT correction_no, run_id, source_run_id, business_key, line_no, old_tax_cny, new_tax_cny, tax_delta_cny, reason_code, posted_at FROM tax_adjustments"
    params: tuple = ()
    if source_run_id is not None:
        sql += " WHERE source_run_id = ?"
        params = (source_run_id,)
    sql += " ORDER BY posted_at, correction_no"
    with connect() as db:
        rows = db.execute(sql, params).fetchall()
    fields = ("correction_no", "run_id", "source_run_id", "business_key", "line_no", "old_tax_cny", "new_tax_cny", "tax_delta_cny", "reason_code", "posted_at")
    return [dict(zip(fields, row)) for row in rows]

def adjustment_count() -> int:
    init_db()
    with connect() as db:
        return db.execute("SELECT COUNT(*) FROM tax_adjustments").fetchone()[0]
