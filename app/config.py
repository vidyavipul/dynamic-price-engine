"""
Configuration constants for the Dynamic Pricing Engine.
All tunable parameters in one place.
"""
from enum import Enum
from typing import Dict, List, Tuple
from datetime import date

# ──────────────────────────────────────────────
# Vehicle Types & Base Rates (₹ per hour)
# ──────────────────────────────────────────────

class VehicleType(str, Enum):
    SCOOTER = "scooter"
    STANDARD_BIKE = "standard_bike"
    PREMIUM_BIKE = "premium_bike"
    SUPER_PREMIUM = "super_premium"


VEHICLE_BASE_RATES: Dict[VehicleType, float] = {
    VehicleType.SCOOTER: 60.0,         # Activa, Jupiter
    VehicleType.STANDARD_BIKE: 80.0,   # Pulsar 150, FZ
    VehicleType.PREMIUM_BIKE: 150.0,   # RE Classic 350, Dominar
    VehicleType.SUPER_PREMIUM: 250.0,  # RE Himalayan, KTM 390
}

VEHICLE_DISPLAY_NAMES: Dict[VehicleType, str] = {
    VehicleType.SCOOTER: "Scooter (Activa, Jupiter)",
    VehicleType.STANDARD_BIKE: "Standard Bike (Pulsar, FZ)",
    VehicleType.PREMIUM_BIKE: "Premium Bike (RE Classic, Dominar)",
    VehicleType.SUPER_PREMIUM: "Super Premium (Himalayan, KTM 390)",
}

# ──────────────────────────────────────────────
# Absolute Price Guards (₹ per hour)
# Floor: prevents pricing below operational cost
# Ceiling: prevents customer overcharging
# ──────────────────────────────────────────────

PRICE_FLOOR_RATES: Dict[VehicleType, float] = {
    VehicleType.SCOOTER: 40.0,         # ~65% of ₹60 base
    VehicleType.STANDARD_BIKE: 50.0,   # ~63% of ₹80 base
    VehicleType.PREMIUM_BIKE: 100.0,   # ~67% of ₹150 base
    VehicleType.SUPER_PREMIUM: 160.0,  # ~64% of ₹250 base
}

PRICE_CEILING_RATES: Dict[VehicleType, float] = {
    VehicleType.SCOOTER: 150.0,        # 2.5× of ₹60 base
    VehicleType.STANDARD_BIKE: 200.0,  # 2.5× of ₹80 base
    VehicleType.PREMIUM_BIKE: 375.0,   # 2.5× of ₹150 base
    VehicleType.SUPER_PREMIUM: 625.0,  # 2.5× of ₹250 base
}

# ──────────────────────────────────────────────
# Demand Multiplier Bounds
# ──────────────────────────────────────────────

MIN_MULTIPLIER = 0.70   # Floor: 30% discount (dead demand)
MAX_MULTIPLIER = 2.00   # Ceiling: 2× surge cap
BASELINE_DEMAND = 0.50  # Midpoint demand score where multiplier ≈ 1.35× (includes margin)

# ──────────────────────────────────────────────
# Duration Discounts (applied AFTER surge pricing)
# ──────────────────────────────────────────────

DURATION_DISCOUNT_TIERS: List[Tuple[int, float]] = [
    (24, 0.70),  # 24+ hours → 30% off
    (8, 0.80),   # 8+ hours  → 20% off
    (4, 0.90),   # 4+ hours  → 10% off
]
# Order: longest first (checked top→down, first match wins)

# ──────────────────────────────────────────────
# Override Stacking Cap
# ──────────────────────────────────────────────

MAX_OVERRIDE_FACTOR = 2.0  # Combined override factor capped here

# When multiple overrides are detected (e.g., Diwali + long weekend + holiday eve),
# their factors are multiplied together: 1.40 × 1.50 × 1.15 = 2.42.
# The cap limits the combined result to 2.0× so overrides can't create an absurdly high surge.

# ──────────────────────────────────────────────
# Demand Signal Weights (must sum to 1.0)
# ──────────────────────────────────────────────

