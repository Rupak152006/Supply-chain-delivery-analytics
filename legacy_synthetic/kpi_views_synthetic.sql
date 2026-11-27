-- KPI semantic layer. Rates are over DELIVERED shipments; volume counts all non-cancelled.
-- OTD  = delivered on/before promised date
-- OTIF = on time AND full quantity delivered
DROP VIEW IF EXISTS vw_shipment;
CREATE VIEW vw_shipment AS
SELECT f.*,
       od.full_date  AS order_date, od.month_start AS order_month, od.is_peak_season,
       c.carrier_code, c.carrier_name,
       w.warehouse_id, w.warehouse_name, w.wh_region,
       cu.segment, cu.region AS dest_region,
       p.category
FROM fact_shipment f
JOIN dim_date od     ON od.date_key = f.order_date_key
JOIN dim_carrier c   ON c.carrier_key = f.carrier_key
JOIN dim_warehouse w ON w.warehouse_key = f.warehouse_key
JOIN dim_customer cu ON cu.customer_key = f.customer_key
JOIN dim_product p   ON p.product_key = f.product_key
WHERE f.status <> 'Cancelled';

DROP VIEW IF EXISTS mart_monthly_kpis;
CREATE VIEW mart_monthly_kpis AS
SELECT order_month                                   AS month,
       COUNT(*)                                      AS shipments,
       SUM(status = 'Delivered')                     AS delivered,
       ROUND(AVG(is_on_time), 4)                     AS otd_rate,
       ROUND(AVG(is_otif), 4)                        AS otif_rate,
       ROUND(AVG(is_damaged), 4)                     AS damage_rate,
       ROUND(AVG(lead_time_days), 2)                 AS avg_lead_time_days,
       ROUND(AVG(transit_days), 2)                   AS avg_transit_days,
       ROUND(AVG(processing_days), 2)                AS avg_processing_days,
       ROUND(AVG(CASE WHEN delay_days > 0 THEN delay_days END), 2) AS avg_days_late,
       ROUND(SUM(freight_cost_inr), 2)               AS freight_cost_inr,
       ROUND(SUM(freight_cost_inr) / COUNT(*), 2)    AS cost_per_shipment,
       ROUND(SUM(freight_cost_inr) / SUM(order_value_inr), 4) AS freight_to_sales
FROM vw_shipment
GROUP BY order_month;

DROP VIEW IF EXISTS mart_carrier_scorecard;
CREATE VIEW mart_carrier_scorecard AS
SELECT carrier_name AS carrier,
       COUNT(*)                                   AS shipments,
       ROUND(AVG(is_on_time), 4)                  AS otd_rate,
       ROUND(AVG(is_otif), 4)                     AS otif_rate,
       ROUND(AVG(is_damaged), 4)                  AS damage_rate,
       ROUND(AVG(transit_days), 2)                AS avg_transit_days,
       ROUND(AVG(CASE WHEN delay_days > 0 THEN delay_days END), 2) AS avg_days_late,
       ROUND(SUM(freight_cost_inr) / COUNT(*), 2) AS cost_per_shipment,
       ROUND(SUM(freight_cost_inr) / SUM(weight_kg), 3) AS cost_per_kg
FROM vw_shipment
WHERE carrier_code <> 'UNK'
GROUP BY carrier_name;

DROP VIEW IF EXISTS mart_region_performance;
CREATE VIEW mart_region_performance AS
SELECT dest_region AS region,
       COUNT(*)                         AS shipments,
       ROUND(AVG(is_on_time), 4)        AS otd_rate,
       ROUND(AVG(lead_time_days), 2)    AS avg_lead_time_days,
       ROUND(SUM(freight_cost_inr) / COUNT(*), 2) AS cost_per_shipment
FROM vw_shipment GROUP BY dest_region;

DROP VIEW IF EXISTS mart_lane_matrix;
CREATE VIEW mart_lane_matrix AS
SELECT warehouse_name AS warehouse, dest_region AS region,
       COUNT(*)                      AS shipments,
       ROUND(AVG(is_on_time), 4)     AS otd_rate,
       ROUND(AVG(lead_time_days), 2) AS avg_lead_time_days
FROM vw_shipment GROUP BY warehouse_name, dest_region;

DROP VIEW IF EXISTS mart_delay_reasons;
CREATE VIEW mart_delay_reasons AS
SELECT delay_reason AS reason,
       COUNT(*)                   AS late_shipments,
       ROUND(AVG(delay_days), 2)  AS avg_days_late,
       ROUND(COUNT(*) * 1.0 / (SELECT COUNT(*) FROM vw_shipment WHERE delay_days > 0), 4) AS share_of_late
FROM vw_shipment WHERE delay_days > 0
GROUP BY delay_reason;

DROP VIEW IF EXISTS mart_ship_mode;
CREATE VIEW mart_ship_mode AS
SELECT ship_mode,
       COUNT(*)                         AS shipments,
       ROUND(AVG(is_on_time), 4)        AS otd_rate,
       ROUND(AVG(lead_time_days), 2)    AS avg_lead_time_days,
       ROUND(SUM(freight_cost_inr) / COUNT(*), 2) AS cost_per_shipment
FROM vw_shipment GROUP BY ship_mode;

DROP VIEW IF EXISTS mart_warehouse;
CREATE VIEW mart_warehouse AS
SELECT warehouse_name AS warehouse,
       COUNT(*)                          AS shipments,
       ROUND(AVG(processing_days), 2)    AS avg_processing_days,
       ROUND(AVG(processing_days > 1), 4) AS share_held_over_1_day,
       ROUND(AVG(is_on_time), 4)         AS otd_rate
FROM vw_shipment GROUP BY warehouse_name;

DROP VIEW IF EXISTS mart_carrier_monthly;
CREATE VIEW mart_carrier_monthly AS
SELECT order_month AS month, carrier_name AS carrier,
       COUNT(*)                  AS shipments,
       ROUND(AVG(is_on_time), 4) AS otd_rate,
       ROUND(AVG(is_otif), 4)    AS otif_rate
FROM vw_shipment WHERE carrier_code <> 'UNK'
GROUP BY order_month, carrier_name;
