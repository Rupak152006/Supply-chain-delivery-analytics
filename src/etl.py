"""Extract the raw Delhivery checkpoint file, clean it, aggregate to trip legs
and load a SQLite star schema.

Raw grain: one row per checkpoint ("cutoff") on a trip leg, with cumulative
actual and OSRM times. Fact grain: one row per leg (trip + source -> destination).

Run:  python src/etl.py
Output: data/processed/delivery.db and reports/data_quality_report.csv
"""
import re
import sqlite3
import numpy as np
import pandas as pd
from config import DB, PROC, RAW_FILE, REPORTS, ROOT, SLA_FACTOR

NAME_RE = re.compile(r"^(?P<place>.*?)\s*\((?P<state>[^()]*)\)\s*$")
HUB_CODES = {"HB", "H", "HUB", "MOTHERHUB"}
DELIVERY_CODES = {"D", "DC", "DPC", "DPP", "PC"}
BANDS = [0, 25, 50, 100, 250, 500, np.inf]
BAND_LABELS = ["<25 km", "25-50 km", "50-100 km", "100-250 km", "250-500 km", "500+ km"]


def parse_facility(name):
    """'Anand_VUNagar_DC (Gujarat)' -> ('Anand', 'Gujarat', 'DC', 'Delivery centre')."""
    if not isinstance(name, str):
        return "Unknown", "Unknown", "", "Unknown"
    m = NAME_RE.match(name.strip())
    place, state = (m.group("place"), m.group("state").strip()) if m else (name.strip(), "Unknown")
    parts = [p for p in re.split(r"[_\s]+", place) if p]
    city = parts[0].title() if parts else "Unknown"
    code = parts[-1].upper() if len(parts) > 1 else ""
    ftype = "Hub" if code in HUB_CODES else "Delivery centre" if code in DELIVERY_CODES else "Other"
    return city, state, code, ftype


def transform(raw):
    dq = []
    log = lambda check, n, action: dq.append({"check": check, "rows_affected": int(n), "action": action})

    df = raw.copy()
    log("raw checkpoint rows", len(df), "loaded")
    n0 = len(df); df = df.drop_duplicates()
    log("exact duplicate checkpoint rows", n0 - len(df), "dropped")

    for c in ["trip_creation_time", "od_start_time", "od_end_time", "cutoff_timestamp"]:
        df[c] = pd.to_datetime(df[c], format="mixed", errors="coerce")
    log("unparseable timestamps", df[["trip_creation_time", "od_start_time", "od_end_time"]].isna().any(axis=1).sum(),
        "rows dropped")
    df = df.dropna(subset=["trip_creation_time", "od_start_time", "od_end_time"])

    # Fill missing facility names from other rows that share the centre code
    for side in ["source", "destination"]:
        miss = df[f"{side}_name"].isna()
        lookup = pd.concat([df[["source_center", "source_name"]].set_axis(["c", "n"], axis=1),
                            df[["destination_center", "destination_name"]].set_axis(["c", "n"], axis=1)]
                           ).dropna().drop_duplicates("c").set_index("c")["n"]
        df.loc[miss, f"{side}_name"] = df.loc[miss, f"{side}_center"].map(lookup)
        still = df[f"{side}_name"].isna()
        log(f"missing {side}_name", miss.sum(), f"filled {int(miss.sum() - still.sum())} from centre code, rest 'Unknown'")

    bad = (df.actual_time <= 0) | (df.osrm_time <= 0) | (df.osrm_distance <= 0)
    log("non-positive time or distance", bad.sum(), "dropped")
    df = df[~bad]

    # ---- aggregate checkpoints to legs (cumulative fields -> max) ----
    keys = ["trip_uuid", "source_center", "destination_center"]
    leg = (df.sort_values("cutoff_timestamp").groupby(keys).agg(
        route_schedule_uuid=("route_schedule_uuid", "first"), route_type=("route_type", "first"),
        source_name=("source_name", "first"), destination_name=("destination_name", "first"),
        trip_created_at=("trip_creation_time", "first"), leg_start_at=("od_start_time", "first"),
        leg_end_at=("od_end_time", "first"), scan_to_scan_min=("start_scan_to_end_scan", "first"),
        actual_time_min=("actual_time", "max"), osrm_time_min=("osrm_time", "max"),
        osrm_distance_km=("osrm_distance", "max"), actual_distance_km=("actual_distance_to_destination", "max"),
        checkpoints=("cutoff_timestamp", "size")).reset_index())
    log("legs built (trip + source -> destination)", len(leg), "aggregated")

    neg = leg.leg_end_at < leg.leg_start_at
    log("legs ending before they start", neg.sum(), "dropped")
    leg = leg[~neg].copy()

    leg["handling_min"] = (leg.scan_to_scan_min - leg.actual_time_min).clip(lower=0)
    clipped = (leg.scan_to_scan_min < leg.actual_time_min).sum()
    log("scan-to-scan shorter than transit time", clipped, "handling time set to 0")
    leg["delay_ratio"] = leg.actual_time_min / leg.osrm_time_min
    leg["excess_min"] = leg.actual_time_min - leg.osrm_time_min
    leg["meets_sla"] = (leg.delay_ratio <= SLA_FACTOR).astype(int)
    log("legs over 10x the OSRM estimate", (leg.delay_ratio > 10).sum(), "kept; medians used in reporting")
    leg["distance_band"] = pd.cut(leg.osrm_distance_km, BANDS, labels=BAND_LABELS, right=False).astype(str)
    leg["start_hour"] = leg.leg_start_at.dt.hour
    leg["leg_id"] = leg.trip_uuid + "|" + leg.source_center + "|" + leg.destination_center
    return leg, pd.DataFrame(dq)


