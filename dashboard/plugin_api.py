"""HTTP namespace /api/plugins/show-your-work/ (Phase 0 spike)."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/ping")
async def ping():
    return {"ok": True, "plugin": "show-your-work", "phase": 0}
