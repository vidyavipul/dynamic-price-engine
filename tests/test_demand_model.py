"""
Tests for the Demand Model.

Validates demand scoring, day classification, zone classification,
and data-derived profile lookups.
"""

import pytest
from datetime import datetime, date

from app.demand_model import DemandModel, classify_demand_zone, DEMAND_ZONES
from app.config import INDIAN_HOLIDAYS


@pytest.fixture
def model():
    """Create a DemandModel instance."""
    return DemandModel()


# ──────────────────────────────────────────────
# Demand Score Range
# ──────────────────────────────────────────────

class TestDemandScoreRange:
    """Demand score must always be in [0, 1]."""

    def test_score_lower_bound(self, model):
        # Worst case: late-night monsoon weekday
        result = model.estimate_demand(datetime(2025, 7, 15, 3, 0))  # Tue 3AM July
        assert result.score >= 0.0

    def test_score_upper_bound(self, model):
        # Best case: Saturday morning in festive season
        result = model.estimate_demand(datetime(2025, 10, 18, 9, 0))  # Sat 9AM Oct
        assert result.score <= 1.0

    def test_score_various_datetimes(self, model):
        """Score should be in [0, 1] for a wide range of dates."""
        datetimes = [
            datetime(2025, 1, 1, 0, 0),    # New Year midnight
            datetime(2025, 3, 14, 12, 0),   # Holi noon
            datetime(2025, 5, 15, 9, 0),    # Summer weekday morning
            datetime(2025, 7, 20, 3, 0),    # Monsoon night
            datetime(2025, 10, 20, 8, 0),   # Diwali morning
            datetime(2025, 12, 25, 18, 0),  # Christmas evening
        ]
        for dt in datetimes:
            result = model.estimate_demand(dt)
            assert 0.0 <= result.score <= 1.0, f"Score {result.score} out of range for {dt}"


# ──────────────────────────────────────────────
# Weekend vs Weekday
# ──────────────────────────────────────────────

class TestWeekendVsWeekday:
    """Weekends should have higher demand than regular weekdays."""

    def test_saturday_higher_than_weekday(self, model):
        sat = model.estimate_demand(datetime(2025, 2, 15, 9, 0))   # Saturday 9AM
        tue = model.estimate_demand(datetime(2025, 2, 11, 9, 0))   # Tuesday 9AM
        assert sat.score > tue.score, \
            f"Saturday ({sat.score}) should > Tuesday ({tue.score})"

    def test_sunday_higher_than_weekday(self, model):
        sun = model.estimate_demand(datetime(2025, 2, 16, 9, 0))   # Sunday 9AM
        wed = model.estimate_demand(datetime(2025, 2, 12, 9, 0))   # Wednesday 9AM
        assert sun.score > wed.score

    def test_friday_higher_than_midweek(self, model):
        fri = model.estimate_demand(datetime(2025, 2, 14, 9, 0))   # Friday 9AM
        wed = model.estimate_demand(datetime(2025, 2, 12, 9, 0))   # Wednesday 9AM
        assert fri.score > wed.score


# ──────────────────────────────────────────────
# Seasonal Patterns
# ──────────────────────────────────────────────

class TestSeasonalPatterns:
    """Summer and festive seasons should score higher than monsoon."""

    def test_summer_higher_than_monsoon(self, model):
        # Same day-of-week (Wednesday), same time, different months
        summer = model.estimate_demand(datetime(2025, 5, 14, 9, 0))   # May Wed
        monsoon = model.estimate_demand(datetime(2025, 7, 16, 9, 0))  # July Wed
        assert summer.season_score > monsoon.season_score

    def test_festive_higher_than_monsoon(self, model):
        festive = model.estimate_demand(datetime(2025, 10, 15, 9, 0))  # Oct Wed
        monsoon = model.estimate_demand(datetime(2025, 7, 16, 9, 0))   # July Wed
        assert festive.season_score > monsoon.season_score


# ──────────────────────────────────────────────
# Long Weekend Detection
# ──────────────────────────────────────────────

