"""
Demand Analyzer — Derives demand profiles from booking history.

Reads the synthetic dataset (or real data) and computes normalized
demand profiles per dimension: hourly, day-of-week, monthly, day-type.
Outputs demand_profiles.json used by the pricing engine.
"""

import csv
import json
import os
from collections import defaultdict
from datetime import datetime
from typing import Dict, List


def load_bookings(csv_path: str) -> List[Dict]:
    """Load bookings from CSV file."""
    bookings = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["duration_hours"] = int(row["duration_hours"])
            row["base_price_per_hr"] = float(row["base_price_per_hr"])
            row["is_holiday"] = row["is_holiday"] == "True"
            row["is_weekend"] = row["is_weekend"] == "True"
            row["rental_start_dt"] = datetime.strptime(row["rental_start"], "%Y-%m-%dT%H:%M:%S")
            bookings.append(row)
    return bookings


def normalize_profile(profile: Dict[str, int]) -> Dict[str, float]:
    """Normalize counts to [0, 1] range where max = 1.0."""
    if not profile:
        return {}
    max_val = max(profile.values())
    if max_val == 0:
        return {k: 0.0 for k in profile}
    return {k: round(v / max_val, 4) for k, v in profile.items()}


def compute_profiles(bookings: List[Dict]) -> Dict:
    """
    Compute demand profiles from booking data.

    Returns normalized profiles for:
    - hourly: demand by hour of day (0-23)
    - day_of_week: demand by weekday (0=Mon to 6=Sun)
    - monthly: demand by month (1-12)
    - day_type: demand by classification (regular_weekday, saturday, etc.)
    """
    hourly_counts = defaultdict(int)
    dow_counts = defaultdict(int)
    monthly_counts = defaultdict(int)
    day_type_counts = defaultdict(int)

    # Count days per category to get average bookings per day (not total)
    hourly_day_count = defaultdict(set)       # hour -> set of dates
    dow_day_count = defaultdict(set)          # dow -> set of dates
    monthly_day_count = defaultdict(set)      # month -> set of dates
    day_type_day_count = defaultdict(set)     # day_type -> set of dates

    for b in bookings:
        dt = b["rental_start_dt"]
        d = dt.date()
        hour = dt.hour
        dow = dt.weekday()
        month = dt.month
        day_type = b["day_type"]

        hourly_counts[str(hour)] += 1
        hourly_day_count[str(hour)].add(d)

        dow_counts[str(dow)] += 1
        dow_day_count[str(dow)].add(d)

        monthly_counts[str(month)] += 1
        monthly_day_count[str(month)].add(d)

        day_type_counts[day_type] += 1
        day_type_day_count[day_type].add(d)

    # Compute average bookings per day for each category
    def avg_per_day(counts, day_counts):
        result = {}
        for k in counts:
            num_days = len(day_counts[k])
            result[k] = counts[k] / num_days if num_days > 0 else 0
        return result

    hourly_avg = avg_per_day(hourly_counts, hourly_day_count)
    dow_avg = avg_per_day(dow_counts, dow_day_count)
    monthly_avg = avg_per_day(monthly_counts, monthly_day_count)
    day_type_avg = avg_per_day(day_type_counts, day_type_day_count)

    # Normalize each to [0, 1]
    profiles = {
        "hourly": normalize_profile(hourly_avg),
        "day_of_week": normalize_profile(dow_avg),
        "monthly": normalize_profile(monthly_avg),
        "day_type": normalize_profile(day_type_avg),
    }

    # Compute baseline statistics
    total_days = len({b["rental_start_dt"].date() for b in bookings})
    baseline_daily = len(bookings) / total_days if total_days > 0 else 0

    profiles["stats"] = {
        "total_bookings": len(bookings),
        "total_days": total_days,
        "baseline_daily_bookings": round(baseline_daily, 2),
        "date_range": {
            "start": min(b["rental_start"] for b in bookings),
            "end": max(b["rental_start"] for b in bookings),
        }
    }

    return profiles


def analyze_and_save(csv_path: str = None, output_path: str = None) -> str:
    """
    Main entry point: load bookings, compute profiles, save JSON.
    Returns the output file path.
    """
    data_dir = os.path.dirname(__file__)

    if csv_path is None:
        csv_path = os.path.join(data_dir, "bookings.csv")

    if output_path is None:
        output_path = os.path.join(data_dir, "demand_profiles.json")

    print(f"Loading bookings from {csv_path}...")
    bookings = load_bookings(csv_path)
    print(f"  Loaded {len(bookings):,} bookings")

    print("Computing demand profiles...")
    profiles = compute_profiles(bookings)

    with open(output_path, "w") as f:
        json.dump(profiles, f, indent=2)

    print(f"✅ Demand profiles saved → {output_path}")
    print(f"\n📊 Profile Summary:")
    print(f"   Baseline daily bookings: {profiles['stats']['baseline_daily_bookings']}")
    print(f"   Date range: {profiles['stats']['date_range']['start'][:10]} → {profiles['stats']['date_range']['end'][:10]}")

    # Print day-type ranking
    print(f"\n📈 Day-Type Demand Ranking (normalized):")
    day_types = profiles["day_type"]
    for dt_name, score in sorted(day_types.items(), key=lambda x: x[1], reverse=True):
        bar = "█" * int(score * 30)
        print(f"   {dt_name:20s} {score:.3f} {bar}")

    return output_path


if __name__ == "__main__":
    analyze_and_save()
