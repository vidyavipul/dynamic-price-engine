"""
FastAPI Server — Dynamic Pricing Engine.

Serves the dashboard UI and exposes the pricing API.
"""

import os
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import VehicleType, VEHICLE_BASE_RATES, VEHICLE_DISPLAY_NAMES
from app.demand_model import DemandModel
from app.price_engine import PriceEngine
from app.overrides import OverrideType, OVERRIDE_DESCRIPTIONS

# ── App setup ──
app = FastAPI(
    title="Dynamic Pricing Engine",
    description="Rule-based dynamic pricing for self-drive bike rentals",
    version="1.0.0",
)

# Static files
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Initialize engine
demand_model = DemandModel()
price_engine = PriceEngine(demand_model)


# ── Request/Response models ──

class PriceRequest(BaseModel):
    rental_datetime: str = Field(
        ...,
        description="Rental start datetime in ISO format (YYYY-MM-DDTHH:MM:SS)",
        examples=["2025-10-18T09:00:00"],
    )
    vehicle_type: str = Field(
        ...,
        description="Vehicle category",
        examples=["standard_bike"],
    )
    duration_hours: int = Field(
        ..., ge=1,
        description="Rental duration in hours (minimum 1)",
        examples=[8],
    )
    overrides: Optional[List[str]] = Field(
        default=[],
        description="Active contextual overrides",
        examples=[["rain", "festival"]],
    )


class VehicleInfo(BaseModel):
    type: str
    name: str
    base_rate: float


class OverrideInfo(BaseModel):
    type: str
    description: str


# ── Routes ──

@app.get("/")
async def serve_dashboard():
    """Serve the main dashboard HTML."""
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/api/vehicles")
async def get_vehicles():
    """Return list of available vehicle types and their base rates."""
    vehicles = [
        VehicleInfo(
            type=v.value,
            name=VEHICLE_DISPLAY_NAMES[v],
            base_rate=VEHICLE_BASE_RATES[v],
        )
        for v in VehicleType
    ]
    return {"vehicles": [v.model_dump() for v in vehicles]}


@app.get("/api/overrides")
async def get_overrides():
    """Return list of available overrides."""
    overrides = [
        OverrideInfo(type=o.value, description=OVERRIDE_DESCRIPTIONS[o])
        for o in OverrideType
    ]
    return {"overrides": [o.model_dump() for o in overrides]}


@app.post("/api/price")
async def calculate_price(request: PriceRequest):
    """
    Calculate dynamic price for a bike rental.

    Takes rental datetime, vehicle type, duration, and optional overrides.
    Returns the full price breakdown with demand analysis and explanation.
    """
    # Parse datetime
    try:
        rental_dt = datetime.fromisoformat(request.rental_datetime)
    except (ValueError, TypeError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid datetime format: {request.rental_datetime}. "
                   f"Use ISO format: YYYY-MM-DDTHH:MM:SS"
        )

    # Calculate price
    try:
        result = price_engine.calculate_price(
            rental_datetime=rental_dt,
            vehicle_type=request.vehicle_type,
            duration_hours=request.duration_hours,
            active_overrides=request.overrides,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Convert dataclass to dict
    from dataclasses import asdict
    return asdict(result)


# ── Main ──

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=5000,
        reload=True,
    )
