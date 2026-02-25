"""
Demand Model v2 — Cross-Dimensional Scoring via DuckDB Profiles.

Instead of blending 3 independent scores (day_type × season × time_slot),
v2 uses cross-dimensional matrices:
- hour_by_dow: "Friday 6 PM" gets its own score
- dow_by_month: "Saturday in October" gets its own score
- hour_by_day_type: "9 AM on a long_weekend" gets its own score

This produces more nuanced demand scores because the interaction
between dimensions is captured in the data, not estimated by blending.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Optional, Dict

from app.config import INDIAN_HOLIDAYS

# Re-use shared types from v1
from app.demand_model import DemandZone, DemandResult, DEMAND_ZONES, classify_demand_zone


# v2 weights: cross-dimensional profiles get higher weight
WEIGHT_CROSS_HOUR_DOW = 0.35        # Hour × Day-of-week (e.g., "Friday 6 PM")
WEIGHT_CROSS_DOW_MONTH = 0.25       # Day-of-week × Month (e.g., "Sat in October")
WEIGHT_CROSS_HOUR_DAYTYPE = 0.25    # Hour × Day-type (e.g., "9 AM on long_weekend")
WEIGHT_WEATHER = 0.15               # Weather impact for the month


class DemandModelV2:
    """
    Enhanced demand model using DuckDB cross-dimensional profiles.

    Key difference from v1:
    - v1 scores Friday (0.36) and 6PM (0.35) independently → blend ≈ 0.35
    - v2 looks up "Friday 6 PM" directly from data → might be 0.55
      (because Friday evenings are a pickup hotspot for weekend trips)
    """

    def __init__(self, profiles_path: Optional[str] = None):
        """Load DuckDB profiles from JSON file."""
        if profiles_path is None:
            profiles_path = os.path.join(
                os.path.dirname(__file__), "..", "data", "demand_profiles_duckdb.json"
            )

        self.profiles = {}
        self.using_fallback = False

        if os.path.exists(profiles_path):
            with open(profiles_path, "r") as f:
                self.profiles = json.load(f)
        else:
            self.using_fallback = True
            # Fall back to v1 profiles
            v1_path = os.path.join(
                os.path.dirname(__file__), "..", "data", "demand_profiles.json"
            )
            if os.path.exists(v1_path):
                with open(v1_path, "r") as f:
                    self.profiles = json.load(f)

    def estimate_demand(self, rental_datetime: datetime) -> DemandResult:
        """
        Estimate demand using cross-dimensional profiles.

        Uses combined lookups (hour×dow, dow×month, hour×day_type)
        instead of blending independent scores.
        """
        d = rental_datetime.date() if isinstance(rental_datetime, datetime) else rental_datetime
        hour = rental_datetime.hour if isinstance(rental_datetime, datetime) else 0
        weekday = d.weekday()
        month = d.month

        # Classify the day type
        day_type = self._classify_day(d)

        # === Cross-dimensional lookups ===

        # 1. Hour × Day-of-Week (e.g., "Friday 6 PM")
        hour_dow_score = self._get_cross_score(
            "hour_by_dow", str(weekday), str(hour), 0.35
        )

        # 2. Day-of-Week × Month (e.g., "Saturday in October")
        dow_month_score = self._get_cross_score(
            "dow_by_month", str(weekday), str(month), 0.40
        )

        # 3. Hour × Day-Type (e.g., "9 AM on long_weekend")
        hour_daytype_score = self._get_cross_score(
            "hour_by_day_type", day_type, str(hour), 0.40
        )

        # 4. Weather impact for this month
        weather_score = self._get_weather_score(month)

        # Blend cross-dimensional scores
        score = (
            WEIGHT_CROSS_HOUR_DOW * hour_dow_score +
            WEIGHT_CROSS_DOW_MONTH * dow_month_score +
            WEIGHT_CROSS_HOUR_DAYTYPE * hour_daytype_score +
            WEIGHT_WEATHER * weather_score
        )
        score = max(0.0, min(1.0, score))

        # Also compute v1-compatible individual scores for display
        day_type_score = self._get_single_score("day_type", day_type, 0.35)
        season_score = self._get_single_score("monthly", str(month), 0.5)
        time_slot_score = self._get_single_score("hourly", str(hour), 0.3)

        # Holiday info
        is_holiday = d in INDIAN_HOLIDAYS
        holiday_name = INDIAN_HOLIDAYS.get(d)

        return DemandResult(
            score=round(score, 4),
            zone=classify_demand_zone(score),
            day_type=day_type,
            day_type_score=round(day_type_score, 4),
            season_score=round(season_score, 4),
            time_slot_score=round(time_slot_score, 4),
            hour=hour,
            month=month,
            weekday=weekday,
            is_holiday=is_holiday,
            holiday_name=holiday_name,
        )

    # ── Lookups ──────────────────────────────────

    def _get_cross_score(self, profile_name: str, dim1: str, dim2: str, default: float) -> float:
        """Look up a cross-dimensional score."""
        matrix = self.profiles.get(profile_name, {})
        row = matrix.get(dim1, {})
        return row.get(dim2, default)

    def _get_single_score(self, profile_name: str, key: str, default: float) -> float:
        """Look up a single-dimension score (for display)."""
        return self.profiles.get(profile_name, {}).get(key, default)

    def _get_weather_score(self, month: int) -> float:
        """
        Compute a weather-adjusted demand score for the month.

        Uses weather_impact data: clear=1.0 baseline, rain<1.0, hot>1.0.
        Blends by probability to get expected demand impact.
        """
        weather_impact = self.profiles.get("weather_impact", {})
        weather_by_month = self.profiles.get("weather_by_month", {})

        month_weather = weather_by_month.get(str(month), {})
        if not month_weather or not weather_impact:
            return 0.5  # neutral default

        # Weighted average of demand ratios by probability
        total_ratio = 0.0
        for weather_type, prob in month_weather.items():
            impact = weather_impact.get(weather_type, {})
            ratio = impact.get("ratio_vs_clear", 1.0)
            total_ratio += prob * ratio

        # Clamp to [0, 1] — clear=1.0 baseline
        return max(0.0, min(1.0, total_ratio))

    # ── Day classification (same as v1) ──────────

    def _classify_day(self, d: date) -> str:
        """Classify a date for demand estimation."""
        weekday = d.weekday()
        is_holiday = d in INDIAN_HOLIDAYS
        month = d.month

        if self._is_long_weekend_day(d):
            return "long_weekend"
        if is_holiday:
            return "holiday"
        if self._is_strong_bridge(d):
            return "bridge_strong"

        tomorrow = d + timedelta(days=1)
        if tomorrow in INDIAN_HOLIDAYS:
            return "holiday_eve"

        if weekday == 5:
            return "saturday"
        if weekday == 6:
            return "sunday"
        if weekday == 4:
            return "friday"

        if self._is_weak_bridge(d):
            return "bridge_weak"

        return "regular_weekday"

    def _is_long_weekend_day(self, d: date) -> bool:
        """Check if date is part of a 3+ day weekend stretch."""
        for offset in range(-3, 4):
            check = d + timedelta(days=offset)
            if check in INDIAN_HOLIDAYS:
                hw = check.weekday()
                if hw == 0 and d in {check - timedelta(2), check - timedelta(1), check}:
                    return True
                if hw == 4 and d in {check, check + timedelta(1), check + timedelta(2)}:
                    return True
                if hw == 1 and d in {check - timedelta(3), check - timedelta(2),
                                      check - timedelta(1), check}:
                    return True
                if hw == 3 and d in {check, check + timedelta(1),
                                      check + timedelta(2), check + timedelta(3)}:
                    return True
        return False

    def _is_strong_bridge(self, d: date) -> bool:
        """Single leave day creating 4-day weekend."""
        weekday = d.weekday()
        if weekday == 0 and (d + timedelta(1)) in INDIAN_HOLIDAYS:
            return True
        if weekday == 4 and (d - timedelta(1)) in INDIAN_HOLIDAYS:
            return True
        return False

    def _is_weak_bridge(self, d: date) -> bool:
        """Needs 2 leave days to connect to weekend."""
        for offset in range(-2, 3):
            check = d + timedelta(days=offset)
            if check in INDIAN_HOLIDAYS and check.weekday() == 2 and check != d:
                return True
        return False
