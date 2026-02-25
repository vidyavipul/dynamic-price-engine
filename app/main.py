"""
FastAPI Server — Dynamic Pricing Engine.

Serves the dashboard UI and exposes the pricing API.
Overrides are auto-detected internally — no manual input needed.
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

# ── Backend selection ──
# Use --backend duckdb to switch to cross-dimensional v2 engine
_backend = os.environ.get("PRICING_BACKEND", "v1")

if _backend == "duckdb":
    from app.demand_model_v2 import DemandModelV2
    demand_model = DemandModelV2()
    _engine_label = "v2 (DuckDB cross-dimensional)"
else:
    demand_model = DemandModel()
    _engine_label = "v1 (single-dimension)"

# ── App setup ──
app = FastAPI(
    title="Dynamic Pricing Engine",
    description=f"Rule-based dynamic pricing for self-drive bike rentals — Engine: {_engine_label}",
    version="1.0.0",
)

# Static files
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Initialize engine
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


class VehicleInfo(BaseModel):
    type: str
    name: str
    base_rate: float


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
    parser.add_argument(
        "--backend", choices=["v1", "duckdb"], default="v1",
        help="Pricing backend: v1 (single-dimension) or duckdb (cross-dimensional)"
    )
    parser.add_argument("--port", type=int, default=5000, help="Server port")
    args = parser.parse_args()

    # Set env var so the module-level code picks it up on reload
    os.environ["PRICING_BACKEND"] = args.backend
    print(f"🚀 Starting with backend: {args.backend}")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=args.port,
        reload=True,
    )
