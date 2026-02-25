"""
Tests for DuckDB Analyzer and Demand Model V2.

Validates:
- DuckDB profiles match pandas profiles (single-dimension consistency)
- Cross-dimensional profiles are populated and meaningful
- DemandModelV2 produces valid scores using cross-dimensional lookups
- V2 gives more nuanced results than V1 for specific scenarios
"""

import json
import os
import pytest
from datetime import datetime

from app.demand_model import DemandModel
from app.demand_model_v2 import DemandModelV2
from app.price_engine import PriceEngine


DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DUCKDB_PROFILES_PATH = os.path.join(DATA_DIR, "demand_profiles_duckdb.json")
V1_PROFILES_PATH = os.path.join(DATA_DIR, "demand_profiles.json")


@pytest.fixture
def duckdb_profiles():
    """Load DuckDB profiles."""
    with open(DUCKDB_PROFILES_PATH, "r") as f:
        return json.load(f)


@pytest.fixture
def v1_profiles():
    """Load v1 (pandas) profiles."""
    with open(V1_PROFILES_PATH, "r") as f:
        return json.load(f)


@pytest.fixture
def v2_model():
    """Create a DemandModelV2 instance."""
    return DemandModelV2()


@pytest.fixture
def v1_model():
    """Create a v1 DemandModel instance."""
    return DemandModel()


@pytest.fixture
def v2_engine():
    """Create a PriceEngine with v2 demand model."""
    model = DemandModelV2()
    return PriceEngine(model)


# ──────────────────────────────────────────────
# DuckDB Profiles: Structure & Completeness
# ──────────────────────────────────────────────

class TestDuckDBProfiles:
    """DuckDB profiles should contain all required sections."""

    def test_has_single_dimension_profiles(self, duckdb_profiles):
        """Should have all v1-compatible profiles."""
        for key in ["hourly", "day_of_week", "monthly", "day_type", "weather_by_month"]:
            assert key in duckdb_profiles, f"Missing profile: {key}"

    def test_has_cross_dimensional_profiles(self, duckdb_profiles):
        """Should have the cross-dimensional matrices."""
        for key in ["hour_by_dow", "dow_by_month", "hour_by_day_type"]:
            assert key in duckdb_profiles, f"Missing cross-dim profile: {key}"

    def test_has_weather_impact(self, duckdb_profiles):
        """Should have weather impact analysis."""
        assert "weather_impact" in duckdb_profiles
        impact = duckdb_profiles["weather_impact"]
        assert "clear" in impact
        assert "rain" in impact
        # Rain should have lower demand ratio than clear
        assert impact["rain"]["ratio_vs_clear"] < impact["clear"]["ratio_vs_clear"]

    def test_has_top_demand_slots(self, duckdb_profiles):
        """Should rank top demand combinations."""
        assert "top_demand_slots" in duckdb_profiles
        slots = duckdb_profiles["top_demand_slots"]
        assert len(slots) > 0
        # Top slot should be long_weekend
        assert slots[0]["day_type"] == "long_weekend"

    def test_has_demand_volatility(self, duckdb_profiles):
        """Should have volatility data per hour."""
        assert "demand_volatility" in duckdb_profiles
        vol = duckdb_profiles["demand_volatility"]
        # Should have entries for all 24 hours
        assert len(vol) == 24

    def test_analyzer_tag(self, duckdb_profiles):
        """Stats should tag the analyzer used."""
        assert duckdb_profiles["stats"]["analyzer"] == "duckdb"


# ──────────────────────────────────────────────
# V1 ↔ DuckDB Profile Consistency
# ──────────────────────────────────────────────

class TestProfileConsistency:
    """DuckDB single-dimension profiles should broadly match v1 (pandas)."""

    def test_same_day_type_ranking(self, v1_profiles, duckdb_profiles):
        """Day type ranking order should be the same."""
        v1_sorted = sorted(v1_profiles["day_type"].items(), key=lambda x: x[1], reverse=True)
        duck_sorted = sorted(duckdb_profiles["day_type"].items(), key=lambda x: x[1], reverse=True)
        # Top 3 should match
        v1_top3 = [k for k, _ in v1_sorted[:3]]
        duck_top3 = [k for k, _ in duck_sorted[:3]]
        assert v1_top3 == duck_top3, f"Top 3 mismatch: v1={v1_top3} vs duck={duck_top3}"

    def test_long_weekend_is_highest(self, duckdb_profiles):
        """long_weekend should be the highest demand day type."""
        day_types = duckdb_profiles["day_type"]
        assert day_types["long_weekend"] == 1.0

    def test_regular_weekday_is_among_lowest(self, duckdb_profiles):
        """regular_weekday should be among the lowest demand."""
        day_types = duckdb_profiles["day_type"]
        assert day_types["regular_weekday"] < 0.4


# ──────────────────────────────────────────────
# Cross-Dimensional Profile Values
# ──────────────────────────────────────────────

