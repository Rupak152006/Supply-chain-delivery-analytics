-- Star schema for delivery analytics (SQLite dialect)
DROP TABLE IF EXISTS fact_shipment;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_carrier;
DROP TABLE IF EXISTS dim_warehouse;
DROP TABLE IF EXISTS dim_customer;
DROP TABLE IF EXISTS dim_product;

CREATE TABLE dim_date (
    date_key     INTEGER PRIMARY KEY,   -- yyyymmdd
    full_date    TEXT NOT NULL,
    year         INTEGER, quarter INTEGER, month INTEGER,
    month_start  TEXT, iso_week INTEGER, day_of_week INTEGER,
    is_weekend   INTEGER, is_peak_season INTEGER
);
CREATE TABLE dim_carrier   (carrier_key INTEGER PRIMARY KEY, carrier_code TEXT UNIQUE, carrier_name TEXT);
CREATE TABLE dim_warehouse (warehouse_key INTEGER PRIMARY KEY, warehouse_id TEXT UNIQUE, warehouse_name TEXT,
                            wh_region TEXT, capacity_pallets INTEGER);
CREATE TABLE dim_customer  (customer_key INTEGER PRIMARY KEY, customer_id TEXT UNIQUE, segment TEXT, region TEXT);
CREATE TABLE dim_product   (product_key INTEGER PRIMARY KEY, sku TEXT UNIQUE, category TEXT,
                            unit_weight_kg REAL, unit_price REAL);

CREATE TABLE fact_shipment (
    shipment_id        TEXT PRIMARY KEY,
    order_id           TEXT NOT NULL,
    order_date_key     INTEGER REFERENCES dim_date(date_key),
    ship_date_key      INTEGER REFERENCES dim_date(date_key),
    promised_date_key  INTEGER REFERENCES dim_date(date_key),
    delivered_date_key INTEGER REFERENCES dim_date(date_key),
    carrier_key        INTEGER REFERENCES dim_carrier(carrier_key),
    warehouse_key      INTEGER REFERENCES dim_warehouse(warehouse_key),
    customer_key       INTEGER REFERENCES dim_customer(customer_key),
    product_key        INTEGER REFERENCES dim_product(product_key),
    ship_mode          TEXT,
    status             TEXT,
    quantity_ordered   INTEGER,
    quantity_delivered INTEGER,
    order_value_inr    REAL,
    weight_kg          REAL,
    freight_cost_inr   REAL,
    processing_days    INTEGER,   -- order -> ship (warehouse dwell)
    transit_days       INTEGER,   -- ship -> delivered
    lead_time_days     INTEGER,   -- order -> delivered
    delay_days         INTEGER,   -- delivered - promised (<=0 means on time)
    is_on_time         INTEGER,
    is_in_full         INTEGER,
    is_otif            INTEGER,
    is_damaged         INTEGER,
    delay_reason       TEXT
);
CREATE INDEX ix_fact_order_date ON fact_shipment(order_date_key);
CREATE INDEX ix_fact_carrier ON fact_shipment(carrier_key);
CREATE INDEX ix_fact_wh ON fact_shipment(warehouse_key);
