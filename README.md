# 🏍️ Dynamic Pricing Engine — Self-Drive Bike Rental

A **rule-based, data-driven** dynamic pricing engine for self-drive bike rentals (Royal Brothers model). Adjusts rental prices based on expected demand at the rental time, not booking time.

## Architecture

```
📊 Synthetic Dataset (2yrs, 287K bookings)
        ↓
📈 Demand Analyzer (compute baselines per hour/day/season/day-type)
        ↓
📋 Demand Profiles (demand_profiles.json)
        ↓
⚡ Pricing Engine (score → surge multiplier → price)
        ↓
💰 Final Price + Step-by-step Explanation
```

## Quick Start

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Generate data & profiles (one-time)
python3 data/generate_dataset.py
python3 data/analyze_demand.py

# Run server
python3 -m app.main

# Open dashboard
open http://localhost:5000
```

## Features

- **4 vehicle types**: Scooter (₹60/hr) → Super Premium (₹250/hr)
- **Data-derived demand profiles**: Not hardcoded — analyzed from 287K synthetic bookings
- **Smart day classification**: Long weekends, bridge days, holiday eves
- **5 demand zones**: Dead 🔵 → Low 🟢 → Normal ⚪ → High 🟡 → Surge 🔴
- **Contextual overrides**: Rain (discount), Festivals (surge), Events, Heatwave
- **Duration discounts**: 4+hrs → 10% off, 8+hrs → 20% off, 24+hrs → 30% off
- **Edge cases**: Zero-demand floor, override stacking cap, input validation, advance booking warnings
- **Full explainability**: Step-by-step pricing breakdown for every calculation

## Testing

```bash
python3 -m pytest tests/ -v   # 46 tests
```

## Tech Stack

- **Backend**: Python, FastAPI, Pydantic
- **Data**: Pandas, NumPy (synthetic data + analysis)
- **Frontend**: Vanilla HTML/CSS/JS, dark theme, glassmorphism