def build_dims(leg):
    fac = pd.concat([leg[["source_center", "source_name"]].set_axis(["center_code", "facility_name"], axis=1),
                     leg[["destination_center", "destination_name"]].set_axis(["center_code", "facility_name"], axis=1)])
    fac = fac.sort_values("facility_name", na_position="last").drop_duplicates("center_code").reset_index(drop=True)
    fac["facility_name"] = fac.facility_name.fillna("Unknown")
    parsed = fac.facility_name.map(parse_facility)
    fac[["city", "state", "facility_code", "facility_type"]] = pd.DataFrame(parsed.tolist(), index=fac.index)
    fac.insert(0, "facility_key", range(1, len(fac) + 1))

    routes = leg[["route_schedule_uuid", "route_type"]].drop_duplicates("route_schedule_uuid").reset_index(drop=True)
    routes.insert(0, "route_key", range(1, len(routes) + 1))

    days = pd.date_range(leg.trip_created_at.min().normalize(), leg.leg_end_at.max().normalize(), freq="D")
    dd = pd.DataFrame({"date_key": days.strftime("%Y%m%d").astype(int), "full_date": days.strftime("%Y-%m-%d"),
                       "day_of_week": days.dayofweek + 1, "day_name": days.day_name(),
                       "is_weekend": (days.dayofweek >= 5).astype(int),
                       "week_start": (days - pd.to_timedelta(days.dayofweek, "D")).strftime("%Y-%m-%d")})
    return fac, routes, dd


def load(leg, fac, routes, dd, dq):
    PROC.mkdir(parents=True, exist_ok=True); REPORTS.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript((ROOT / "sql" / "schema.sql").read_text())
    key = fac.set_index("center_code").facility_key
    state = fac.set_index("center_code").state
    fact = pd.DataFrame({
        "leg_id": leg.leg_id, "trip_uuid": leg.trip_uuid,
        "route_key": leg.route_schedule_uuid.map(routes.set_index("route_schedule_uuid").route_key),
        "source_key": leg.source_center.map(key), "destination_key": leg.destination_center.map(key),
        "trip_date_key": leg.trip_created_at.dt.strftime("%Y%m%d").astype(int),
        "route_type": leg.route_type,
        "trip_created_at": leg.trip_created_at.dt.strftime("%Y-%m-%d %H:%M:%S"),
        "leg_start_at": leg.leg_start_at.dt.strftime("%Y-%m-%d %H:%M:%S"),
        "leg_end_at": leg.leg_end_at.dt.strftime("%Y-%m-%d %H:%M:%S"),
        "start_hour": leg.start_hour,
        "is_interstate": (leg.source_center.map(state) != leg.destination_center.map(state)).astype(int),
        "checkpoints": leg.checkpoints, "scan_to_scan_min": leg.scan_to_scan_min,
        "actual_time_min": leg.actual_time_min, "osrm_time_min": leg.osrm_time_min,
        "osrm_distance_km": leg.osrm_distance_km.round(2), "actual_distance_km": leg.actual_distance_km.round(2),
        "handling_min": leg.handling_min, "delay_ratio": leg.delay_ratio.round(4),
        "excess_min": leg.excess_min, "meets_sla": leg.meets_sla, "distance_band": leg.distance_band,
    })
    dd.to_sql("dim_date", con, if_exists="append", index=False)
    fac.to_sql("dim_facility", con, if_exists="append", index=False)
    routes.to_sql("dim_route", con, if_exists="append", index=False)
    fact.to_sql("fact_leg", con, if_exists="append", index=False)
    con.executescript((ROOT / "sql" / "kpi_views.sql").read_text())
    con.commit(); con.close()
    dq.to_csv(REPORTS / "data_quality_report.csv", index=False)
    print(dq.to_string(index=False))
    print(f"\nloaded {len(fact):,} legs, {len(fac):,} facilities, {len(routes):,} routes into {DB}")


def main():
    raw = pd.read_csv(RAW_FILE)
    leg, dq = transform(raw)
    fac, routes, dd = build_dims(leg)
    load(leg, fac, routes, dd, dq)


if __name__ == "__main__":
    main()
