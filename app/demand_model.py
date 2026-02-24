"""
Demand Model — Loads data-derived profiles and scores any datetime.

The demand score is a weighted blend of three signals:
- Day type (45%): long_weekend, holiday, bridge, weekday, etc.
- Season/month (30%): summer peak, monsoon dip, festive surge
- Time slot/hour (25%): morning pickup peak, late night dead zone

All scores come from demand_profiles.json (computed by analyze_demand.py).
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Optional, Dict

from app.config import (
    WEIGHT_DAY_TYPE, WEIGHT_SEASON, WEIGHT_TIME_SLOT,
    INDIAN_HOLIDAYS
)


@dataclass
class DemandZone:
    """Demand intensity classification."""
    name: str
    color: str
    emoji: str
    description: str


# Demand intensity zones
DEMAND_ZONES = [
    DemandZone("Dead", "#3B82F6", "🔵", "Deep discount — near-zero demand"),
    DemandZone("Low", "#22C55E", "🟢", "Below normal — discount pricing"),
    DemandZone("Normal", "#9CA3AF", "⚪", "Baseline — standard pricing"),
    DemandZone("High", "#EAB308", "🟡", "Above normal — mild surge"),
    DemandZone("Surge", "#EF4444", "🔴", "Peak demand — full surge pricing"),
]


def classify_demand_zone(score: float) -> DemandZone:
    """Map a demand score (0-1) to an intensity zone."""
    if score < 0.15:
        return DEMAND_ZONES[0]  # Dead
    elif score < 0.40:
        return DEMAND_ZONES[1]  # Low
    elif score < 0.60:
        return DEMAND_ZONES[2]  # Normal
    elif score < 0.80:
        return DEMAND_ZONES[3]  # High
    else:
        return DEMAND_ZONES[4]  # Surge


@dataclass
class DemandResult:
    """Complete demand estimation result."""
    score: float               # 0-1 blended demand score
    zone: DemandZone           # Classified intensity zone
    day_type: str              # e.g., "long_weekend", "regular_weekday"
    day_type_score: float      # Raw score for day type
    season_score: float        # Raw score for month/season
    time_slot_score: float     # Raw score for hour
    hour: int
    month: int
    weekday: int
    is_holiday: bool
    holiday_name: Optional[str]


class DemandModel:
    """
    Demand scorer powered by data-derived profiles.

    Loads profiles from demand_profiles.json and uses them to score
    any given datetime. Falls back to rule-based defaults if profiles
    are not available.
    """

    def __init__(self, profiles_path: Optional[str] = None):
        """Load demand profiles from JSON file."""
        if profiles_path is None:
            profiles_path = os.path.join(
                os.path.dirname(__file__), "..", "data", "demand_profiles.json"
            )

        self.profiles = {}
        self.using_fallback = False

        if os.path.exists(profiles_path):
            with open(profiles_path, "r") as f:
                self.profiles = json.load(f)
        else:
            self.using_fallback = True
            self.profiles = self._fallback_profiles()

    def estimate_demand(self, rental_datetime: datetime) -> DemandResult:
        """
        Estimate demand for a given rental datetime.

        Returns a DemandResult with the blended score and breakdown.
        """
        d = rental_datetime.date() if isinstance(rental_datetime, datetime) else rental_datetime
        hour = rental_datetime.hour if isinstance(rental_datetime, datetime) else 0
        weekday = d.weekday()
        month = d.month

        # 1. Day type score (45% weight)
        day_type = self._classify_day(d)
        day_type_score = self._get_day_type_score(day_type)

        # 2. Season/month score (30% weight)
        season_score = self._get_monthly_score(month)

        # 3. Time slot score (25% weight)
        time_slot_score = self._get_hourly_score(hour)

        # Blend
        score = (
            WEIGHT_DAY_TYPE * day_type_score +
            WEIGHT_SEASON * season_score +
            WEIGHT_TIME_SLOT * time_slot_score
        )
        score = max(0.0, min(1.0, score))  # Clamp to [0, 1]

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

    # ── Profile lookups ──────────────────────────

    def _get_day_type_score(self, day_type: str) -> float:
        """Look up day type score from data-derived profiles."""
        day_type_profiles = self.profiles.get("day_type", {})
        return day_type_profiles.get(day_type, 0.35)  # default to low

    def _get_monthly_score(self, month: int) -> float:
        """Look up monthly score from data-derived profiles."""
        monthly_profiles = self.profiles.get("monthly", {})
        return monthly_profiles.get(str(month), 0.5)

    def _get_hourly_score(self, hour: int) -> float:
        """Look up hourly score from data-derived profiles."""
        hourly_profiles = self.profiles.get("hourly", {})
        return hourly_profiles.get(str(hour), 0.3)

    # ── Day classification (mirrors generate_dataset logic) ──

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
        if month in (3, 4) and weekday < 5:
            return "exam_weekday"

        return "regular_weekday"

    def _is_long_weekend_day(self, d: date) -> bool:
        """Check if date is part of a 3+ day weekend stretch."""
        for offset in range(-3, 4):
            check = d + timedelta(days=offset)
            if check in INDIAN_HOLIDAYS:
                hw = check.weekday()

                # Monday holiday → Sat-Sun-Mon
                if hw == 0:
                    if d in {check - timedelta(2), check - timedelta(1), check}:
                        return True

                # Friday holiday → Fri-Sat-Sun
                if hw == 4:
                    if d in {check, check + timedelta(1), check + timedelta(2)}:
                        return True

                # Tuesday holiday → Sat-Sun-Mon(bridge)-Tue
                if hw == 1:
                    if d in {check - timedelta(3), check - timedelta(2),
                             check - timedelta(1), check}:
                        return True

                # Thursday holiday → Thu-Fri(bridge)-Sat-Sun
                if hw == 3:
                    if d in {check, check + timedelta(1),
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

    # ── Fallback profiles (used when demand_profiles.json doesn't exist) ──

    @staticmethod
    def _fallback_profiles() -> Dict:
        """Rule-based fallback if no data profiles exist yet."""
        return {
            "hourly": {
                "0": 0.02, "1": 0.01, "2": 0.01, "3": 0.01, "4": 0.02, "5": 0.05,
                "6": 0.15, "7": 0.70, "8": 0.95, "9": 1.00, "10": 0.65, "11": 0.50,
                "12": 0.40, "13": 0.35, "14": 0.35, "15": 0.40, "16": 0.50, "17": 0.45,
                "18": 0.35, "19": 0.25, "20": 0.15, "21": 0.08, "22": 0.05, "23": 0.02,
            },
            "day_of_week": {
                "0": 0.45, "1": 0.40, "2": 0.40, "3": 0.45, "4": 0.60,
                "5": 0.95, "6": 0.80,
            },
            "monthly": {
                "1": 0.55, "2": 0.50, "3": 0.70, "4": 0.65, "5": 1.00, "6": 0.40,
                "7": 0.25, "8": 0.30, "9": 0.35, "10": 0.88, "11": 0.85, "12": 0.60,
            },
            "day_type": {
                "long_weekend": 1.00,
                "holiday": 0.90,
                "bridge_strong": 0.85,
                "holiday_eve": 0.70,
                "saturday": 0.80,
                "sunday": 0.65,
                "friday": 0.55,
                "bridge_weak": 0.45,
                "regular_weekday": 0.35,
                "exam_weekday": 0.18,
            },
        }
