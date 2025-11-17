from __future__ import annotations

from fastapi import APIRouter, Query, Depends

from services.auth_service import protect

from teach_mode import is_teach_mode_on, set_teach_mode


router = APIRouter()


@router.get("/teach_mode")
def get_teach_mode(current_user: dict = Depends(protect)):
    return {"teach_mode": is_teach_mode_on()}


@router.post("/teach_mode")
def update_teach_mode(
    enabled: bool = Query(..., description="Enable or disable Teach Mode"),
    current_user: dict = Depends(protect),
):
    state = set_teach_mode(enabled)
    return {"teach_mode": state}
