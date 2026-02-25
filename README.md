# Dynamic Pricing Engine — Complete Solution Guide

A from-scratch explanation of every file, module, function, class, and variable.

---

## 🏗️ Project Structure

```
dynamic-price-engine/
│
├── data/                     ← DATA PIPELINE (offline, run once)
│   ├── generate_dataset.py   ← Step 1: Creates synthetic bookings CSV
│   ├── analyze_demand.py     ← Step 2: Derives demand profiles from CSV
│   ├── duckdb_analyzer.py    ← Step 2b: DuckDB analytics (reporting only)
│   ├── bookings.csv          ← Generated: 287K bookings (gitignored)
│   ├── demand_profiles.json  ← Generated: v1 profiles (used by pricing)
│   └── demand_profiles_duckdb.json ← Generated: DuckDB profiles (reporting)
│
├── app/                      ← RUNTIME ENGINE (runs on every API call)
│   ├── config.py             ← All constants, tunable parameters
│   ├── demand_model.py       ← Scores any datetime → demand 0-1
│   ├── demand_model_v2.py    ← DuckDB-based scorer (kept for reference)
│   ├── overrides.py          ← Auto-detects holidays, rain, festivals
│   ├── price_engine.py       ← Orchestrates everything → final ₹ price
│   └── main.py               ← FastAPI server, routes, endpoints
│
├── static/                   ← FRONTEND
│   ├── index.html            ← Pricing dashboard UI
│   ├── analytics.html        ← DuckDB analytics reporting page
│   ├── app.js                ← Frontend JavaScript logic
│   └── style.css             ← All styling
│
├── tests/                    ← TEST SUITE (78 tests)
│   ├── test_demand_model.py  ← 21 tests for demand scoring
│   ├── test_price_engine.py  ← 36 tests for pricing + overrides + guards
│   └── test_duckdb_analyzer.py ← 21 tests for DuckDB profiles
│
└── requirements.txt          ← Dependencies
```

---

## 📊 The Data Pipeline (Offline, Run Once)

The pipeline has 2 steps: **Generate** → **Analyze**. You run these once to create the data files that the pricing engine uses at runtime.

---

### Step 1: [generate_dataset.py](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/generate_dataset.py)

**Purpose**: Creates a realistic synthetic dataset of bike rental bookings (287K rows, ~2 years).

**How to run**: `python3 data/generate_dataset.py`
**Output**: [data/bookings.csv](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/bookings.csv)

#### Key Constants

| Variable | Value | What it does |
|---|---|---|
| `LOCATIONS` | 10 Bangalore areas | Pickup spots (Koramangala, Indiranagar, etc.) |
| `WEATHER_BY_SEASON` | dict of dicts | Probability of each weather per season. Example: monsoon has 55% rain, 20% heavy rain |

#### Key Functions

