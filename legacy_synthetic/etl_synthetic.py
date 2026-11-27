"""Extract raw CSVs -> clean & validate -> load SQLite star schema.

Run:  python src/etl.py
Output: data/processed/delivery.db  and  reports/data_quality_report.csv
"""
from pathlib import Path
import sqlite3
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, PROC, REPORTS = ROOT / "data" / "raw", ROOT / "data" / "processed", ROOT / "reports"
DB = PROC / "delivery.db"
PEAK_MONTHS = (10, 11)  # festive / Diwali season


def parse_mixed_dates(s: pd.Series) -> pd.Series:
    """Parse a column holding both ISO (yyyy-mm-dd) and US (mm/dd/yyyy) dates."""
    iso = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    us = pd.to_datetime(s, format="%m/%d/%Y", errors="coerce")
    return iso.fillna(us)


def extract():
    return {name: pd.read_csv(RAW / f"{name}.csv", dtype=str)
            for name in ["orders", "shipments", "carriers", "warehouses", "customers", "products"]}


def transform(raw):
    dq = []  # data-quality log
    def log(check, n, action):
        dq.append({"check": check, "rows_affected": int(n), "action": action})

    # ---- orders ----
    o = raw["orders"].copy()
    o["ship_mode"] = o.ship_mode.str.strip().str.title().replace({"Freight Ltl": "Freight LTL"})
    o["order_date"] = parse_mixed_dates(o.order_date)
    o["quantity"] = o.quantity.astype(int)
    o["order_value"] = o.order_value.astype(float)
    log("orders: ship_mode casing normalised", (raw["orders"].ship_mode != o.ship_mode).sum(), "title-cased")

    # ---- shipments ----
    s = raw["shipments"].copy()
    n0 = len(s)
    s = s.drop_duplicates()
    log("shipments: exact duplicate rows", n0 - len(s), "dropped")
    n1 = len(s)
    s = s.drop_duplicates("shipment_id", keep="first")
    log("shipments: duplicate shipment_id", n1 - len(s), "kept first")

    raw_code = s.carrier_code.copy()
    s["carrier_code"] = s.carrier_code.str.strip().str.upper()
    log("shipments: carrier_code whitespace/casing", (raw_code != s.carrier_code).sum(), "trimmed + upper-cased")
    known = set(raw["carriers"].carrier_code)
    unk = ~s.carrier_code.isin(known)
    log("shipments: unknown carrier_code", unk.sum(), "mapped to UNK")
    s.loc[unk, "carrier_code"] = "UNK"

    for c in ["ship_date", "promised_date", "delivered_date"]:
        us = s[c].str.contains("/", na=False).sum()
        s[c] = parse_mixed_dates(s[c])
        if us:
            log(f"shipments: {c} in US format", us, "parsed mm/dd/yyyy")

    s["weight_kg"] = s.weight_kg.astype(float)
    bad_w = s.weight_kg <= 0
    log("shipments: non-positive weight", bad_w.sum(), "set NULL (imputed from product weight)")
    s.loc[bad_w, "weight_kg"] = np.nan
    s["freight_cost_inr"] = s.freight_cost_inr.astype(float)
    s["qty_delivered"] = s.qty_delivered.astype(int)
    s["delay_reason"] = s.delay_reason.str.strip().replace("", np.nan)

    open_rows = s.delivered_date.isna() & (s.status == "Delivered")
    log("shipments: Delivered without delivered_date", open_rows.sum(), "status -> In Transit")
    s.loc[open_rows, "status"] = "In Transit"

    # ---- join & derive ----
    f = s.merge(o, on="order_id", how="left", validate="one_to_one")
    orphan = f.order_date.isna().sum()
    log("shipments: no matching order", orphan, "dropped")
    f = f[f.order_date.notna()].copy()

    prod = raw["products"].assign(unit_weight_kg=lambda d: d.unit_weight_kg.astype(float),
                                  unit_price=lambda d: d.unit_price.astype(float))
    f = f.merge(prod[["sku", "unit_weight_kg"]], on="sku", how="left")
    f["weight_kg"] = f.weight_kg.fillna((f.quantity * f.unit_weight_kg).round(1))

    bad_seq = f.ship_date < f.order_date
    log("shipments: ship_date before order_date", bad_seq.sum(), "flag only")

    delivered = f.status == "Delivered"
    f["processing_days"] = (f.ship_date - f.order_date).dt.days
    f["transit_days"] = (f.delivered_date - f.ship_date).dt.days
    f["lead_time_days"] = (f.delivered_date - f.order_date).dt.days
    f["delay_days"] = (f.delivered_date - f.promised_date).dt.days
    f["is_on_time"] = np.where(delivered, (f.delay_days <= 0).astype(float), np.nan)
    f["is_in_full"] = np.where(delivered, (f.qty_delivered >= f.quantity).astype(float), np.nan)
    f["is_otif"] = f.is_on_time * f.is_in_full
    f["is_damaged"] = np.where(delivered, (f.damaged_flag == "Y").astype(float), np.nan)
    # Business rule: a delay reason only applies to late deliveries
    f.loc[~(delivered & (f.delay_days > 0)), "delay_reason"] = None
    # Late with no carrier-reported reason: attribute to the warehouse when the
    # order sat >1 day before shipping, otherwise mark Unspecified.
    late_no_reason = delivered & (f.delay_days > 0) & f.delay_reason.isna()
    held = late_no_reason & (f.processing_days > 1)
    f.loc[held, "delay_reason"] = "Warehouse processing delay"
    f.loc[late_no_reason & ~held, "delay_reason"] = "Unspecified"
    log("shipments: late, no reason, held >1 day in DC", held.sum(), "reason = Warehouse processing delay")
    log("shipments: late, no reason, other", (late_no_reason & ~held).sum(), "reason = Unspecified")

    return f, prod, pd.DataFrame(dq)


