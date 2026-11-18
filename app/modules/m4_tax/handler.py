from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.web import page
from .service import demo
from .adjustment import tax_adjustment_delta, batch_tax_delta

router = APIRouter()
ROWS = [{"key":"IV-001","status":"相等","value":"1130.00"},{"key":"IV-002","status":"尾差","value":"0.01"},{"key":"IV-003","status":"隔离","value":"13%"}]


class TaxDeltaIn(BaseModel):
    old_tax: str
    new_tax: str


class BatchDeltaIn(BaseModel):
    deltas: list[str]


@router.get("/tax", response_class=HTMLResponse)
def view(request: Request):
    return page(request, "m4.html", "税额核验", "/api/tax/check", ROWS)


@router.post("/api/tax/check")
def execute():
    return demo()


@router.post("/api/tax/adjustment-delta")
def adjustment_delta(payload: TaxDeltaIn):
    return tax_adjustment_delta(payload.old_tax, payload.new_tax)


@router.post("/api/tax/batch-delta")
def batch_delta(payload: BatchDeltaIn):
    return {"tax_delta_cny": batch_tax_delta(payload.deltas)}
