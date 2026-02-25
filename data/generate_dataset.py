"""
Synthetic Dataset Generator for Bike Rental Bookings.

Generates ~2 years of realistic booking data with built-in demand patterns:
- Weekend spikes (2.5× vs weekday)
- Holiday surges (3×)
- Long weekend effects (3.5×)
- Bridge day boosts (2× when connecting holiday to weekend)
- Morning pickup peaks
- Monsoon dips
- Seasonal variations
"""

import random
import os
from datetime import datetime, timedelta, date
from typing import List, Dict
import csv

# Add parent to path so we can import config
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.config import INDIAN_HOLIDAYS, VehicleType, VEHICLE_BASE_RATES

# ──────────────────────────────────────────────
# Constants for data generation
# ──────────────────────────────────────────────

START_DATE = date(2024, 1, 1)
END_DATE = date(2025, 12, 31)

# Base daily bookings (average normal weekday)
BASE_DAILY_BOOKINGS = 250

# Pickup locations
LOCATIONS = [
    "Koramangala", "Indiranagar", "HSR Layout", "Whitefield",
    "Electronic City", "MG Road", "Jayanagar", "Marathahalli",
    "BTM Layout", "Banashankari"
]

# Weather conditions and their probabilities by season
WEATHER_BY_SEASON = {
    "summer":  {"clear": 0.70, "hot": 0.25, "rain": 0.05},
    "monsoon": {"clear": 0.25, "rain": 0.55, "heavy_rain": 0.20},
    "winter":  {"clear": 0.80, "fog": 0.15, "rain": 0.05},
    "festive": {"clear": 0.85, "hot": 0.10, "rain": 0.05},
}

# ──────────────────────────────────────────────
# Season classification
# ──────────────────────────────────────────────

def get_season(d: date) -> str:
    """Classify a date into a season."""
    month = d.month
    if month in (3, 4, 5):
        return "summer"
    elif month in (6, 7, 8, 9):
        return "monsoon"
    elif month in (10, 11):
        return "festive"
    else:  # 12, 1, 2
        return "winter"


# ──────────────────────────────────────────────
# Day type classification (core demand logic)
# ──────────────────────────────────────────────

def classify_day(d: date) -> str:
    """
    Classify a date into a day type for demand estimation.
    Returns one of: long_weekend, holiday, bridge_strong, holiday_eve,
                    saturday, sunday, friday, bridge_weak, exam_weekday, regular_weekday
    """
    weekday = d.weekday()  # 0=Mon, 6=Sun
    is_holiday = d in INDIAN_HOLIDAYS
    month = d.month

    # Check if this date is part of a long weekend
    if _is_long_weekend_day(d):
        return "long_weekend"

    if is_holiday:
        return "holiday"

    # Strong bridge: single weekday connecting holiday to weekend
    if _is_strong_bridge(d):
        return "bridge_strong"

    # Holiday eve (day before a holiday)
    tomorrow = d + timedelta(days=1)
    if tomorrow in INDIAN_HOLIDAYS:
        return "holiday_eve"

    if weekday == 5:  # Saturday
        return "saturday"
    if weekday == 6:  # Sunday
        return "sunday"
    if weekday == 4:  # Friday
        return "friday"

    # Weak bridge: needs 2 leave days to connect
    if _is_weak_bridge(d):
        return "bridge_weak"

    # Exam season: March-April weekdays
    if month in (3, 4) and weekday < 5:
        return "exam_weekday"

    return "regular_weekday"


