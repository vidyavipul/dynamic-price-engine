"""
Price Engine — Computes dynamic rental price.

Maps demand score → surge multiplier, auto-detects overrides from data,
clamps to bounds, applies duration discounts, returns full breakdown.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Optional, Dict

from app.config import (
    VEHICLE_BASE_RATES, VEHICLE_DISPLAY_NAMES, VehicleType,
    MIN_MULTIPLIER, MAX_MULTIPLIER,
    DURATION_DISCOUNT_TIERS, LOW_CONFIDENCE_DAYS,
    INDIAN_HOLIDAYS,
)
from app.demand_model import DemandModel, DemandResult
from app.overrides import OverrideDetector


@dataclass
class PriceResult:
    """Complete pricing result with full breakdown."""
    # Final output
    final_price: float
    hourly_rate: float
    effective_hourly_rate: float

    # Inputs
    vehicle_type: str
    vehicle_name: str
    base_rate: float
    duration_hours: int
    rental_datetime: str

    # Demand
    demand: Dict

    # Multipliers
    surge_multiplier: float
    override_factor: float
    final_multiplier: float
    duration_discount: float

    # Auto-detected overrides
    overrides_detected: List[Dict]
    override_was_capped: bool
    warnings: List[str] = field(default_factory=list)

    # Explanation steps
    explanation: List[str] = field(default_factory=list)


class PriceEngine:
    """
    Dynamic pricing engine for bike rentals.

    Overrides are auto-detected from:
    - Holiday calendar (festivals, public holidays)
    - Day classification (long weekends, bridge days)
    - Weather probabilities from historical data
    """

    def __init__(self, demand_model: Optional[DemandModel] = None,
                 override_detector: Optional[OverrideDetector] = None):
        self.demand_model = demand_model or DemandModel()
        self.override_detector = override_detector or OverrideDetector()

    def calculate_price(
        self,
        rental_datetime: datetime,
        vehicle_type: str,
        duration_hours: int,
    ) -> PriceResult:
        """
        Calculate the dynamic price for a rental.

        Overrides are auto-detected internally — no manual input needed.

        Args:
            rental_datetime: When the rental starts
            vehicle_type: Vehicle category (scooter, standard_bike, etc.)
            duration_hours: Rental duration in hours

        Returns:
            PriceResult with full breakdown

        Raises:
            ValueError: If vehicle_type or duration is invalid
        """
        # ── Input validation ──
        warnings = []

        try:
            v_type = VehicleType(vehicle_type)
        except ValueError:
            valid = [v.value for v in VehicleType]
            raise ValueError(
                f"Invalid vehicle type '{vehicle_type}'. "
                f"Valid types: {valid}"
            )

        if not isinstance(duration_hours, int) or duration_hours < 1:
            raise ValueError(
                f"Duration must be a positive integer (got {duration_hours}). "
                f"Minimum rental: 1 hour."
            )

        # Check for past dates (allowed for historical reference)
        now = datetime.now()
        if rental_datetime < now:
            warnings.append(
                f"📅 This date is in the past ({rental_datetime.strftime('%Y-%m-%d %H:%M')}). "
                f"Price shown for historical reference only."
            )

        # Smart confidence for far-future dates
        days_ahead = (rental_datetime.date() - now.date()).days
        if days_ahead > LOW_CONFIDENCE_DAYS:
            d = rental_datetime.date()
            is_holiday = d in INDIAN_HOLIDAYS
            is_weekend = d.weekday() >= 5  # Saturday or Sunday

            if is_holiday:
                holiday_name = INDIAN_HOLIDAYS[d]
                warnings.append(
                    f"✅ Booking is {days_ahead} days ahead but {holiday_name} is "
                    f"calendar-certain — high confidence pricing."
                )
            elif is_weekend:
                warnings.append(
                    f"📅 Booking is {days_ahead} days ahead (>{LOW_CONFIDENCE_DAYS} days). "
                    f"Weekend demand is predictable but seasonal factors may vary — "
                    f"medium confidence."
                )
            else:
                warnings.append(
                    f"⚠️ Booking is {days_ahead} days ahead (>{LOW_CONFIDENCE_DAYS} days). "
                    f"Demand prediction confidence is lower for distant weekdays — "
                    f"weather and local events are uncertain."
                )

        # ── Step 1: Demand estimation ──
        demand_result = self.demand_model.estimate_demand(rental_datetime)

        # ── Step 2: Base surge multiplier from demand ──
        surge_multiplier = MIN_MULTIPLIER + demand_result.score * (MAX_MULTIPLIER - MIN_MULTIPLIER)

        # ── Step 3: Auto-detect overrides ──
        override_factor, detected_overrides, override_capped = (
            self.override_detector.detect_overrides(rental_datetime, demand_result.day_type)
        )

        # ── Step 4: Final multiplier (clamped) ──
        raw_multiplier = surge_multiplier * override_factor
        final_multiplier = max(MIN_MULTIPLIER, min(MAX_MULTIPLIER, raw_multiplier))

        # ── Step 5: Duration discount ──
        duration_discount = 1.0
        for threshold, discount in DURATION_DISCOUNT_TIERS:
            if duration_hours >= threshold:
                duration_discount = discount
                break

        # ── Step 6: Compute price ──
        base_rate = VEHICLE_BASE_RATES[v_type]
        effective_hourly = base_rate * final_multiplier * duration_discount
        total_price = effective_hourly * duration_hours

        # ── Build explanation ──
        explanation = self._build_explanation(
            v_type, base_rate, duration_hours, demand_result,
            surge_multiplier, override_factor, detected_overrides,
            override_capped, final_multiplier, duration_discount,
            effective_hourly, total_price
        )

        # ── Build demand dict ──
        demand_dict = {
            "score": demand_result.score,
            "zone": demand_result.zone.name,
            "zone_color": demand_result.zone.color,
            "zone_emoji": demand_result.zone.emoji,
            "zone_description": demand_result.zone.description,
            "day_type": demand_result.day_type,
            "day_type_score": demand_result.day_type_score,
            "season_score": demand_result.season_score,
            "time_slot_score": demand_result.time_slot_score,
            "is_holiday": demand_result.is_holiday,
            "holiday_name": demand_result.holiday_name,
        }

        # ── Build override dicts ──
        override_dicts = [
            {
                "name": o.name,
                "factor": o.factor,
                "reason": o.reason,
                "confidence": o.confidence,
                "effect": o.effect,
            }
            for o in detected_overrides
        ]

        return PriceResult(
            final_price=round(total_price, 2),
            hourly_rate=base_rate,
            effective_hourly_rate=round(effective_hourly, 2),
            vehicle_type=v_type.value,
            vehicle_name=VEHICLE_DISPLAY_NAMES[v_type],
            base_rate=base_rate,
            duration_hours=duration_hours,
            rental_datetime=rental_datetime.strftime("%Y-%m-%dT%H:%M:%S"),
            demand=demand_dict,
            surge_multiplier=round(surge_multiplier, 4),
            override_factor=round(override_factor, 4),
            final_multiplier=round(final_multiplier, 4),
            duration_discount=duration_discount,
            overrides_detected=override_dicts,
            override_was_capped=override_capped,
            warnings=warnings,
            explanation=explanation,
        )

    def _build_explanation(
        self, v_type, base_rate, duration, demand, surge,
        override_factor, detected_overrides, override_capped,
        final_mult, duration_discount, effective_hourly, total
    ) -> List[str]:
        """Build step-by-step human-readable pricing explanation."""
        steps = []
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        steps.append(f"🏍️ Vehicle: {VEHICLE_DISPLAY_NAMES[v_type]} — Base rate: ₹{base_rate}/hr")

        # Demand breakdown
        day_label = demand.day_type.replace("_", " ").title()
        steps.append(
            f"📅 Day type: {day_label} ({weekdays[demand.weekday]}) — "
            f"score: {demand.day_type_score:.2f}"
        )

        months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        steps.append(
            f"🌤️ Season ({months[demand.month]}): score {demand.season_score:.2f}"
        )

        steps.append(
            f"🕐 Time slot ({demand.hour:02d}:00): score {demand.time_slot_score:.2f}"
        )

        if demand.is_holiday and demand.holiday_name:
            steps.append(f"🎉 Holiday: {demand.holiday_name}")

        steps.append(
            f"📊 Blended demand score: {demand.score:.2f} → "
            f"{demand.zone.emoji} {demand.zone.name} zone"
        )

        steps.append(f"📈 Surge multiplier: {surge:.2f}×")

        # Auto-detected overrides
        if detected_overrides:
            steps.append(f"🔍 Auto-detected {len(detected_overrides)} override(s):")
            for o in detected_overrides:
                direction = "↓" if o.effect == "discount" else "↑"
                conf_badge = {"high": "●", "medium": "◐", "low": "○"}[o.confidence]
                steps.append(
                    f"  {direction} {o.name}: ×{o.factor:.2f} "
                    f"[{conf_badge} {o.confidence}] — {o.reason}"
                )
            if override_capped:
                steps.append(f"  ⚠️ Combined override capped at ×{override_factor:.2f}")
        else:
            steps.append("🔍 No contextual overrides detected for this date")

        steps.append(f"🔒 Final multiplier: {final_mult:.2f}× (bounds: {MIN_MULTIPLIER}–{MAX_MULTIPLIER})")

        if duration_discount < 1.0:
            discount_pct = int((1 - duration_discount) * 100)
            steps.append(f"⏱️ Duration discount ({duration}hrs): {discount_pct}% off")

        steps.append(f"💰 Effective rate: ₹{effective_hourly:.2f}/hr × {duration}hrs = ₹{total:.2f}")

        return steps
