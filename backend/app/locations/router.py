from __future__ import annotations

from fastapi import APIRouter

from backend.app.locations.schemas import (
    LocationResolveRequest,
    LocationResolveResponse,
)
from backend.app.locations.service import resolve_administrative_location


router = APIRouter(prefix="/locations", tags=["locations"])


@router.post("/resolve", response_model=LocationResolveResponse)
def resolve_location(payload: LocationResolveRequest) -> LocationResolveResponse:
    return resolve_administrative_location(payload)