WEIGHT_DAY_TYPE = 0.45
WEIGHT_SEASON = 0.30
WEIGHT_TIME_SLOT = 0.25

# ──────────────────────────────────────────────
# Indian Public Holidays (2024–2026)
# ──────────────────────────────────────────────

INDIAN_HOLIDAYS: Dict[date, str] = {
    # 2024
    date(2024, 1, 26): "Republic Day",
    date(2024, 3, 25): "Holi",
    date(2024, 3, 29): "Good Friday",
    date(2024, 4, 11): "Eid ul-Fitr",
    date(2024, 4, 14): "Ambedkar Jayanti",
    date(2024, 4, 17): "Ram Navami",
    date(2024, 4, 21): "Mahavir Jayanti",
    date(2024, 5, 23): "Buddha Purnima",
    date(2024, 6, 17): "Eid ul-Adha",
    date(2024, 7, 17): "Muharram",
    date(2024, 8, 15): "Independence Day",
    date(2024, 8, 19): "Raksha Bandhan",
    date(2024, 8, 26): "Janmashtami",
    date(2024, 9, 7): "Milad un-Nabi",
    date(2024, 10, 2): "Gandhi Jayanti",
    date(2024, 10, 12): "Dussehra",
    date(2024, 10, 31): "Halloween / Diwali Eve",
    date(2024, 11, 1): "Diwali",
    date(2024, 11, 2): "Diwali (Day 2)",
    date(2024, 11, 15): "Guru Nanak Jayanti",
    date(2024, 12, 25): "Christmas",

    # 2025
    date(2025, 1, 1): "New Year",
    date(2025, 1, 14): "Pongal / Makar Sankranti",
    date(2025, 1, 26): "Republic Day",
    date(2025, 3, 14): "Holi",
    date(2025, 3, 30): "Eid ul-Fitr",
    date(2025, 4, 6): "Ram Navami",
    date(2025, 4, 10): "Mahavir Jayanti",
    date(2025, 4, 14): "Ambedkar Jayanti",
    date(2025, 4, 18): "Good Friday",
    date(2025, 5, 12): "Buddha Purnima",
    date(2025, 6, 7): "Eid ul-Adha",
    date(2025, 7, 6): "Muharram",
    date(2025, 8, 9): "Raksha Bandhan",
    date(2025, 8, 15): "Independence Day / Janmashtami",
    date(2025, 8, 27): "Milad un-Nabi",
    date(2025, 10, 2): "Gandhi Jayanti",
    date(2025, 10, 2): "Dussehra",
    date(2025, 10, 20): "Diwali",
    date(2025, 10, 21): "Diwali (Day 2)",
    date(2025, 11, 5): "Guru Nanak Jayanti",
    date(2025, 12, 25): "Christmas",

    # 2026
    date(2026, 1, 1): "New Year",
    date(2026, 1, 14): "Pongal / Makar Sankranti",
    date(2026, 1, 26): "Republic Day",
    date(2026, 3, 4): "Holi",
    date(2026, 3, 20): "Eid ul-Fitr",
    date(2026, 3, 26): "Ram Navami",
    date(2026, 3, 31): "Mahavir Jayanti",
    date(2026, 4, 3): "Good Friday",
    date(2026, 4, 14): "Ambedkar Jayanti",
    date(2026, 5, 1): "Buddha Purnima",
    date(2026, 5, 27): "Eid ul-Adha",
    date(2026, 6, 26): "Muharram",
    date(2026, 7, 29): "Raksha Bandhan",
    date(2026, 8, 14): "Janmashtami",
    date(2026, 8, 15): "Independence Day",
    date(2026, 8, 17): "Milad un-Nabi",
    date(2026, 9, 21): "Dussehra",
    date(2026, 10, 2): "Gandhi Jayanti",
    date(2026, 10, 9): "Diwali",
    date(2026, 10, 10): "Diwali (Day 2)",
    date(2026, 10, 25): "Guru Nanak Jayanti",
    date(2026, 12, 25): "Christmas",
}

# Advance Booking Confidence Thresholds

LOW_CONFIDENCE_DAYS = 90  # Bookings > 90 days out get low-confidence flag
