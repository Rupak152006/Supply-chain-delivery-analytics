"""Export KPI views to CSV marts for the BI layer, adding medians SQLite lacks."""
import sqlite3
import pandas as pd
from config import DB, MARTS, MIN_LEGS_RANKED, SLA_FACTOR


def medians(con, by, cols=("delay_ratio",)):
    df = pd.read_sql(f"SELECT {', '.join(by)}, {', '.join(cols)} FROM vw_leg", con)
    out = df.groupby(list(by))[list(cols)].median().round(3)
    return out.rename(columns={c: f"median_{c}" for c in cols}).reset_index()


def main():
    MARTS.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    q = lambda sql: pd.read_sql(sql, con)
    marts = {
        "daily": q("SELECT * FROM mart_daily ORDER BY date").merge(
            medians(con, ["trip_date"]).rename(columns={"trip_date": "date"}), on="date"),
        "route_type": q("SELECT * FROM mart_route_type").merge(
            medians(con, ["route_type"], ("delay_ratio", "actual_time_min", "osrm_time_min")), on="route_type"),
        "distance_band": q("SELECT * FROM mart_distance_band").merge(
            medians(con, ["distance_band", "route_type"]), on=["distance_band", "route_type"]),
        "hour": q("SELECT * FROM mart_hour ORDER BY hour"),
        "day_of_week": q("SELECT * FROM mart_day_of_week ORDER BY day_of_week"),
        "state": q(f"SELECT * FROM mart_state WHERE legs >= {MIN_LEGS_RANKED} ORDER BY legs DESC"),
        "corridor": q(f"SELECT * FROM mart_corridor WHERE legs >= {MIN_LEGS_RANKED} ORDER BY legs DESC"),
        "hub": q(f"SELECT * FROM mart_hub WHERE legs >= {MIN_LEGS_RANKED} ORDER BY legs DESC"),
    }
    band_order = ["<25 km", "25-50 km", "50-100 km", "100-250 km", "250-500 km", "500+ km"]
    marts["distance_band"]["band_order"] = marts["distance_band"].distance_band.map(band_order.index)
    marts["distance_band"] = marts["distance_band"].sort_values(["band_order", "route_type"])
    overall = q(f"""SELECT COUNT(*) AS legs, COUNT(DISTINCT trip_uuid) AS trips,
        (SELECT COUNT(*) FROM dim_facility) AS facilities, ROUND(AVG(meets_sla), 4) AS sla_rate,
        ROUND(AVG(is_interstate), 4) AS interstate_share, ROUND(AVG(route_type='FTL'), 4) AS ftl_share,
        ROUND(SUM(osrm_distance_km), 0) AS planned_km, ROUND(AVG(handling_min), 1) AS avg_handling_min,
        MIN(trip_date) AS first_date, MAX(trip_date) AS last_date, {SLA_FACTOR} AS sla_factor FROM vw_leg""")
    overall["median_delay_ratio"] = round(q("SELECT delay_ratio FROM vw_leg").delay_ratio.median(), 3)
    marts["overall"] = overall
    for name, df in marts.items():
        df.to_csv(MARTS / f"{name}.csv", index=False)
        print(f"{name:15s} {len(df):5d} rows")
    con.close()


if __name__ == "__main__":
    main()
