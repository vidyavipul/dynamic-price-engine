"""
Tests for the Price Engine with auto-detected overrides.

Validates pricing calculations, edge cases, multiplier bounds,
auto-override detection, duration discounts, and input validation.
"""

import pytest
from datetime import datetime

from app.price_engine import PriceEngine
from app.demand_model import DemandModel
from app.config import MIN_MULTIPLIER, MAX_MULTIPLIER, VEHICLE_BASE_RATES, VehicleType


@pytest.fixture
def engine():
    """Create a PriceEngine instance."""
    model = DemandModel()
    return PriceEngine(model)


# ──────────────────────────────────────────────
# Basic Price Calculation
# ──────────────────────────────────────────────

class TestBasicPricing:
    """Price should be computed correctly from demand."""

    def test_returns_positive_price(self, engine):
        result = engine.calculate_price(
            rental_datetime=datetime(2025, 5, 15, 9, 0),
            vehicle_type="standard_bike",
            duration_hours=8,
        )
        assert result.final_price > 0

    def test_price_increases_with_duration(self, engine):
        short = engine.calculate_price(
            datetime(2025, 5, 15, 9, 0), "standard_bike", 4
        )
        long = engine.calculate_price(
            datetime(2025, 5, 15, 9, 0), "standard_bike", 8
        )
        assert long.final_price > short.final_price

    def test_premium_vehicle_costs_more(self, engine):
        standard = engine.calculate_price(
            datetime(2025, 5, 15, 9, 0), "standard_bike", 8
        )
        premium = engine.calculate_price(
            datetime(2025, 5, 15, 9, 0), "premium_bike", 8
        )
        assert premium.final_price > standard.final_price


# ──────────────────────────────────────────────
# Demand-Based Pricing (Below vs Above Baseline)
# ──────────────────────────────────────────────

class TestDemandBasedPricing:
    """Below-baseline demand should give discounts, above-baseline should surge."""

    def test_low_demand_discount(self, engine):
        """Late night monsoon weekday should have low multiplier."""
        result = engine.calculate_price(
            datetime(2025, 7, 15, 3, 0),  # Tuesday 3AM July
            "standard_bike", 4
        )
        # Monsoon late night = low demand
        assert result.surge_multiplier < 1.0

    def test_high_demand_surge(self, engine):
        """Saturday morning in festive season should have multiplier > 1.0."""
        result = engine.calculate_price(
            datetime(2025, 10, 18, 9, 0),  # Sat 9AM October
            "standard_bike", 8
        )
        assert result.surge_multiplier > 1.0

    def test_weekend_more_expensive_than_weekday(self, engine):
        sat = engine.calculate_price(
            datetime(2025, 5, 17, 9, 0), "standard_bike", 8  # Saturday
        )
        tue = engine.calculate_price(
            datetime(2025, 5, 13, 9, 0), "standard_bike", 8  # Tuesday
        )
        assert sat.final_price > tue.final_price


# ──────────────────────────────────────────────
# Multiplier Bounds
# ──────────────────────────────────────────────

class TestMultiplierBounds:
    """Final multiplier must stay within [MIN, MAX] bounds."""

    def test_multiplier_never_below_min(self, engine):
        # Worst case: monsoon late night with potential rain discount
        result = engine.calculate_price(
            datetime(2025, 7, 15, 3, 0),  # Tue 3AM monsoon
            "scooter", 1,
        )
        assert result.final_multiplier >= MIN_MULTIPLIER

    def test_multiplier_never_above_max(self, engine):
        # Best case: holiday in festive season
        result = engine.calculate_price(
            datetime(2025, 10, 20, 9, 0),  # Diwali morning
            "super_premium", 8,
        )
        assert result.final_multiplier <= MAX_MULTIPLIER

    def test_zero_demand_floor(self, engine):
        """Even in worst case, price should never be ₹0."""
        result = engine.calculate_price(
            datetime(2025, 7, 15, 3, 0),
            "scooter", 1,
        )
        assert result.final_price > 0
        min_expected = VEHICLE_BASE_RATES[VehicleType.SCOOTER] * MIN_MULTIPLIER * 1
        assert result.final_price >= min_expected * 0.99  # Allow tiny float drift


# ──────────────────────────────────────────────
# Auto-Detected Overrides
# ──────────────────────────────────────────────