def _is_long_weekend_day(d: date) -> bool:
    """
    Check if a date is part of a long weekend (3+ consecutive off days).
    Examples:
    - Holiday on Monday → Sat, Sun, Mon = long weekend
    - Holiday on Friday → Fri, Sat, Sun = long weekend
    - Holiday on Tuesday → Mon (bridge), Tue, and Sat, Sun before = 4-day stretch
    """
    # Check 5-day window around this date for holiday+weekend combos
    for offset in range(-3, 4):
        check = d + timedelta(days=offset)
        if check in INDIAN_HOLIDAYS:
            holiday_weekday = check.weekday()

            # Holiday on Monday → Sat(d-2), Sun(d-1), Mon(d) = long weekend
            if holiday_weekday == 0:  # Monday
                long_wknd = {check - timedelta(2), check - timedelta(1), check}
                if d in long_wknd:
                    return True

            # Holiday on Friday → Fri, Sat(d+1), Sun(d+2)
            if holiday_weekday == 4:  # Friday
                long_wknd = {check, check + timedelta(1), check + timedelta(2)}
                if d in long_wknd:
                    return True

            # Holiday on Tuesday → Sat, Sun, Mon(bridge), Tue = 4-day
            if holiday_weekday == 1:  # Tuesday
                long_wknd = {
                    check - timedelta(3),  # Sat
                    check - timedelta(2),  # Sun
                    check - timedelta(1),  # Mon (bridge)
                    check                  # Tue (holiday)
                }
                if d in long_wknd:
                    return True

            # Holiday on Thursday → Thu, Fri(bridge), Sat, Sun = 4-day
            if holiday_weekday == 3:  # Thursday
                long_wknd = {
                    check,                 # Thu (holiday)
                    check + timedelta(1),  # Fri (bridge)
                    check + timedelta(2),  # Sat
                    check + timedelta(3),  # Sun
                }
                if d in long_wknd:
                    return True

    return False


def _is_strong_bridge(d: date) -> bool:
    """
    A strong bridge day: single leave day that creates a 4-day weekend.
    - Tuesday holiday → Monday is strong bridge (Sat-Sun-Mon-Tue)
    - Thursday holiday → Friday is strong bridge (Thu-Fri-Sat-Sun)
    """
    weekday = d.weekday()

    # Monday: check if Tuesday is a holiday
    if weekday == 0:
        tuesday = d + timedelta(days=1)
        if tuesday in INDIAN_HOLIDAYS:
            return True

    # Friday: check if Thursday is a holiday
    if weekday == 4:
        thursday = d - timedelta(days=1)
        if thursday in INDIAN_HOLIDAYS:
            return True

    return False


def _is_weak_bridge(d: date) -> bool:
    """
    A weak bridge: needs 2 days of leave to connect to weekend.
    - Wednesday holiday → Monday or Tuesday could be weak bridges
    """
    weekday = d.weekday()

    # Check if any day within 2 positions is a holiday on Wednesday
    for offset in range(-2, 3):
        check = d + timedelta(days=offset)
        if check in INDIAN_HOLIDAYS and check.weekday() == 2 and check != d:
            return True

    return False


# ──────────────────────────────────────────────
# Booking multiplier based on day type
# ──────────────────────────────────────────────

DAY_TYPE_BOOKING_MULTIPLIER = {
    "long_weekend":    3.5,
    "holiday":         3.0,
    "bridge_strong":   2.5,
    "holiday_eve":     2.0,
    "saturday":        2.5,
    "sunday":          2.0,
    "friday":          1.5,
    "bridge_weak":     1.3,
    "regular_weekday": 1.0,
    "exam_weekday":    0.6,
}

# Season multiplier for booking volume
SEASON_BOOKING_MULTIPLIER = {
    "summer":  1.5,
    "monsoon": 0.5,
    "festive": 1.6,
    "winter":  0.9,
}

# ──────────────────────────────────────────────
# Hourly distribution of pickups
# ──────────────────────────────────────────────

HOURLY_PICKUP_WEIGHTS = {
    0: 0.01, 1: 0.005, 2: 0.005, 3: 0.005, 4: 0.01, 5: 0.02,
    6: 0.04, 7: 0.10, 8: 0.14, 9: 0.12, 10: 0.08, 11: 0.06,
    12: 0.05, 13: 0.04, 14: 0.04, 15: 0.05, 16: 0.06, 17: 0.05,
    18: 0.04, 19: 0.03, 20: 0.02, 21: 0.015, 22: 0.01, 23: 0.005,
}

# Normalize so they sum to 1
_total = sum(HOURLY_PICKUP_WEIGHTS.values())
HOURLY_PICKUP_PROBS = {h: w / _total for h, w in HOURLY_PICKUP_WEIGHTS.items()}

# Duration distribution (hours)
DURATION_CHOICES = [1, 2, 3, 4, 6, 8, 12, 24, 48, 72]
DURATION_WEIGHTS = [0.05, 0.08, 0.08, 0.12, 0.10, 0.22, 0.12, 0.15, 0.05, 0.03]