class TestCrossDimensionalProfiles:
    """Cross-dimensional matrices should capture interaction effects."""

    def test_hour_by_dow_has_all_days(self, duckdb_profiles):
        """hour_by_dow should have entries for 7 days of the week."""
        hour_by_dow = duckdb_profiles["hour_by_dow"]
        assert len(hour_by_dow) >= 7

    def test_friday_evening_higher_than_tuesday_evening(self, duckdb_profiles):
        """Friday 18:00 should have higher demand than Tuesday 18:00."""
        hour_by_dow = duckdb_profiles["hour_by_dow"]
        # DuckDB DOW: 0=Sunday, 1=Monday, ..., 5=Friday, 6=Saturday
        friday_evening = hour_by_dow.get("5", {}).get("18", 0)
        tuesday_evening = hour_by_dow.get("2", {}).get("18", 0)
        assert friday_evening > tuesday_evening, \
            f"Friday 6PM ({friday_evening}) should > Tuesday 6PM ({tuesday_evening})"

    def test_saturday_morning_is_peak(self, duckdb_profiles):
        """Saturday 8-9 AM should be among the highest in hour_by_dow."""
        hour_by_dow = duckdb_profiles["hour_by_dow"]
        # DuckDB DOW: 6=Saturday
        sat_8am = hour_by_dow.get("6", {}).get("8", 0)
        assert sat_8am > 0.7, f"Saturday 8 AM should be high demand, got {sat_8am}"

    def test_october_saturday_higher_than_july_saturday(self, duckdb_profiles):
        """Saturday in October should have higher demand than Saturday in July."""
        dow_by_month = duckdb_profiles["dow_by_month"]
        # DuckDB DOW: 6=Saturday
        sat_oct = dow_by_month.get("6", {}).get("10", 0)
        sat_jul = dow_by_month.get("6", {}).get("7", 0)
        assert sat_oct > sat_jul, \
            f"Sat in Oct ({sat_oct}) should > Sat in Jul ({sat_jul})"


# ──────────────────────────────────────────────
# DemandModelV2 Scoring
# ──────────────────────────────────────────────

class TestDemandModelV2:
    """V2 model should produce valid, meaningful scores."""

    def test_score_range(self, v2_model):
        """Score should always be in [0, 1]."""
        for dt in [
            datetime(2025, 5, 15, 9, 0),
            datetime(2025, 7, 15, 3, 0),
            datetime(2025, 10, 18, 9, 0),
            datetime(2025, 12, 25, 12, 0),
        ]:
            result = v2_model.estimate_demand(dt)
            assert 0.0 <= result.score <= 1.0, f"Score {result.score} out of range for {dt}"

    def test_weekend_higher_than_weekday(self, v2_model):
        """Saturday should score higher than Tuesday."""
        sat = v2_model.estimate_demand(datetime(2025, 5, 17, 9, 0))  # Saturday
        tue = v2_model.estimate_demand(datetime(2025, 5, 13, 9, 0))  # Tuesday
        assert sat.score > tue.score

    def test_peak_hour_higher_than_night(self, v2_model):
        """9 AM Saturday should score higher than 3 AM Saturday."""
        morning = v2_model.estimate_demand(datetime(2025, 5, 17, 9, 0))
        night = v2_model.estimate_demand(datetime(2025, 5, 17, 3, 0))
        assert morning.score > night.score

    def test_returns_demand_result_type(self, v2_model):
        """Should return the same DemandResult type as v1."""
        from app.demand_model import DemandResult
        result = v2_model.estimate_demand(datetime(2025, 5, 15, 9, 0))
        assert isinstance(result, DemandResult)


# ──────────────────────────────────────────────
# V2 Engine Integration
# ──────────────────────────────────────────────

class TestV2EngineIntegration:
    """PriceEngine should work with DemandModelV2."""

    def test_basic_pricing(self, v2_engine):
        """V2 engine should produce valid prices."""
        result = v2_engine.calculate_price(
            datetime(2025, 5, 15, 9, 0), "standard_bike", 8
        )
        assert result.final_price > 0

    def test_weekend_costs_more(self, v2_engine):
        """Saturday should cost more than Tuesday with v2 engine."""
        sat = v2_engine.calculate_price(
            datetime(2025, 5, 17, 9, 0), "standard_bike", 8
        )
        tue = v2_engine.calculate_price(
            datetime(2025, 5, 13, 9, 0), "standard_bike", 8
        )
        assert sat.final_price > tue.final_price

    def test_holiday_detected(self, v2_engine):
        """V2 engine should still auto-detect overrides."""
        result = v2_engine.calculate_price(
            datetime(2025, 10, 20, 9, 0),  # Diwali
            "standard_bike", 8
        )
        names = [o["name"] for o in result.overrides_detected]
        assert any("diwali" in n.lower() or "festival" in n.lower() for n in names)

    def test_explanation_present(self, v2_engine):
        """V2 engine should still generate explanations."""
        result = v2_engine.calculate_price(
            datetime(2025, 5, 15, 9, 0), "standard_bike", 8
        )
        assert len(result.explanation) >= 5