class TestAutoDetectedOverrides:
    """Overrides should be auto-detected from the rental datetime."""

    def test_holiday_auto_detected(self, engine):
        """Diwali should auto-detect a festival override."""
        result = engine.calculate_price(
            datetime(2025, 10, 20, 9, 0),  # Diwali
            "standard_bike", 8
        )
        names = [o["name"] for o in result.overrides_detected]
        assert any("diwali" in n.lower() or "festival" in n.lower() for n in names), \
            f"Expected Diwali override in {names}"

    def test_monsoon_rain_auto_detected(self, engine):
        """July bookings should auto-detect rain from weather probabilities."""
        result = engine.calculate_price(
            datetime(2025, 7, 15, 9, 0),  # July (monsoon)
            "standard_bike", 8
        )
        names = [o["name"] for o in result.overrides_detected]
        # Either rain or heavy rain should be detected for monsoon months
        assert any("rain" in n.lower() for n in names), \
            f"Expected rain override in July. Got: {names}"

    def test_rain_is_discount(self, engine):
        """Rain override should be a discount (factor < 1.0)."""
        result = engine.calculate_price(
            datetime(2025, 7, 15, 9, 0),
            "standard_bike", 8
        )
        rain_overrides = [o for o in result.overrides_detected if "rain" in o["name"].lower()]
        for o in rain_overrides:
            assert o["factor"] < 1.0, f"Rain should be discount, got factor {o['factor']}"
            assert o["effect"] == "discount"

    def test_winter_no_rain_detected(self, engine):
        """December should NOT auto-detect rain (dry winter)."""
        result = engine.calculate_price(
            datetime(2025, 12, 10, 9, 0),  # Dec weekday
            "standard_bike", 8
        )
        names = [o["name"] for o in result.overrides_detected]
        assert not any("rain" in n.lower() for n in names), \
            f"Should not detect rain in December. Got: {names}"

    def test_no_manual_overrides_param(self, engine):
        """Engine should not accept active_overrides parameter anymore."""
        import inspect
        sig = inspect.signature(engine.calculate_price)
        assert "active_overrides" not in sig.parameters, \
            "calculate_price should no longer have active_overrides parameter"

    def test_regular_weekday_no_surge_overrides(self, engine):
        """A normal February weekday should have no surge overrides."""
        result = engine.calculate_price(
            datetime(2025, 2, 12, 9, 0),  # Wed Feb
            "standard_bike", 8
        )
        surge_overrides = [o for o in result.overrides_detected if o["effect"] == "surge"]
        assert len(surge_overrides) == 0, \
            f"Regular weekday should have no surge overrides. Got: {surge_overrides}"

    def test_override_confidence_present(self, engine):
        """All auto-detected overrides should have confidence level."""
        result = engine.calculate_price(
            datetime(2025, 10, 20, 9, 0),  # Diwali
            "standard_bike", 8
        )
        for o in result.overrides_detected:
            assert o["confidence"] in ("high", "medium", "low"), \
                f"Override missing confidence: {o}"

    def test_friday_evening_detected(self, engine):
        """Friday 6 PM should auto-detect a Friday evening pickup surge."""
        result = engine.calculate_price(
            datetime(2025, 5, 16, 18, 0),  # Friday 6 PM
            "standard_bike", 8
        )
        names = [o["name"] for o in result.overrides_detected]
        assert any("friday" in n.lower() for n in names), \
            f"Expected Friday evening override. Got: {names}"

    def test_friday_morning_not_detected(self, engine):
        """Friday 9 AM should NOT trigger Friday evening override."""
        result = engine.calculate_price(
            datetime(2025, 5, 16, 9, 0),  # Friday 9 AM
            "standard_bike", 8
        )
        names = [o["name"] for o in result.overrides_detected]
        assert not any("friday" in n.lower() for n in names), \
            f"Friday morning should NOT trigger evening override. Got: {names}"

    def test_friday_evening_costs_more_than_morning(self, engine):
        """Friday 6 PM should cost more than Friday 9 AM (same day)."""
        evening = engine.calculate_price(
            datetime(2025, 5, 16, 18, 0), "standard_bike", 8
        )
        morning = engine.calculate_price(
            datetime(2025, 5, 16, 9, 0), "standard_bike", 8
        )
        assert evening.final_price > morning.final_price, \
            f"Friday evening (₹{evening.final_price}) should > morning (₹{morning.final_price})"


# ──────────────────────────────────────────────
# Duration Discounts
# ──────────────────────────────────────────────

