"""
Auto-Detected Contextual Overrides for pricing.

Instead of manual toggles, overrides are automatically predicted
from the rental datetime using:
- Holiday calendar → festival/holiday override
- Day classification → long weekend override
- Weather probabilities from historical data → rain/heatwave override
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional

from app.config import INDIAN_HOLIDAYS, MAX_OVERRIDE_FACTOR


@dataclass
class DetectedOverride:
    """A single auto-detected override."""
    name: str
    factor: float
    reason: str
    confidence: str   # "high", "medium", "low"
    effect: str       # "surge" or "discount"


# Override factor definitions
OVERRIDE_FACTORS = {
    "long_weekend": 1.50,
    "festival": 1.40,
    "holiday": 1.30,
    "holiday_eve": 1.15,
    "rain_likely": 0.85,
    "heavy_rain_likely": 0.70,
    "heatwave_likely": 0.90,
}


class OverrideDetector:
    """
    Automatically detects applicable overrides for a given rental datetime.

    Uses:
    - Indian holiday calendar for festival/holiday detection
    - Day classification for long weekend detection
    - Weather probabilities (from analyzed booking data) for weather prediction
    """

    def __init__(self, profiles_path: Optional[str] = None):
        """Load weather probabilities from demand profiles."""
        if profiles_path is None:
            profiles_path = os.path.join(
                os.path.dirname(__file__), "..", "data", "demand_profiles.json"
            )

        self.weather_by_month = {}
        if os.path.exists(profiles_path):
            with open(profiles_path, "r") as f:
                profiles = json.load(f)
                self.weather_by_month = profiles.get("weather_by_month", {})

    def detect_overrides(self, rental_datetime: datetime, day_type: str) -> Tuple[float, List[DetectedOverride], bool]:
        """
        Auto-detect all applicable overrides for a rental datetime.

        Args:
            rental_datetime: When the rental starts
            day_type: Day classification from demand model (e.g., "long_weekend", "holiday")

        Returns:
            (combined_factor, list_of_overrides, was_capped)
        """
        overrides = []
        d = rental_datetime.date() if isinstance(rental_datetime, datetime) else rental_datetime
        month = d.month

        # ── 1. Long weekend (from day classification) ──
        if day_type == "long_weekend":
            overrides.append(DetectedOverride(
                name="Long Weekend",
                factor=OVERRIDE_FACTORS["long_weekend"],
                reason=f"Part of an extended weekend stretch (detected from calendar)",
                confidence="high",
                effect="surge",
            ))

        # ── 2. Festival / Holiday (from calendar) ──
        if d in INDIAN_HOLIDAYS:
            holiday_name = INDIAN_HOLIDAYS[d]
            is_festival = any(kw in holiday_name.lower() for kw in
                             ["diwali", "holi", "dussehra", "christmas", "pongal",
                              "ganesh", "onam", "eid", "guru nanak"])
            if is_festival:
                overrides.append(DetectedOverride(
                    name=f"Festival: {holiday_name}",
                    factor=OVERRIDE_FACTORS["festival"],
                    reason=f"{holiday_name} — major festival drives high rental demand",
                    confidence="high",
                    effect="surge",
                ))
            else:
                overrides.append(DetectedOverride(
                    name=f"Holiday: {holiday_name}",
                    factor=OVERRIDE_FACTORS["holiday"],
                    reason=f"{holiday_name} — public holiday increases leisure rentals",
                    confidence="high",
                    effect="surge",
                ))

        # ── 3. Holiday eve (day before a holiday) ──
        elif day_type == "holiday_eve":
            tomorrow = d + timedelta(days=1)
            if tomorrow in INDIAN_HOLIDAYS:
                overrides.append(DetectedOverride(
                    name=f"Eve of {INDIAN_HOLIDAYS[tomorrow]}",
                    factor=OVERRIDE_FACTORS["holiday_eve"],
                    reason=f"Day before {INDIAN_HOLIDAYS[tomorrow]} — early pickup demand",
                    confidence="high",
                    effect="surge",
                ))

        # ── 4. Weather prediction (from data probabilities) ──
        month_str = str(month)
        if month_str in self.weather_by_month:
            weather_probs = self.weather_by_month[month_str]

            rain_prob = weather_probs.get("rain", 0) + weather_probs.get("heavy_rain", 0)
            heavy_rain_prob = weather_probs.get("heavy_rain", 0)

            # Heavy rain likely (>15% of bookings in this month had heavy rain)
            if heavy_rain_prob > 0.15:
                overrides.append(DetectedOverride(
                    name="Heavy Rain Likely",
                    factor=OVERRIDE_FACTORS["heavy_rain_likely"],
                    reason=f"Historical data: {heavy_rain_prob:.0%} of bookings in month {month} had heavy rain",
                    confidence="medium",
                    effect="discount",
                ))
            # Rain likely (>25% of bookings had rain)
            elif rain_prob > 0.25:
                overrides.append(DetectedOverride(
                    name="Rain Likely",
                    factor=OVERRIDE_FACTORS["rain_likely"],
                    reason=f"Historical data: {rain_prob:.0%} of bookings in month {month} had rain",
                    confidence="medium",
                    effect="discount",
                ))

            # Heatwave likely (>20% of bookings had hot weather)
            hot_prob = weather_probs.get("hot", 0)
            if hot_prob > 0.20:
                overrides.append(DetectedOverride(
                    name="Heatwave Likely",
                    factor=OVERRIDE_FACTORS["heatwave_likely"],
                    reason=f"Historical data: {hot_prob:.0%} of bookings in month {month} had heatwave conditions",
                    confidence="medium",
                    effect="discount",
                ))

        # ── Combine all override factors ──
        combined = 1.0
        for o in overrides:
            combined *= o.factor

        was_capped = False
        if combined > MAX_OVERRIDE_FACTOR:
            was_capped = True
            combined = MAX_OVERRIDE_FACTOR
        elif combined < (1.0 / MAX_OVERRIDE_FACTOR):
            was_capped = True
            combined = 1.0 / MAX_OVERRIDE_FACTOR

        return combined, overrides, was_capped
