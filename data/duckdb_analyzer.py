"""
DuckDB-Powered Demand Analyzer — Cross-Dimensional Profiles.

Alternative to analyze_demand.py (pandas-based). Uses DuckDB's SQL
engine for richer analysis including cross-dimensional demand profiles.

Same input:  data/bookings.csv
Output:      data/demand_profiles_duckdb.json
"""

import json
import os
from typing import Dict

import duckdb


def analyze_with_duckdb(csv_path: str = None, output_path: str = None) -> str:
    """
    Analyze booking data using DuckDB SQL queries.

    Produces all profiles from the original analyzer PLUS:
    - hour_by_dow: 7×24 cross-dimensional demand matrix
    - dow_by_month: 7×12 cross-dimensional demand matrix
    - hour_by_day_type: demand per hour per day classification
    - weather_impact: demand shift per weather type vs clear baseline
    - top_demand_slots: highest-demand combinations ranked
    - demand_volatility: std deviation per time slot
    """
    data_dir = os.path.dirname(__file__)
    if csv_path is None:
        csv_path = os.path.join(data_dir, "bookings.csv")
    if output_path is None:
        output_path = os.path.join(data_dir, "demand_profiles_duckdb.json")

    print(f"Loading bookings from {csv_path} via DuckDB...")

    con = duckdb.connect(":memory:")

    # ── Load CSV into DuckDB ──
    con.execute(f"""
        CREATE TABLE bookings AS
        SELECT *,
            CAST(rental_start AS TIMESTAMP) AS ts,
            CAST(rental_start AS DATE) AS d,
            EXTRACT(HOUR FROM CAST(rental_start AS TIMESTAMP)) AS hour,
            EXTRACT(DOW FROM CAST(rental_start AS TIMESTAMP)) AS dow,
            EXTRACT(MONTH FROM CAST(rental_start AS TIMESTAMP)) AS month
        FROM read_csv_auto('{csv_path}')
    """)

    total = con.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    total_days = con.execute("SELECT COUNT(DISTINCT d) FROM bookings").fetchone()[0]
    print(f"  Loaded {total:,} bookings across {total_days} days")

    profiles = {}

    # ══════════════════════════════════════════════
    # 1. SINGLE-DIMENSION PROFILES (matching original)
    # ══════════════════════════════════════════════

    # ── Hourly profile ──
    profiles["hourly"] = _normalized_query(con, """
        SELECT CAST(hour AS INT) AS key,
               COUNT(*) * 1.0 / COUNT(DISTINCT d) AS avg_bookings
        FROM bookings GROUP BY hour ORDER BY hour
    """)

    # ── Day of week profile ──
    profiles["day_of_week"] = _normalized_query(con, """
        SELECT CAST(dow AS INT) AS key,
               COUNT(*) * 1.0 / COUNT(DISTINCT d) AS avg_bookings
        FROM bookings GROUP BY dow ORDER BY dow
    """)

    # ── Monthly profile ──
    profiles["monthly"] = _normalized_query(con, """
        SELECT CAST(month AS INT) AS key,
               COUNT(*) * 1.0 / COUNT(DISTINCT d) AS avg_bookings
        FROM bookings GROUP BY month ORDER BY month
    """)

    # ── Day type profile ──
    profiles["day_type"] = _normalized_query(con, """
        SELECT day_type AS key,
               COUNT(*) * 1.0 / COUNT(DISTINCT d) AS avg_bookings
        FROM bookings GROUP BY day_type ORDER BY avg_bookings DESC
    """)

    # ── Weather by month ──
    profiles["weather_by_month"] = {}
    weather_rows = con.execute("""
        SELECT CAST(month AS INT) AS m, weather,
               COUNT(*) * 1.0 / SUM(COUNT(*)) OVER (PARTITION BY month) AS prob
        FROM bookings GROUP BY month, weather ORDER BY month, prob DESC
    """).fetchall()
    for m, weather, prob in weather_rows:
        m_str = str(m)
        if m_str not in profiles["weather_by_month"]:
            profiles["weather_by_month"][m_str] = {}
        profiles["weather_by_month"][m_str][weather] = round(prob, 4)

    # ══════════════════════════════════════════════
    # 2. CROSS-DIMENSIONAL PROFILES (DuckDB advantage)
    # ══════════════════════════════════════════════

    # ── Hour × Day-of-Week matrix ──
    # "Friday 6 PM" gets its own score, different from "Tuesday 6 PM"
    profiles["hour_by_dow"] = _cross_dim_query(con, """
        SELECT CAST(dow AS INT) AS dim1,
               CAST(hour AS INT) AS dim2,
               COUNT(*) * 1.0 / COUNT(DISTINCT d) AS avg_bookings
        FROM bookings GROUP BY dow, hour ORDER BY dow, hour
    """)

    # ── Day-of-Week × Month matrix ──
    # "Saturday in October" vs "Saturday in July"
    profiles["dow_by_month"] = _cross_dim_query(con, """
        SELECT CAST(dow AS INT) AS dim1,
               CAST(month AS INT) AS dim2,
               COUNT(*) * 1.0 / COUNT(DISTINCT d) AS avg_bookings
        FROM bookings GROUP BY dow, month ORDER BY dow, month
    """)

    # ── Hour × Day-Type matrix ──
    # "9 AM on a long_weekend" vs "9 AM on a regular_weekday"
    profiles["hour_by_day_type"] = _cross_dim_query(con, """
        SELECT day_type AS dim1,
               CAST(hour AS INT) AS dim2,
               COUNT(*) * 1.0 / COUNT(DISTINCT d) AS avg_bookings
        FROM bookings GROUP BY day_type, hour ORDER BY day_type, hour
    """)

    # ══════════════════════════════════════════════
    # 3. WEATHER IMPACT ANALYSIS
    # ══════════════════════════════════════════════

    # How much does each weather type shift demand vs clear-day baseline?
    weather_impact = con.execute("""
        WITH daily_counts AS (
            SELECT d, weather,
                   COUNT(*) AS bookings
            FROM bookings GROUP BY d, weather
        ),
        weather_avg AS (
            SELECT weather,
                   AVG(bookings) AS avg_bookings,
                   STDDEV(bookings) AS std_bookings,
                   COUNT(*) AS num_days
            FROM daily_counts GROUP BY weather
        ),
        baseline AS (
            SELECT avg_bookings FROM weather_avg WHERE weather = 'clear'
        )
        SELECT w.weather,
               ROUND(w.avg_bookings, 1) AS avg_daily,
               ROUND(w.avg_bookings / b.avg_bookings, 4) AS vs_baseline,
               ROUND(w.std_bookings, 1) AS std_dev,
               w.num_days
        FROM weather_avg w CROSS JOIN baseline b
        ORDER BY w.avg_bookings DESC
    """).fetchall()

    profiles["weather_impact"] = {
        row[0]: {
            "avg_daily_bookings": row[1],
            "ratio_vs_clear": row[2],
            "std_dev": row[3],
            "num_days": row[4],
        }
        for row in weather_impact
    }

    # ══════════════════════════════════════════════
    # 4. TOP DEMAND SLOTS
    # ══════════════════════════════════════════════

    top_slots = con.execute("""
        SELECT day_type, CAST(hour AS INT) AS hour,
               CAST(month AS INT) AS month,
               COUNT(*) * 1.0 / COUNT(DISTINCT d) AS avg_bookings
        FROM bookings
        GROUP BY day_type, hour, month
        ORDER BY avg_bookings DESC
        LIMIT 20
    """).fetchall()

    profiles["top_demand_slots"] = [
        {
            "day_type": row[0],
            "hour": row[1],
            "month": row[2],
            "avg_bookings": round(row[3], 2),
        }
        for row in top_slots
    ]

    # ══════════════════════════════════════════════
    # 5. DEMAND VOLATILITY (std dev per hour slot)
    # ══════════════════════════════════════════════

    volatility = con.execute("""
        WITH hourly_daily AS (
            SELECT d, CAST(hour AS INT) AS hour, COUNT(*) AS bookings
            FROM bookings GROUP BY d, hour
        )
        SELECT hour,
               ROUND(AVG(bookings), 2) AS mean,
               ROUND(STDDEV(bookings), 2) AS std_dev,
               ROUND(STDDEV(bookings) / NULLIF(AVG(bookings), 0), 4) AS cv
        FROM hourly_daily GROUP BY hour ORDER BY hour
    """).fetchall()

    profiles["demand_volatility"] = {
        str(row[0]): {
            "mean": row[1],
            "std_dev": row[2],
            "coefficient_of_variation": row[3],
        }
        for row in volatility
    }

    # ── Stats ──
    date_range = con.execute(
        "SELECT MIN(rental_start), MAX(rental_start) FROM bookings"
    ).fetchone()

    profiles["stats"] = {
        "total_bookings": total,
        "total_days": total_days,
        "baseline_daily_bookings": round(total / total_days, 2),
        "analyzer": "duckdb",
        "date_range": {
            "start": str(date_range[0])[:10],
            "end": str(date_range[1])[:10],
        },
    }

    con.close()

    # ── Save ──
    with open(output_path, "w") as f:
        json.dump(profiles, f, indent=2)

    print(f"✅ DuckDB profiles saved → {output_path}")
    print(f"\n📊 Profile Summary:")
    print(f"   Baseline daily bookings: {profiles['stats']['baseline_daily_bookings']}")
    print(f"   Date range: {profiles['stats']['date_range']['start']} → {profiles['stats']['date_range']['end']}")
    print(f"   Cross-dimensional matrices: hour×dow, dow×month, hour×day_type")

    # Print top 10 demand slots
    print(f"\n🔥 Top 10 Demand Slots (day_type × hour × month):")
    for i, slot in enumerate(profiles["top_demand_slots"][:10], 1):
        print(f"   {i:2d}. {slot['day_type']:16s} @ {slot['hour']:02d}:00, month {slot['month']:2d}  → {slot['avg_bookings']:.1f} avg bookings")

    # Print weather impact
    print(f"\n🌦️ Weather Impact (vs clear-day baseline):")
    for weather, data in sorted(profiles["weather_impact"].items(),
                                 key=lambda x: x[1]["ratio_vs_clear"], reverse=True):
        ratio = data["ratio_vs_clear"]
        direction = "↑" if ratio > 1.0 else "↓" if ratio < 1.0 else "="
        print(f"   {weather:12s} {direction} {ratio:.2f}× baseline ({data['avg_daily_bookings']:.0f} avg/day, {data['num_days']} days)")

    return output_path


def _normalized_query(con, sql: str) -> Dict[str, float]:
    """Run a query and normalize results to [0, 1]."""
    rows = con.execute(sql).fetchall()
    if not rows:
        return {}
    max_val = max(r[1] for r in rows)
    if max_val == 0:
        return {str(r[0]): 0.0 for r in rows}
    return {str(r[0]): round(r[1] / max_val, 4) for r in rows}


def _cross_dim_query(con, sql: str) -> Dict[str, Dict[str, float]]:
    """
    Run a 2D cross-dimensional query and normalize to [0, 1].
    Returns: { dim1: { dim2: score } }
    """
    rows = con.execute(sql).fetchall()
    if not rows:
        return {}
    max_val = max(r[2] for r in rows)
    if max_val == 0:
        return {}

    result = {}
    for dim1, dim2, val in rows:
        d1 = str(dim1)
        d2 = str(dim2)
        if d1 not in result:
            result[d1] = {}
        result[d1][d2] = round(val / max_val, 4)
    return result


if __name__ == "__main__":
    analyze_with_duckdb()