class TestDurationDiscounts:
    """Longer rentals should receive duration discounts."""

    def test_4hr_discount(self, engine):
        result = engine.calculate_price(
            datetime(2025, 5, 15, 9, 0), "standard_bike", 4
        )
        assert result.duration_discount == 0.90  # 10% off

    def test_8hr_discount(self, engine):
        result = engine.calculate_price(
            datetime(2025, 5, 15, 9, 0), "standard_bike", 8
        )
        assert result.duration_discount == 0.80  # 20% off

    def test_24hr_discount(self, engine):
        result = engine.calculate_price(
            datetime(2025, 5, 15, 9, 0), "standard_bike", 24
        )
        assert result.duration_discount == 0.70  # 30% off

    def test_short_duration_no_discount(self, engine):
        result = engine.calculate_price(
            datetime(2025, 5, 15, 9, 0), "standard_bike", 2
        )
        assert result.duration_discount == 1.0  # No discount


# ──────────────────────────────────────────────
# Input Validation
# ──────────────────────────────────────────────

class TestInputValidation:
    """Invalid inputs should raise clear errors."""

    def test_invalid_vehicle_type(self, engine):
        with pytest.raises(ValueError, match="Invalid vehicle type"):
            engine.calculate_price(
                datetime(2025, 5, 15, 9, 0), "flying_car", 8
            )

    def test_zero_duration(self, engine):
        with pytest.raises(ValueError, match="Duration"):
            engine.calculate_price(
                datetime(2025, 5, 15, 9, 0), "standard_bike", 0
            )

    def test_negative_duration(self, engine):
        with pytest.raises(ValueError, match="Duration"):
            engine.calculate_price(
                datetime(2025, 5, 15, 9, 0), "standard_bike", -5
            )


# ──────────────────────────────────────────────
# Warnings
# ──────────────────────────────────────────────

class TestWarnings:
    """Edge cases should produce appropriate warnings."""

    def test_past_date_historical_note(self, engine):
        """Past date should show historical reference note."""
        result = engine.calculate_price(
            datetime(2020, 1, 1, 9, 0),  # Far in the past
            "standard_bike", 8
        )
        assert any("historical reference" in w.lower() for w in result.warnings)

    def test_far_future_weekday_low_confidence(self, engine):
        """Regular weekday >90 days out should get low confidence warning."""
        result = engine.calculate_price(
            datetime(2030, 3, 6, 9, 0),  # Far future Wednesday
            "standard_bike", 8
        )
        assert any("lower" in w.lower() or "uncertain" in w.lower() for w in result.warnings)

    def test_far_future_holiday_high_confidence(self, engine):
        """Known holiday >90 days out should get HIGH confidence."""
        result = engine.calculate_price(
            datetime(2026, 10, 9, 9, 0),  # Diwali 2026 (>90 days from Feb 2026)
            "standard_bike", 8
        )
        assert any("high confidence" in w.lower() or "calendar-certain" in w.lower() for w in result.warnings), \
            f"Expected high confidence for Diwali 2026. Got: {result.warnings}"

    def test_far_future_weekend_medium_confidence(self, engine):
        """Weekend >90 days out should get medium confidence."""
        result = engine.calculate_price(
            datetime(2030, 3, 9, 9, 0),  # Far future Saturday
            "standard_bike", 8
        )
        assert any("medium" in w.lower() for w in result.warnings), \
            f"Expected medium confidence for far weekend. Got: {result.warnings}"


# ──────────────────────────────────────────────
# Explanation
# ──────────────────────────────────────────────

class TestExplanation:
    """Pricing result should always include explanation steps."""

    def test_explanation_has_steps(self, engine):
        result = engine.calculate_price(
            datetime(2025, 5, 15, 9, 0), "standard_bike", 8
        )
        assert len(result.explanation) >= 5  # At least 5 explanation steps

    def test_explanation_mentions_vehicle(self, engine):
        result = engine.calculate_price(
            datetime(2025, 5, 15, 9, 0), "premium_bike", 8
        )
        assert any("Premium" in step for step in result.explanation)

    def test_explanation_shows_auto_detected(self, engine):
        """When overrides are detected, explanation should mention auto-detection."""
        result = engine.calculate_price(
            datetime(2025, 10, 20, 9, 0),  # Diwali
            "standard_bike", 8
        )
        assert any("auto-detected" in step.lower() or "Auto-detected" in step for step in result.explanation)
