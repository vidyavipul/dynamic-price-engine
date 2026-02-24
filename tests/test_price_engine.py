"""
Tests for the Price Engine.

Validates pricing calculations, edge cases, multiplier bounds,
override stacking, duration discounts, and input validation.
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
        """Late night monsoon weekday should have multiplier < 1.0 (discount)."""
        result = engine.calculate_price(
            datetime(2025, 7, 15, 3, 0),  # Tuesday 3AM July
            "standard_bike", 4
        )
        base_price = VEHICLE_BASE_RATES[VehicleType.STANDARD_BIKE] * 4
        assert result.final_price < base_price, \
            f"Low demand price ({result.final_price}) should be < base ({base_price})"

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
        # Worst case scenario
        result = engine.calculate_price(
            datetime(2025, 7, 15, 3, 0),  # Tue 3AM monsoon
            "scooter", 1,
            active_overrides=["rain", "heavy_rain"],
        )
        assert result.final_multiplier >= MIN_MULTIPLIER

    def test_multiplier_never_above_max(self, engine):
        # Best case with all surge overrides
        result = engine.calculate_price(
            datetime(2025, 10, 18, 9, 0),  # Sat morning festive
            "super_premium", 8,
            active_overrides=["long_weekend", "festival", "major_event"],
        )
        assert result.final_multiplier <= MAX_MULTIPLIER

    def test_zero_demand_floor(self, engine):
        """Even in worst case, price should never be ₹0."""
        result = engine.calculate_price(
            datetime(2025, 7, 15, 3, 0),
            "scooter", 1,
            active_overrides=["rain", "heavy_rain"],
        )
        assert result.final_price > 0
        min_expected = VEHICLE_BASE_RATES[VehicleType.SCOOTER] * MIN_MULTIPLIER * 1
        assert result.final_price >= min_expected * 0.99  # Allow tiny float drift


# ──────────────────────────────────────────────
# Override Effects
# ──────────────────────────────────────────────

class TestOverrideEffects:
    """Overrides should correctly adjust price."""

    def test_rain_decreases_price(self, engine):
        """Rain should be a discount for bike rentals."""
        no_rain = engine.calculate_price(
            datetime(2025, 5, 15, 9, 0), "standard_bike", 8
        )
        with_rain = engine.calculate_price(
            datetime(2025, 5, 15, 9, 0), "standard_bike", 8,
            active_overrides=["rain"],
        )
        assert with_rain.final_price < no_rain.final_price, \
            f"Rain price ({with_rain.final_price}) should be < no rain ({no_rain.final_price})"

    def test_festival_increases_price(self, engine):
        no_festival = engine.calculate_price(
            datetime(2025, 5, 15, 9, 0), "standard_bike", 8
        )
        with_festival = engine.calculate_price(
            datetime(2025, 5, 15, 9, 0), "standard_bike", 8,
            active_overrides=["festival"],
        )
        assert with_festival.final_price > no_festival.final_price

    def test_conflicting_overrides_both_apply(self, engine):
        """Rain + Festival should both apply multiplicatively."""
        result = engine.calculate_price(
            datetime(2025, 5, 15, 9, 0), "standard_bike", 8,
            active_overrides=["rain", "festival"],
        )
        assert len(result.overrides_applied) == 2

    def test_override_stacking_cap(self, engine):
        """Multiple surge overrides should be capped."""
        result = engine.calculate_price(
            datetime(2025, 10, 18, 9, 0), "standard_bike", 8,
            active_overrides=["long_weekend", "festival", "major_event"],
        )
        # Combined override: 1.5 × 1.4 × 1.3 = 2.73 → should be capped at 2.0
        assert result.override_factor <= 2.0

    def test_unknown_override_ignored(self, engine):
        """Unknown overrides should be silently ignored."""
        result = engine.calculate_price(
            datetime(2025, 5, 15, 9, 0), "standard_bike", 8,
            active_overrides=["unknown_override"],
        )
        assert result.override_factor == 1.0  # No effect


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

    def test_past_date_warning(self, engine):
        result = engine.calculate_price(
            datetime(2020, 1, 1, 9, 0),  # Far in the past
            "standard_bike", 8
        )
        assert any("past" in w.lower() for w in result.warnings)

    def test_far_future_warning(self, engine):
        result = engine.calculate_price(
            datetime(2030, 1, 1, 9, 0),  # Far in the future
            "standard_bike", 8
        )
        assert any("confidence" in w.lower() for w in result.warnings)


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
