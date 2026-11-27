-- Star schema for Delhivery line-haul legs (SQLite)
DROP TABLE IF EXISTS fact_leg;
DROP TABLE IF EXISTS fact_checkpoint;
DROP TABLE IF EXISTS dim_facility;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_route;

CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY, full_date TEXT, day_of_week INTEGER, day_name TEXT,
    is_weekend INTEGER, week_start TEXT
);
CREATE TABLE dim_facility (
    facility_key INTEGER PRIMARY KEY, center_code TEXT UNIQUE, facility_name TEXT,
    city TEXT, state TEXT, facility_code TEXT, facility_type TEXT
);
CREATE TABLE dim_route (
    route_key INTEGER PRIMARY KEY, route_schedule_uuid TEXT UNIQUE, route_type TEXT
);

-- One row per trip leg (trip_uuid + source -> destination)
CREATE TABLE fact_leg (
    leg_id               TEXT PRIMARY KEY,
    trip_uuid            TEXT NOT NULL,
    route_key            INTEGER REFERENCES dim_route(route_key),
    source_key           INTEGER REFERENCES dim_facility(facility_key),
    destination_key      INTEGER REFERENCES dim_facility(facility_key),
    trip_date_key        INTEGER REFERENCES dim_date(date_key),
    route_type           TEXT,
    trip_created_at      TEXT,
    leg_start_at         TEXT,
    leg_end_at           TEXT,
    start_hour           INTEGER,
    is_interstate        INTEGER,
    checkpoints          INTEGER,
    scan_to_scan_min     REAL,   -- start scan to end scan (total leg time)
    actual_time_min      REAL,   -- actual transit time
    osrm_time_min        REAL,   -- routing-engine estimate
    osrm_distance_km     REAL,
    actual_distance_km   REAL,
    handling_min         REAL,   -- scan-to-scan minus transit: time at facilities
    delay_ratio          REAL,   -- actual / OSRM time
    excess_min           REAL,   -- actual - OSRM time
    meets_sla            INTEGER,
    distance_band        TEXT
);
CREATE INDEX ix_leg_date ON fact_leg(trip_date_key);
CREATE INDEX ix_leg_src ON fact_leg(source_key);
CREATE INDEX ix_leg_dst ON fact_leg(destination_key);
