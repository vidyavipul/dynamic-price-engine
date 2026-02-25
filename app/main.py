"""
FastAPI Server — Dynamic Pricing Engine.

Serves the dashboard UI and exposes the pricing API.
Overrides are auto-detected internally — no manual input needed.
DuckDB analytics available via /analytics page.
"""

import json
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

# ── App setup ──
app = FastAPI(
    title="Dynamic Pricing Engine",
    description="Rule-based dynamic pricing for self-drive bike rentals",
    version="1.0.0",
)

# Static files
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Initialize engine (always v1)
demand_model = DemandModel()
price_engine = PriceEngine(demand_model)

# Load DuckDB analytics profiles (for reporting only)
_duckdb_profiles_path = os.path.join(
    os.path.dirname(__file__), "..", "data", "demand_profiles_duckdb.json"
)
_duckdb_profiles = {}
if os.path.exists(_duckdb_profiles_path):
    with open(_duckdb_profiles_path, "r") as f:
        _duckdb_profiles = json.load(f)


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


class VehicleInfo(BaseModel):
    type: str
    name: str
    base_rate: float


# ── Routes ──

@app.get("/")
async def serve_dashboard():
    """Serve the main dashboard HTML."""
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/analytics")
async def serve_analytics():
    """Serve the DuckDB analytics reporting page."""
    return FileResponse(os.path.join(static_dir, "analytics.html"))


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


@app.get("/api/analytics")
async def get_analytics():
    """Return DuckDB analytics profiles for reporting."""
    if not _duckdb_profiles:
        raise HTTPException(
            status_code=404,
            detail="DuckDB analytics not available. Run: python3 data/duckdb_analyzer.py"
        )
    return _duckdb_profiles


@app.post("/api/price")
async def calculate_price(request: PriceRequest):
    """
    Calculate dynamic price for a bike rental.

    Overrides are auto-detected from the rental datetime using:
    - Holiday calendar (festivals, public holidays)
    - Day classification (long weekends, holiday eves)
    - Weather probabilities from historical booking data
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

    # Calculate price (overrides auto-detected internally)
    try:
        result = price_engine.calculate_price(
            rental_datetime=rental_dt,
            vehicle_type=request.vehicle_type,
            duration_hours=request.duration_hours,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Convert dataclass to dict
    from dataclasses import asdict
    return asdict(result)


# ── Main ──

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Dynamic Pricing Engine")
    parser.add_argument("--port", type=int, default=5000, help="Server port")
    args = parser.parse_args()

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=args.port,
        reload=True,
    )
