-- KPI semantic layer for Delhivery legs.
-- SLA rate   = share of legs whose actual transit time <= SLA_FACTOR x OSRM estimate (meets_sla)
-- Delay ratio = actual transit time / OSRM estimate (medians are added in build_marts.py)
DROP VIEW IF EXISTS vw_leg;
CREATE VIEW vw_leg AS
SELECT f.*, d.full_date AS trip_date, d.day_name, d.day_of_week, d.is_weekend,
       s.facility_name AS source_name, s.city AS source_city, s.state AS source_state, s.facility_type AS source_type,
       t.facility_name AS destination_name, t.city AS destination_city, t.state AS destination_state,
       t.facility_type AS destination_type
FROM fact_leg f
JOIN dim_date d     ON d.date_key = f.trip_date_key
JOIN dim_facility s ON s.facility_key = f.source_key
JOIN dim_facility t ON t.facility_key = f.destination_key;

DROP VIEW IF EXISTS mart_daily;
CREATE VIEW mart_daily AS
SELECT trip_date AS date, COUNT(*) AS legs, COUNT(DISTINCT trip_uuid) AS trips,
       ROUND(AVG(meets_sla), 4) AS sla_rate,
       ROUND(AVG(route_type = 'FTL'), 4) AS ftl_share,
       ROUND(AVG(actual_time_min), 1) AS avg_actual_min,
       ROUND(AVG(osrm_time_min), 1) AS avg_osrm_min,
       ROUND(SUM(osrm_distance_km), 0) AS planned_km
FROM vw_leg GROUP BY trip_date;

DROP VIEW IF EXISTS mart_route_type;
CREATE VIEW mart_route_type AS
SELECT route_type, COUNT(*) AS legs, ROUND(AVG(meets_sla), 4) AS sla_rate,
       ROUND(AVG(osrm_distance_km), 1) AS avg_distance_km,
       ROUND(AVG(actual_time_min), 1) AS avg_actual_min, ROUND(AVG(osrm_time_min), 1) AS avg_osrm_min,
       ROUND(AVG(handling_min), 1) AS avg_handling_min
FROM vw_leg GROUP BY route_type;

DROP VIEW IF EXISTS mart_distance_band;
CREATE VIEW mart_distance_band AS
SELECT distance_band, route_type, COUNT(*) AS legs, ROUND(AVG(meets_sla), 4) AS sla_rate,
       ROUND(AVG(excess_min), 1) AS avg_excess_min
FROM vw_leg GROUP BY distance_band, route_type;

DROP VIEW IF EXISTS mart_hour;
CREATE VIEW mart_hour AS
SELECT start_hour AS hour, COUNT(*) AS legs, ROUND(AVG(meets_sla), 4) AS sla_rate
FROM vw_leg GROUP BY start_hour;

DROP VIEW IF EXISTS mart_day_of_week;
CREATE VIEW mart_day_of_week AS
SELECT day_of_week, day_name, COUNT(*) AS legs, ROUND(AVG(meets_sla), 4) AS sla_rate
FROM vw_leg GROUP BY day_of_week, day_name;

DROP VIEW IF EXISTS mart_state;
CREATE VIEW mart_state AS
SELECT source_state AS state, COUNT(*) AS legs, ROUND(AVG(meets_sla), 4) AS sla_rate,
       ROUND(AVG(is_interstate), 4) AS interstate_share, ROUND(AVG(handling_min), 1) AS avg_handling_min
FROM vw_leg GROUP BY source_state;

DROP VIEW IF EXISTS mart_corridor;
CREATE VIEW mart_corridor AS
SELECT source_state, destination_state, COUNT(*) AS legs, ROUND(AVG(meets_sla), 4) AS sla_rate,
       ROUND(AVG(osrm_distance_km), 1) AS avg_distance_km, ROUND(AVG(excess_min), 1) AS avg_excess_min
FROM vw_leg GROUP BY source_state, destination_state;

DROP VIEW IF EXISTS mart_hub;
CREATE VIEW mart_hub AS
SELECT source_name AS facility, source_city AS city, source_state AS state, source_type AS facility_type,
       COUNT(*) AS legs, ROUND(AVG(meets_sla), 4) AS sla_rate,
       ROUND(AVG(handling_min), 1) AS avg_handling_min, ROUND(AVG(excess_min), 1) AS avg_excess_min
FROM vw_leg GROUP BY source_key;
