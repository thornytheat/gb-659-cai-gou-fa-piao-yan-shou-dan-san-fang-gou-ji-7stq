from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from app.web import page
from app import store
from .service import demo
from .exporter import differences_csv
from .corrections import apply_corrections, trace_adjustments

router = APIRouter()
ROWS = [{"key":"RUN-659-A","status":"守恒","value":"36"},{"key":"RUN-659-B","status":"复用","value":"36"},{"key":"RUN-659-C","status":"差异","value":"2"}]


class ClosedBatchIn(BaseModel):
    run_id: str
    closed_at: str
    tax_cny: str
    gross_cny: str
    snapshot: dict


class CorrectionIn(BaseModel):
    corrections: list[dict]


@router.get("/batches", response_class=HTMLResponse)
def view(request: Request):
    return page(request, "m6.html", "差异批次", "/api/reconcile", ROWS)


@router.post("/api/reconcile")
def execute():
    return demo()


@router.get("/api/export/differences.csv")
def export_differences():
    body = differences_csv([{"business_key": "SKU-C|0.13", "line_no": 9, "reason_code": "UNINVOICED", "amount_cny": "226.00"}])
    return PlainTextResponse(body, media_type="text/csv", headers={"content-disposition": "attachment; filename=differences.csv"})


@router.post("/api/batches/closed")
def register_closed_batch(payload: ClosedBatchIn):
    """Freeze a batch's closing numbers; later corrections never overwrite them."""
    store.register_closed_batch(
        payload.run_id, payload.closed_at, payload.tax_cny, payload.gross_cny, payload.snapshot
    )
    return store.get_closed_batch(payload.run_id)


@router.post("/api/batches/corrections")
def post_corrections(payload: CorrectionIn):
    return apply_corrections(payload.corrections)


@router.get("/api/batches/corrections")
def get_corrections(source_run_id: str | None = None):
    return trace_adjustments(source_run_id)
