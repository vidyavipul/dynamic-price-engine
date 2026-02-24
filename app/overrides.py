"""
Contextual Overrides for pricing.

Override factors that layer on top of the demand-based multiplier.
Rain discounts rentals (unlike ride-hailing). Events/holidays increase them.
"""

from enum import Enum
from typing import Dict, List
from app.config import MAX_OVERRIDE_FACTOR


class OverrideType(str, Enum):
    LONG_WEEKEND = "long_weekend"
    FESTIVAL = "festival"
    RAIN = "rain"
    HEAVY_RAIN = "heavy_rain"
    MAJOR_EVENT = "major_event"
    HEATWAVE = "heatwave"


# Override multiplier definitions
OVERRIDE_FACTORS: Dict[OverrideType, float] = {
    OverrideType.LONG_WEEKEND: 1.50,   # Peak rental demand
    OverrideType.FESTIVAL: 1.40,       # Dussehra, Diwali travel
    OverrideType.RAIN: 0.80,           # DISCOUNT — discourages rentals
    OverrideType.HEAVY_RAIN: 0.65,     # Bigger DISCOUNT
    OverrideType.MAJOR_EVENT: 1.30,    # Concerts, sports events
    OverrideType.HEATWAVE: 0.90,       # Slightly reduced demand
}

OVERRIDE_DESCRIPTIONS: Dict[OverrideType, str] = {
    OverrideType.LONG_WEEKEND: "Long Weekend (3-4 day stretch)",
    OverrideType.FESTIVAL: "Festival / Public Holiday",
    OverrideType.RAIN: "Rain (reduces rental demand)",
    OverrideType.HEAVY_RAIN: "Heavy Rain / Storm Warning",
    OverrideType.MAJOR_EVENT: "Major Event (concert, match, rally)",
    OverrideType.HEATWAVE: "Heatwave Advisory",
}


def compute_combined_override(active_overrides: List[str]) -> tuple:
    """
    Compute the combined override factor from a list of active overrides.

    Overrides stack multiplicatively but are capped at MAX_OVERRIDE_FACTOR.

    Returns:
        (combined_factor, breakdown_list)
        - combined_factor: float, the final combined multiplier
        - breakdown_list: list of dicts with override name, factor, description
    """
    combined = 1.0
    breakdown = []

    for override_name in active_overrides:
        try:
            override = OverrideType(override_name)
        except ValueError:
            continue  # Skip unknown overrides

        factor = OVERRIDE_FACTORS[override]
        combined *= factor
        breakdown.append({
            "override": override.value,
            "factor": factor,
            "description": OVERRIDE_DESCRIPTIONS[override],
            "effect": "discount" if factor < 1.0 else "surge",
        })

    # Cap the combined factor
    was_capped = False
    if combined > MAX_OVERRIDE_FACTOR:
        was_capped = True
        combined = MAX_OVERRIDE_FACTOR
    elif combined < (1.0 / MAX_OVERRIDE_FACTOR):
        was_capped = True
        combined = 1.0 / MAX_OVERRIDE_FACTOR

    return combined, breakdown, was_capped