def build_dim_date(dates: pd.Series) -> pd.DataFrame:
    rng = pd.date_range(dates.min(), dates.max(), freq="D")
    return pd.DataFrame({
        "date_key": rng.strftime("%Y%m%d").astype(int),
        "full_date": rng.strftime("%Y-%m-%d"),
        "year": rng.year, "quarter": rng.quarter, "month": rng.month,
        "month_start": rng.to_period("M").start_time.strftime("%Y-%m-%d"),
        "iso_week": rng.isocalendar().week.values.astype(int),
        "day_of_week": rng.dayofweek + 1,
        "is_weekend": (rng.dayofweek >= 5).astype(int),
        "is_peak_season": np.isin(rng.month, PEAK_MONTHS).astype(int),
    })


def to_key(d: pd.Series):
    return d.dt.strftime("%Y%m%d").astype("Int64")


def load(f, prod, raw, dq):
    PROC.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript((ROOT / "sql" / "schema.sql").read_text())

    carriers = pd.concat([raw["carriers"], pd.DataFrame([{"carrier_code": "UNK", "carrier_name": "Unknown"}])],
                         ignore_index=True)
    carriers.insert(0, "carrier_key", range(1, len(carriers) + 1))
    wh = raw["warehouses"].copy(); wh.insert(0, "warehouse_key", range(1, len(wh) + 1))
    cu = raw["customers"].copy(); cu.insert(0, "customer_key", range(1, len(cu) + 1))
    pr = prod.copy(); pr.insert(0, "product_key", range(1, len(pr) + 1))

    all_dates = pd.concat([f.order_date, f.ship_date, f.promised_date, f.delivered_date]).dropna()
    dd = build_dim_date(all_dates)

    fact = (f.merge(carriers[["carrier_key", "carrier_code"]], on="carrier_code")
             .merge(wh[["warehouse_key", "warehouse_id"]], on="warehouse_id")
             .merge(cu[["customer_key", "customer_id"]], on="customer_id")
             .merge(pr[["product_key", "sku"]], on="sku"))
    fact = pd.DataFrame({
        "shipment_id": fact.shipment_id, "order_id": fact.order_id,
        "order_date_key": to_key(fact.order_date), "ship_date_key": to_key(fact.ship_date),
        "promised_date_key": to_key(fact.promised_date), "delivered_date_key": to_key(fact.delivered_date),
        "carrier_key": fact.carrier_key, "warehouse_key": fact.warehouse_key,
        "customer_key": fact.customer_key, "product_key": fact.product_key,
        "ship_mode": fact.ship_mode, "status": fact.status,
        "quantity_ordered": fact.quantity, "quantity_delivered": fact.qty_delivered,
        "order_value_inr": fact.order_value, "weight_kg": fact.weight_kg,
        "freight_cost_inr": fact.freight_cost_inr,
        "processing_days": fact.processing_days, "transit_days": fact.transit_days,
        "lead_time_days": fact.lead_time_days, "delay_days": fact.delay_days,
        "is_on_time": fact.is_on_time, "is_in_full": fact.is_in_full, "is_otif": fact.is_otif,
        "is_damaged": fact.is_damaged, "delay_reason": fact.delay_reason,
    })

    dd.to_sql("dim_date", con, if_exists="append", index=False)
    carriers.to_sql("dim_carrier", con, if_exists="append", index=False)
    wh.to_sql("dim_warehouse", con, if_exists="append", index=False)
    cu.to_sql("dim_customer", con, if_exists="append", index=False)
    pr.to_sql("dim_product", con, if_exists="append", index=False)
    fact.to_sql("fact_shipment", con, if_exists="append", index=False)
    con.executescript((ROOT / "sql" / "kpi_views.sql").read_text())
    con.commit(); con.close()

    dq.to_csv(REPORTS / "data_quality_report.csv", index=False)
    print(dq.to_string(index=False))
    print(f"\nloaded {len(fact):,} shipments into {DB}")


def main():
    raw = extract()
    f, prod, dq = transform(raw)
    load(f, prod, raw, dq)


if __name__ == "__main__":
    main()