# Vehicle type distribution
VEHICLE_CHOICES = list(VehicleType)
VEHICLE_WEIGHTS = [0.40, 0.35, 0.18, 0.07]


# ──────────────────────────────────────────────
# Generate bookings for one day
# ──────────────────────────────────────────────

def generate_day_bookings(d: date, booking_counter: int) -> List[Dict]:
    """Generate all bookings for a single day."""
    season = get_season(d)
    day_type = classify_day(d)
    weather = random.choices(
        list(WEATHER_BY_SEASON[season].keys()),
        weights=list(WEATHER_BY_SEASON[season].values()),
        k=1
    )[0]

    # Calculate number of bookings for this day
    day_mult = DAY_TYPE_BOOKING_MULTIPLIER[day_type]
    season_mult = SEASON_BOOKING_MULTIPLIER[season]

    # Weather impact on booking count
    weather_mult = 1.0
    if weather == "rain":
        weather_mult = 0.7
    elif weather == "heavy_rain":
        weather_mult = 0.4
    elif weather == "hot":
        weather_mult = 0.9

    expected_bookings = BASE_DAILY_BOOKINGS * day_mult * season_mult * weather_mult
    # Add some randomness (±20%)
    actual_bookings = max(1, int(expected_bookings * random.uniform(0.80, 1.20)))

    bookings = []
    hours = list(HOURLY_PICKUP_PROBS.keys())
    hour_weights = list(HOURLY_PICKUP_PROBS.values())

    for i in range(actual_bookings):
        booking_counter += 1

        # Pick a random pickup hour based on distribution
        pickup_hour = random.choices(hours, weights=hour_weights, k=1)[0]
        pickup_minute = random.randint(0, 59)

        rental_start = datetime(d.year, d.month, d.day, pickup_hour, pickup_minute)

        # Some bookings are made in advance (1-30 days before)
        advance_days = random.choices(
            [0, 1, 2, 3, 7, 14, 30],
            weights=[0.35, 0.20, 0.15, 0.10, 0.10, 0.05, 0.05],
            k=1
        )[0]
        booking_datetime = rental_start - timedelta(days=advance_days, hours=random.randint(0, 12))

        # Duration
        duration = random.choices(DURATION_CHOICES, weights=DURATION_WEIGHTS, k=1)[0]

        # Vehicle type
        vehicle = random.choices(VEHICLE_CHOICES, weights=VEHICLE_WEIGHTS, k=1)[0]

        bookings.append({
            "booking_id": f"BK-{booking_counter:06d}",
            "booking_datetime": booking_datetime.strftime("%Y-%m-%dT%H:%M:%S"),
            "rental_start": rental_start.strftime("%Y-%m-%dT%H:%M:%S"),
            "duration_hours": duration,
            "vehicle_type": vehicle.value,
            "pickup_location": random.choice(LOCATIONS),
            "base_price_per_hr": VEHICLE_BASE_RATES[vehicle],
            "day_type": day_type,
            "is_holiday": d in INDIAN_HOLIDAYS,
            "is_weekend": d.weekday() >= 5,
            "season": season,
            "weather": weather,
        })

    return bookings, booking_counter


# ──────────────────────────────────────────────
# Main generator
# ──────────────────────────────────────────────

def generate_dataset(output_path: str = None) -> str:
    """
    Generate the full synthetic dataset and save as CSV.
    Returns the output file path.
    """
    if output_path is None:
        output_path = os.path.join(os.path.dirname(__file__), "bookings.csv")

    random.seed(42)  # Reproducible

    all_bookings = []
    booking_counter = 0
    current = START_DATE

    print(f"Generating bookings from {START_DATE} to {END_DATE}...")

    while current <= END_DATE:
        day_bookings, booking_counter = generate_day_bookings(current, booking_counter)
        all_bookings.extend(day_bookings)
        current += timedelta(days=1)

    # Write to CSV
    if all_bookings:
        fieldnames = list(all_bookings[0].keys())
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_bookings)

    print(f"✅ Generated {len(all_bookings):,} bookings → {output_path}")
    print(f"   Date range: {START_DATE} to {END_DATE}")
    print(f"   Total days: {(END_DATE - START_DATE).days + 1}")
    print(f"   Avg bookings/day: {len(all_bookings) // ((END_DATE - START_DATE).days + 1)}")

    return output_path


if __name__ == "__main__":
    generate_dataset()
