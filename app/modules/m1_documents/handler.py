from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.web import page
from app import store
from .service import demo
from .corrections import parse_correction_notes

router = APIRouter()
ROWS = [{"key":"PO-001","status":"采购","value":"12"},{"key":"GR-001","status":"验收","value":"10"},{"key":"IV-001","status":"发票","value":"9"}]


class CorrectionNotesIn(BaseModel):
    corrections: list[dict]


@router.get("/documents", response_class=HTMLResponse)
def view(request: Request):
    return page(request, "m1.html", "单据采信", "/api/documents/import", ROWS)


@router.post("/api/documents/import")
def execute():
    return demo()


@router.post("/api/documents/corrections/accept")
def accept_corrections(payload: CorrectionNotesIn):
    accepted, quarantined = parse_correction_notes(payload.corrections, store.get_closed_batch)
    return {
        "input": len(payload.corrections),
        "accepted": len(accepted),
        "quarantined": len(quarantined),
        "accepted_notes": accepted,
        "evidence": quarantined,
    }