class TestLongWeekendDetection:
    """Long weekends should be detected and score highest."""

    def test_monday_holiday_creates_long_weekend(self, model):
        # Jan 26, 2026 is Monday (Republic Day)
        sat = model.estimate_demand(datetime(2026, 1, 24, 9, 0))   # Sat before
        sun = model.estimate_demand(datetime(2026, 1, 25, 9, 0))   # Sun
        mon = model.estimate_demand(datetime(2026, 1, 26, 9, 0))   # Mon (Republic Day)

        for result in [sat, sun, mon]:
            assert result.day_type == "long_weekend", \
                f"{result} should be long_weekend, got {result.day_type}"

    def test_long_weekend_higher_than_regular_weekend(self, model):
        long_wknd = model.estimate_demand(datetime(2026, 1, 24, 9, 0))  # Long weekend Sat
        regular_sat = model.estimate_demand(datetime(2025, 2, 15, 9, 0))  # Regular Sat
        assert long_wknd.day_type_score >= regular_sat.day_type_score


# ──────────────────────────────────────────────
# Bridge Day Detection
# ──────────────────────────────────────────────

class TestBridgeDayDetection:
    """Bridge days connecting holidays to weekends should score high."""

    def test_tuesday_holiday_monday_bridge(self, model):
        """If Tuesday is a holiday, Monday should be detected as part of long weekend."""
        # Check if any Tuesday holidays exist in our calendar
        for d, name in INDIAN_HOLIDAYS.items():
            if d.weekday() == 1:  # Tuesday
                monday = date(d.year, d.month, d.day - 1) if d.day > 1 else d
                from datetime import timedelta
                monday = d - timedelta(days=1)
                result = model.estimate_demand(datetime(monday.year, monday.month, monday.day, 9, 0))
                # Monday should be classified as long_weekend (part of Sat-Sun-Mon-Tue stretch)
                assert result.day_type in ("long_weekend", "bridge_strong"), \
                    f"Monday before Tuesday holiday ({name}) should be long_weekend or bridge_strong, got {result.day_type}"
                break  # Test at least one


# ──────────────────────────────────────────────
# Demand Zone Classification
# ──────────────────────────────────────────────

class TestDemandZones:
    """Zone classification should match score boundaries."""

    def test_dead_zone(self):
        zone = classify_demand_zone(0.10)
        assert zone.name == "Dead"

    def test_low_zone(self):
        zone = classify_demand_zone(0.25)
        assert zone.name == "Low"

    def test_normal_zone(self):
        zone = classify_demand_zone(0.50)
        assert zone.name == "Normal"

    def test_high_zone(self):
        zone = classify_demand_zone(0.70)
        assert zone.name == "High"

    def test_surge_zone(self):
        zone = classify_demand_zone(0.90)
        assert zone.name == "Surge"

    def test_boundary_values(self):
        """Test exact boundary values."""
        assert classify_demand_zone(0.0).name == "Dead"
        assert classify_demand_zone(0.15).name == "Low"    # >= 0.15
        assert classify_demand_zone(0.40).name == "Normal"  # >= 0.40
        assert classify_demand_zone(0.60).name == "High"    # >= 0.60
        assert classify_demand_zone(0.80).name == "Surge"   # >= 0.80
        assert classify_demand_zone(1.0).name == "Surge"


# ──────────────────────────────────────────────
# Holiday Detection
# ──────────────────────────────────────────────

class TestHolidayDetection:
    """Known holidays should be detected from the calendar."""

    def test_republic_day_detected(self, model):
        result = model.estimate_demand(datetime(2025, 1, 26, 9, 0))
        assert result.is_holiday
        assert result.holiday_name is not None

    def test_diwali_detected(self, model):
        result = model.estimate_demand(datetime(2025, 10, 20, 9, 0))
        assert result.is_holiday

    def test_regular_day_not_holiday(self, model):
        result = model.estimate_demand(datetime(2025, 6, 10, 9, 0))
        assert not result.is_holiday


# ──────────────────────────────────────────────
# Time Slot Patterns
# ──────────────────────────────────────────────

class TestTimeSlotPatterns:
    """Morning should score higher than late night."""

    def test_morning_higher_than_night(self, model):
        morning = model.estimate_demand(datetime(2025, 5, 14, 9, 0))
        night = model.estimate_demand(datetime(2025, 5, 14, 3, 0))
        assert morning.time_slot_score > night.time_slot_score