**[get_season(d)](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/generate_dataset.py#57-68)** → [str](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#227-235)
Maps a date to a season. Uses Indian climate:
- Summer: Mar-May
- Monsoon: Jun-Sep
- Winter: Nov-Feb
- Festive: Oct (separate because Oct has Diwali/Dussehra)

**[classify_day(d)](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/generate_dataset.py#72-110)** → [str](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#227-235)
The **most important function in the entire project**. Classifies any date into one of 10 demand categories:

| Day Type | Demand | Logic |
|---|---|---|
| [long_weekend](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#194-224) | 🔴 Highest | 3+ consecutive off days (e.g., Sat-Sun-Mon holiday) |
| [holiday](file:///Users/vidya/Documents/Projects/dynamic-price-engine/tests/test_duckdb_analyzer.py#231-239) | 🟡 High | Date is in `INDIAN_HOLIDAYS` |
| `bridge_strong` | 🟡 High | 1 leave day creates 4-day weekend (Tue holiday → Mon bridge) |
| `holiday_eve` | 🟡 Moderate | Day before a holiday |
| [saturday](file:///Users/vidya/Documents/Projects/dynamic-price-engine/tests/test_duckdb_analyzer.py#153-159) | 🟢 Above-avg | Saturday |
| [sunday](file:///Users/vidya/Documents/Projects/dynamic-price-engine/tests/test_demand_model.py#66-70) | 🟢 Above-avg | Sunday (slightly less than Sat — people return bikes) |
| [friday](file:///Users/vidya/Documents/Projects/dynamic-price-engine/tests/test_price_engine.py#201-210) | ⚪ Normal+ | Fridays (evening pickup demand) |
| `bridge_weak` | ⚪ Normal | Needs 2 days leave to connect to weekend |
| [regular_weekday](file:///Users/vidya/Documents/Projects/dynamic-price-engine/tests/test_duckdb_analyzer.py#126-130) | 🔵 Lowest | Mon-Thu, no special event |

**[_is_long_weekend_day(d)](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#194-224)** → `bool`
Checks if a date is part of a 3+ day off stretch. Looks at holidays near weekends:
- Monday holiday → Sat+Sun+Mon = 3-day weekend ✓
- Friday holiday → Fri+Sat+Sun = 3-day weekend ✓
- Tuesday holiday → Mon(bridge)+Tue+Sat+Sun = 4-day stretch ✓

**[_is_strong_bridge(d)](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#227-235)** / **[_is_weak_bridge(d)](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/generate_dataset.py#186-200)** → `bool`
Bridge days are workdays between a holiday and weekend that people take off:
- **Strong**: Only 1 leave needed (Tuesday holiday → Monday is strong bridge)
- **Weak**: 2 leaves needed (Wednesday holiday → Mon+Tue could be weak bridges)

**[generate_day_bookings(d, counter)](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/generate_dataset.py#254-324)** → `list`
Generates all bookings for a single day. The number of bookings is controlled by:

```python
day_type = classify_day(d)
multiplier = DAY_TYPE_MULTIPLIERS[day_type]  # e.g., long_weekend = 3.5×
base_bookings = random.gauss(25, 5)          # ~25 ± 5 per day
num_bookings = base_bookings * multiplier     # long_weekend → ~87 bookings
```

Each booking gets: booking_id, rental_start, duration, vehicle_type, location, weather, day_type, is_holiday, is_weekend, base_price.

**[generate_dataset()](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/generate_dataset.py#330-365)** → [str](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#227-235)
Main entry: iterates every day from 2024-01-01 to 2025-12-31, calls [generate_day_bookings()](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/generate_dataset.py#254-324) for each, writes all rows to CSV.

---

### Step 2: [analyze_demand.py](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/analyze_demand.py)

**Purpose**: Reads `bookings.csv` and computes normalized demand profiles.

**How to run**: `python3 data/analyze_demand.py`
**Output**: [data/demand_profiles.json](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/demand_profiles.json)

#### Key Functions

**[load_bookings(csv_path)](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/analyze_demand.py#17-30)** → `list[dict]`
Reads CSV, parses types (int, float, bool, datetime).

**[normalize_profile(profile)](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/analyze_demand.py#32-40)** → `dict`
Takes raw counts like `{"saturday": 450, "regular_weekday": 180}` and normalizes to [0, 1] where the max becomes 1.0:
```
long_weekend: 1.00, holiday: 0.71, saturday: 0.56, regular_weekday: 0.23
```

**[compute_profiles(bookings)](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/analyze_demand.py#42-138)** → `dict`
The core function. Computes **average bookings per day** (not total) for 5 dimensions:

| Profile | Keys | Example |
|---|---|---|
| [hourly](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#158-162) | "0" to "23" | 8AM = 1.0, 3AM = 0.04 |
| `day_of_week` | "0" (Mon) to "6" (Sun) | Sat(6) = 1.0, Wed(2) = 0.38 |
| [monthly](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#153-157) | "1" (Jan) to "12" (Dec) | Oct = 1.0, Jul = 0.18 |
| [day_type](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#148-152) | 10 categories | long_weekend = 1.0, regular_weekday = 0.21 |
| `weather_by_month` | month → weather% | Jul: {rain: 0.55, clear: 0.25, ...} |

> **Why average per day, not total?** If there are 100 Saturdays but only 2 Diwali days in the data, total counts would be unfair. Average-per-day ensures Diwali's ~150 bookings/day correctly ranks above Saturday's ~80/day.

**[analyze_and_save()](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/analyze_demand.py#140-176)**
Orchestrates: load → compute → save JSON → print summary.

---

### Step 2b: [duckdb_analyzer.py](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/duckdb_analyzer.py)

**Purpose**: Uses DuckDB (embedded SQL database) for richer analysis. **Used for reporting only, NOT for pricing.**

**Output**: [data/demand_profiles_duckdb.json](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/demand_profiles_duckdb.json)

What it adds beyond v1:
- **Cross-dimensional matrices**: [hour_by_dow](file:///Users/vidya/Documents/Projects/dynamic-price-engine/tests/test_duckdb_analyzer.py#139-143) (168 cells: 24hrs × 7days), `dow_by_month`, `hour_by_day_type`
- **Weather impact**: demand ratio vs clear-day baseline (rain = 0.35×)
- **Top demand slots**: ranked by (day_type × hour × month)
- **Demand volatility**: standard deviation per hour

---

## ⚙️ The Runtime Engine (Runs on Every API Call)

When someone hits "Calculate Price", these modules execute in sequence:

```
Request → main.py → DemandModel.estimate_demand() → OverrideDetector.detect_overrides() → PriceEngine.calculate_price() → Response
```

---

### [config.py](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/config.py)

**Purpose**: Single source of truth for ALL tunable parameters.

#### Vehicle Configuration

```python
class VehicleType(str, Enum):      # 4 vehicle categories
    SCOOTER = "scooter"            # ₹60/hr (Activa, Jupiter)
    STANDARD_BIKE = "standard_bike" # ₹80/hr (Pulsar, FZ)
    PREMIUM_BIKE = "premium_bike"   # ₹150/hr (RE Classic, Dominar)
    SUPER_PREMIUM = "super_premium" # ₹250/hr (Himalayan, KTM 390)
```

#### Pricing Parameters

| Variable | Value | What it does |
|---|---|---|
| `MIN_MULTIPLIER` | 0.70 | Floor: worst case = 30% discount |
| `MAX_MULTIPLIER` | 2.00 | Ceiling: max = 2× surge |
| `BASELINE_DEMAND` | 0.50 | A score of 0.50 → ~1.0× multiplier |
| `MAX_OVERRIDE_FACTOR` | 2.00 | Combined overrides can't exceed 2× |

#### Absolute Price Guards (₹ per hour)

Prevents pricing below operational cost (floor) or overcharging customers (ceiling):

| Vehicle | Base | Floor (~65%) | Ceiling (~250%) |
|---|---|---|---|
| Scooter | ₹60 | ₹40 | ₹150 |
| Standard Bike | ₹80 | ₹50 | ₹200 |
| Premium Bike | ₹150 | ₹100 | ₹375 |
| Super Premium | ₹250 | ₹160 | ₹625 |

> These are the **last safety net** — applied after all multipliers and discounts. Even if demand is dead AND 24hr discount stacks, the rate never drops below the floor.

#### Demand Signal Weights

```python
WEIGHT_DAY_TYPE  = 0.45  # 45% — strongest signal
WEIGHT_SEASON    = 0.30  # 30% — seasonal patterns
WEIGHT_TIME_SLOT = 0.25  # 25% — time of day
```

These MUST sum to 1.0. Day type gets the most weight because it's the best predictor of demand (long_weekend vs regular_weekday is a 5× difference).

#### Duration Discounts

```python
DURATION_DISCOUNT_TIERS = [
    (24, 0.70),  # 24+ hours → 30% off
    (8,  0.80),  # 8+ hours  → 20% off
    (4,  0.90),  # 4+ hours  → 10% off
]
```
Checked top-down, first match wins. Incentivizes longer rentals.

#### Holiday Calendar

`INDIAN_HOLIDAYS`: dict mapping `date → name` for 2024-2026. Covers Republic Day, Holi, Eid, Diwali, Christmas, etc. Used by both [DemandModel](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#73-274) and [OverrideDetector](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/overrides.py#43-189).

#### Confidence Threshold

`LOW_CONFIDENCE_DAYS = 90` — Bookings >90 days ahead get a confidence warning (unless it's a known holiday or weekend).

---

### [demand_model.py](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py)

**Purpose**: Given any datetime, produce a demand score from 0.0 (dead) to 1.0 (peak surge).

#### Classes

**[DemandZone](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#24-31)** — Classifies scores into 5 zones:

| Range | Zone | Color | Meaning |
|---|---|---|---|
| 0.00–0.15 | Dead 🔵 | Blue | Near-zero demand, deep discount |
| 0.15–0.35 | Low 🟢 | Green | Below normal, discount pricing |
| 0.35–0.55 | Normal ⚪ | Gray | Baseline, standard pricing |
| 0.55–0.75 | High 🟡 | Yellow | Above normal, mild surge |
| 0.75–1.00 | Surge 🔴 | Red | Peak demand, full surge |

**[DemandResult](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#57-71)** — Returned by [estimate_demand()](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#99-145). Contains:
- [score](file:///Users/vidya/Documents/Projects/dynamic-price-engine/tests/test_duckdb_analyzer.py#177-187): blended 0-1 score
- [zone](file:///Users/vidya/Documents/Projects/dynamic-price-engine/tests/test_demand_model.py#152-155): which DemandZone it falls in
- [day_type](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#148-152), [day_type_score](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#148-152): e.g., "saturday", 0.59
- `season_score`: e.g., 1.0 for October
- `time_slot_score`: e.g., 1.0 for 8 AM
- `is_holiday`, `holiday_name`: e.g., True, "Diwali"

**[DemandModel](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#73-274)** — The scoring engine.

**[__init__(profiles_path)](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#82-98)**: Loads [demand_profiles.json](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/demand_profiles.json) at startup. If file missing, uses hardcoded fallback profiles.

**[estimate_demand(rental_datetime)](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#99-145)** → [DemandResult](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#57-71):
The core scoring method. Does 4 things:

```python
# 1. Classify the day
day_type = self._classify_day(d)           # → "saturday"

# 2. Look up each dimension's score from profiles
day_type_score  = profiles["day_type"]["saturday"]    # → 0.59
season_score    = profiles["monthly"]["10"]           # → 1.00 (October)
time_slot_score = profiles["hourly"]["9"]             # → 0.89 (9 AM)

# 3. Weighted blend
score = 0.45 × 0.59 + 0.30 × 1.00 + 0.25 × 0.89     # → 0.788

# 4. Classify into zone
zone = classify_demand_zone(0.788)                     # → Surge 🔴
```

**[_classify_day(d)](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model_v2.py#171-199)**: Same logic as [classify_day()](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/generate_dataset.py#72-110) in generate_dataset.py — checks holidays, long weekends, bridges, etc.

**[_get_day_type_score(day_type)](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#148-152)**, **[_get_monthly_score(month)](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#153-157)**, **[_get_hourly_score(hour)](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#158-162)**: Simple lookups into the loaded profiles dict.

**[_fallback_profiles()](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#246-277)**: Returns hardcoded profiles if [demand_profiles.json](file:///Users/vidya/Documents/Projects/dynamic-price-engine/data/demand_profiles.json) doesn't exist (useful for first run before data pipeline).

---

### [overrides.py](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/overrides.py)

**Purpose**: Auto-detects contextual factors that should modify the price beyond normal demand scoring.

> **Key difference from demand_model**: DemandModel scores *inherent* demand patterns. OverrideDetector catches *special circumstances* that need extra adjustment.

#### [DetectedOverride](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/overrides.py#20-28) dataclass
Each detected override has:
- `name`: "Festival: Diwali", "Rain Likely", etc.
- `factor`: multiplier (1.40 = 40% surge, 0.85 = 15% discount)
- `reason`: human-readable explanation
- [confidence](file:///Users/vidya/Documents/Projects/dynamic-price-engine/tests/test_price_engine.py#191-200): "high", "medium", or "low"
- `effect`: "surge" or "discount"

#### `OVERRIDE_FACTORS` dict

```python
{
    "long_weekend":    1.50,  # 50% surge
    "festival":        1.40,  # 40% surge
    "holiday":         1.30,  # 30% surge
    "holiday_eve":     1.15,  # 15% surge
    "friday_evening":  1.20,  # 20% surge
    "rain_likely":     0.85,  # 15% discount
    "heavy_rain_likely": 0.70, # 30% discount
    "heatwave_likely": 0.90,  # 10% discount
}
```

#### [OverrideDetector](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/overrides.py#43-189) class

**[__init__(profiles_path)](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#82-98)**: Loads `weather_by_month` from profiles to get historical rain/heat probabilities per month.

**[detect_overrides(rental_datetime, day_type)](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/overrides.py#66-189)** → [(factor, overrides, was_capped)](file:///Users/vidya/Documents/Projects/dynamic-price-engine/tests/test_demand_model.py#15-19)

Checks 5 things in order:

1. **Long weekend**: if `day_type == "long_weekend"` → 1.50× surge
2. **Festival/Holiday**: checks `INDIAN_HOLIDAYS` dict. Festivals (Diwali, Holi, Eid) get 1.40×, regular holidays get 1.30×
3. **Holiday eve**: day before a holiday → 1.15× surge
4. **Friday evening**: Friday after 5 PM → 1.20× surge (weekend getaway pickups)
5. **Weather**: checks historical probabilities for that month:
   - Heavy rain >15% → 0.70× discount
   - Rain >25% → 0.85× discount
   - Hot >20% → 0.90× discount

All factors are **multiplied together** (stacked), then capped at `MAX_OVERRIDE_FACTOR` (2.0×).

Example: Diwali on a long weekend in October = 1.50 × 1.40 = 2.10 → capped to 2.00×.

---

### [price_engine.py](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/price_engine.py)

**Purpose**: The orchestrator. Takes a request, runs demand scoring + overrides, and returns the final ₹ price.

#### [PriceResult](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/price_engine.py#23-54) dataclass
The complete response containing:
- `final_price`: the ₹ amount
- `hourly_rate`, `effective_hourly_rate`: before/after surge
- [demand](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/demand_model.py#99-145): dict with score, zone, day_type, etc.
- `surge_multiplier`, `override_factor`, `final_multiplier`
- `duration_discount`: 0.70-1.00
- `overrides_detected`: list of detected overrides
- `warnings`: smart confidence messages
- [explanation](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/price_engine.py#244-319): step-by-step pricing breakdown (12+ steps)

#### `PriceEngine.calculate_price(rental_datetime, vehicle_type, duration_hours)` → [PriceResult](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/price_engine.py#23-54)

The **main function**. Executes 7 steps:

```
Step 1: Demand Score
  DemandModel.estimate_demand(datetime) → score=0.788, zone=Surge 🔴

Step 2: Base Surge Multiplier
  surge = 0.70 + 0.788 × (2.00 - 0.70) = 1.72×

Step 3: Auto-Detect Overrides
  OverrideDetector.detect_overrides() → factor=1.40 (festival detected)

Step 4: Final Multiplier (clamped)
  raw = 1.72 × 1.40 = 2.41 → clamped to 2.00×

Step 5: Duration Discount
  8 hours → 0.80 (20% off)

Step 6: Compute Effective Rate
  base_rate = ₹80/hr (Standard Bike)
  effective = ₹80 × 2.00 × 0.80 = ₹128/hr

Step 7: Price Floor/Ceiling Guard 🛡️
  ₹128 is within [₹50 floor, ₹200 ceiling] ✓
  total = ₹128 × 8 = ₹1,024
```

#### Smart Confidence (in Step 0: Validation)

For dates >90 days ahead:
- **Known holiday** (in `INDIAN_HOLIDAYS`) → ✅ "calendar-certain, high confidence"
- **Weekend** (Sat/Sun) → 📅 "medium confidence — weekends are predictable"
- **Regular weekday** → ⚠️ "low confidence — weather and events uncertain"
- **Past date** → 📅 "Price shown for historical reference only"

---

### [main.py](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/main.py)

**Purpose**: FastAPI server — connects everything to HTTP endpoints.

#### Initialization (runs once at startup)

```python
demand_model = DemandModel()       # Loads demand_profiles.json
price_engine = PriceEngine(demand_model)  # Creates engine with model
_duckdb_profiles = json.load(...)  # Loads DuckDB profiles for analytics API
```

#### API Endpoints

| Method | Route | What it does |
|---|---|---|
| GET | `/` | Serves [index.html](file:///Users/vidya/Documents/Projects/dynamic-price-engine/static/index.html) (pricing dashboard) |
| GET | `/analytics` | Serves [analytics.html](file:///Users/vidya/Documents/Projects/dynamic-price-engine/static/analytics.html) (reporting page) |
| GET | `/api/vehicles` | Returns vehicle types + base rates |
| GET | `/api/analytics` | Returns DuckDB profiles JSON |
| POST | `/api/price` | **Main endpoint**: parses request → calls `price_engine.calculate_price()` → returns PriceResult |

#### [PriceRequest](file:///Users/vidya/Documents/Projects/dynamic-price-engine/app/main.py#50-66) model (Pydantic)
```python
{
    "rental_datetime": "2025-10-18T09:00:00",  # ISO format
    "vehicle_type": "standard_bike",
    "duration_hours": 8
}
```

---

## 🎨 The Frontend

### [index.html](file:///Users/vidya/Documents/Projects/dynamic-price-engine/static/index.html)
Dashboard with: vehicle selector grid, datetime picker, duration dropdown, calculate button, and results section (price hero card, stats row, demand gauge, overrides card, explanation steps, warnings).

### [app.js](file:///Users/vidya/Documents/Projects/dynamic-price-engine/static/app.js)
- [setDefaultDatetime()](file:///Users/vidya/Documents/Projects/dynamic-price-engine/static/app.js#26-37): Sets next Saturday 9 AM as default
- [loadVehicles()](file:///Users/vidya/Documents/Projects/dynamic-price-engine/static/app.js#38-54): Fetches vehicle data from API
- [calculatePrice()](file:///Users/vidya/Documents/Projects/dynamic-price-engine/static/app.js#78-116): POST to `/api/price`, renders results
- [renderResults()](file:///Users/vidya/Documents/Projects/dynamic-price-engine/static/app.js#119-212): Updates all result sections from API response

### [analytics.html](file:///Users/vidya/Documents/Projects/dynamic-price-engine/static/analytics.html)
Reporting page with 5 sections:
1. **Stats summary**: total bookings, days, avg/day, date range
2. **Weather Impact**: demand ratio per weather type vs clear baseline
3. **Day Type Ranking**: horizontal bars from long_weekend→regular_weekday
4. **Seasonal Monthly Trends**: bar chart with season labels
5. **Demand Volatility**: mean ± std dev per hour
6. **Hour×Day Heatmap**: 7×24 grid, hover for values

---

## 🧪 Tests (78 total)

| File | Count | What it covers |
|---|---|---|
| [test_demand_model.py](file:///Users/vidya/Documents/Projects/dynamic-price-engine/tests/test_demand_model.py) | 21 | Score bounds [0,1], weekend > weekday, seasonal patterns, long weekend detection, bridge days, demand zones, holiday detection, time patterns |
| [test_price_engine.py](file:///Users/vidya/Documents/Projects/dynamic-price-engine/tests/test_price_engine.py) | 36 | Basic pricing, demand-based pricing, multiplier bounds, auto-detected overrides, duration discounts, input validation, smart confidence, price floor/ceiling guards |
| [test_duckdb_analyzer.py](file:///Users/vidya/Documents/Projects/dynamic-price-engine/tests/test_duckdb_analyzer.py) | 21 | DuckDB profile structure, v1↔DuckDB consistency, cross-dimensional values, DemandModelV2 scoring, v2 engine integration |

---

## 🔄 Complete Request Flow

```
User clicks "Calculate" for Standard Bike, Sat Oct 18 2025, 8 hours

1. Frontend POST → /api/price
     { rental_datetime: "2025-10-18T09:00:00", vehicle_type: "standard_bike", duration_hours: 8 }

2. main.py parses request, calls price_engine.calculate_price()

3. PriceEngine Step 1: DemandModel.estimate_demand()
     _classify_day(Oct 18) → "saturday"
     day_type_score = profiles["day_type"]["saturday"] = 0.59
     season_score = profiles["monthly"]["10"] = 1.00  (October = festive peak)
     time_slot_score = profiles["hourly"]["9"] = 0.89  (9 AM = morning rush)
     score = 0.45×0.59 + 0.30×1.00 + 0.25×0.89 = 0.788
     zone = Surge 🔴

4. PriceEngine Step 2: Surge multiplier
     surge = 0.70 + 0.788 × 1.30 = 1.72×

5. PriceEngine Step 3: OverrideDetector.detect_overrides()
     Saturday in October, not a holiday, no long weekend
     Month 10 weather: hot=0%, rain=0%, clear=100% → no weather override
     No overrides detected → factor = 1.00

6. PriceEngine Step 4: Final multiplier
     raw = 1.72 × 1.00 = 1.72 (within bounds 0.70–2.00) ✓

7. PriceEngine Step 5: Duration discount
     8 hours ≥ 8 → 0.80 (20% off)

8. PriceEngine Step 6+7: Price with floor/ceiling guard
     effective_hourly = ₹80 × 1.72 × 0.80 = ₹110.08
     🛡️ Check: ₹110.08 within [₹50 floor, ₹200 ceiling] ✓
     total = ₹110.08 × 8 = ₹880.64

9. Response → Frontend renders result
```

---

## 📸 Screenshots

### System Architecture
![Architecture Diagram](docs/screenshots/architecture.png)

### Pricing Dashboard
![Dashboard](docs/screenshots/dashboard.png)

### Pricing Results
![Pricing Results](docs/screenshots/pricing-results.png)

### Analytics Page
![Analytics](docs/screenshots/analytics.png)
