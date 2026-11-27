"""Generate a realistic, deliberately messy synthetic supply-chain dataset for India.

Indian geography (5 DCs, 6 zones), fictional Indian carriers, rupee (INR) costs,
Diwali/festive peak in Oct-Nov and monsoon disruption in Jul-Sep.

Writes raw CSV extracts to data/raw/, the way they'd land from an ERP/TMS:
  orders.csv, shipments.csv, carriers.csv, warehouses.csv, customers.csv, products.csv

Built-in data-quality problems for the ETL to fix: duplicate shipment rows,
inconsistent casing/whitespace, mixed date formats, missing delivery dates
for in-transit loads, negative/zero weights, and unknown carrier codes.
"""
from pathlib import Path
import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)
RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
START, END = pd.Timestamp("2024-11-01"), pd.Timestamp("2026-10-31")
N_ORDERS = 60_000

# Carrier names are fictional; they are not real Indian logistics companies.
CARRIERS = pd.DataFrame({
    "carrier_code": ["GRX", "VAY", "DCC", "SFF", "GNR", "SHT", "BRC"],
    "carrier_name": ["Garuda Express", "Vayu Logistics", "Deccan Couriers", "Saffron Freight",
                     "Ganga Roadways", "Sahyadri Transport", "Brahmaputra Cargo"],
    "base_ontime": [0.93, 0.92, 0.89, 0.86, 0.90, 0.82, 0.78],
    "speed": [0.85, 0.9, 1.0, 1.05, 1.1, 1.2, 1.6],
    "cost_mult": [1.35, 1.25, 1.2, 1.0, 0.95, 0.85, 0.7],
    "damage": [0.006, 0.007, 0.009, 0.012, 0.010, 0.016, 0.020],
})
WAREHOUSES = pd.DataFrame({
    "warehouse_id": ["WH-DEL", "WH-BOM", "WH-BLR", "WH-CCU", "WH-NAG"],
    "warehouse_name": ["Delhi NCR DC", "Mumbai (Bhiwandi) DC", "Bengaluru DC", "Kolkata DC", "Nagpur DC"],
    "wh_region": ["North", "West", "South", "East", "Central"],
    "capacity_pallets": [48000, 52000, 44000, 30000, 26000],
})
REGIONS = ["North", "West", "South", "East", "Central", "Northeast"]
SAME = 1
ADJ = {frozenset(p) for p in [("North", "Central"), ("North", "West"), ("West", "Central"), ("West", "South"),
                              ("South", "Central"), ("East", "Central"), ("East", "Northeast"), ("North", "East")]}
# Prices and weights; money is in Indian rupees (INR)
CATEGORIES = {"Electronics": (0.5, 6, 9000), "Fashion": (0.3, 2, 1500), "Home & Kitchen": (1, 12, 2500),
              "Industrial": (10, 120, 15000), "Beauty & Personal Care": (0.2, 1.5, 700), "FMCG / Grocery": (2, 25, 900)}
SHIP_MODES = {"Surface": (1.0, 1.0, 0.55), "Air Express": (0.55, 2.2, 0.22),
              "Rail Freight": (1.3, 0.7, 0.15), "Same Day (Metro)": (0.25, 3.0, 0.08)}
DELAY_REASONS = ["Monsoon / flooding", "Carrier capacity", "Warehouse backlog", "Incomplete address",
                 "E-way bill / checkpost hold", "Vehicle breakdown", "Festive peak volume"]
PEAK_MONTHS = [10, 11]       # Diwali / festive sale season
MONSOON_MONTHS = [7, 8, 9]


def lane_days(o, d):
    if o == d:
        return SAME
    if "Northeast" in (o, d):
        return 3 if "East" in (o, d) else 6
    if frozenset((o, d)) in ADJ:
        return 3
    return 4


def main():
    RAW.mkdir(parents=True, exist_ok=True)

    # Customers
    n_cust = 4000
    customers = pd.DataFrame({
        "customer_id": [f"C{i:05d}" for i in range(n_cust)],
        "segment": RNG.choice(["Kirana / Retail", "Distributor", "E-commerce", "Enterprise"], n_cust, p=[.3, .2, .35, .15]),
        "region": RNG.choice(REGIONS, n_cust, p=[.27, .25, .24, .12, .07, .05]),
    })
    # Products
    n_prod = 600
    cats = RNG.choice(list(CATEGORIES), n_prod)
    products = pd.DataFrame({
        "sku": [f"SKU-{i:04d}" for i in range(n_prod)],
        "category": cats,
        "unit_weight_kg": [round(RNG.uniform(*CATEGORIES[c][:2]), 2) for c in cats],
        "unit_price": [round(RNG.gamma(3, CATEGORIES[c][2] / 3), 2) for c in cats],
    })

    # Orders with seasonality (peak Nov–Dec) and growth
    days = pd.date_range(START, END, freq="D")
    season = 1 + 0.5 * np.isin(days.month, PEAK_MONTHS) + 0.1 * (days.month == 12)
    trend = np.linspace(1.0, 1.25, len(days))
    weekday = np.where(days.dayofweek == 6, 0.4, 1.0)  # Sunday is the quiet day
    w = season * trend * weekday
    order_dates = RNG.choice(days, N_ORDERS, p=w / w.sum())
    order_dates = pd.to_datetime(np.sort(order_dates))

    cust = customers.sample(N_ORDERS, replace=True, random_state=1).reset_index(drop=True)
    prod = products.sample(N_ORDERS, replace=True, random_state=2).reset_index(drop=True)
    modes = RNG.choice(list(SHIP_MODES), N_ORDERS, p=[v[2] for v in SHIP_MODES.values()])
    qty = RNG.integers(1, 40, N_ORDERS)

    # Nearest warehouse with some overflow routing
    wh_by_region = {"North": "WH-DEL", "West": "WH-BOM", "South": "WH-BLR", "East": "WH-CCU",
                    "Central": "WH-NAG", "Northeast": "WH-CCU"}
    wh = np.array([wh_by_region[r] for r in cust.region])
    overflow = RNG.random(N_ORDERS) < 0.18
    wh[overflow] = RNG.choice(WAREHOUSES.warehouse_id, overflow.sum())

    orders = pd.DataFrame({
        "order_id": [f"SO-{i:06d}" for i in range(N_ORDERS)],
        "order_date": order_dates,
        "customer_id": cust.customer_id,
        "sku": prod.sku,
        "quantity": qty,
        "ship_mode": modes,
        "warehouse_id": wh,
    })
    orders["order_value"] = (qty * prod.unit_price).round(2)

    # Shipments
    c_idx = RNG.choice(len(CARRIERS), N_ORDERS, p=[.17, .2, .14, .16, .12, .12, .09])
    car = CARRIERS.iloc[c_idx].reset_index(drop=True)
    wh_region = WAREHOUSES.set_index("warehouse_id").loc[wh, "wh_region"].values
    base = np.array([lane_days(o, d) for o, d in zip(wh_region, cust.region)])
    mode_speed = np.array([SHIP_MODES[m][0] for m in modes])
    mode_cost = np.array([SHIP_MODES[m][1] for m in modes])

    # Warehouse processing (dwell) — Mumbai (Bhiwandi) + festive backlog are slower
    dwell = RNG.poisson(0.6, N_ORDERS) + (wh == "WH-BOM") * RNG.poisson(0.5, N_ORDERS)
    peak = np.isin(order_dates.month, PEAK_MONTHS)
    monsoon = np.isin(order_dates.month, MONSOON_MONTHS)
    dwell = dwell + peak * RNG.poisson(0.7, N_ORDERS)
    ship_date = order_dates + pd.to_timedelta(dwell, "D")

    promised_days = np.maximum(1, np.ceil(base * mode_speed * 1.0 + 1)).astype(int)
    promised = order_dates + pd.to_timedelta(promised_days + 1, "D")

    transit = np.maximum(1, np.round(base * mode_speed * car.speed.values + RNG.normal(0, 0.6, N_ORDERS)))
    # Disruptions: probability driven by carrier reliability, peak, weather months, lane length
    p_late = (1 - car.base_ontime.values) + 0.07 * peak + 0.05 * monsoon \
        + 0.04 * (base >= 5) - 0.03 * (modes == "Same Day (Metro)")
    # Improvement program from mid-2025 for Saffron Freight
    p_late = p_late - 0.05 * ((car.carrier_code.values == "SFF") & (order_dates >= "2025-07-01"))
    disrupted = RNG.random(N_ORDERS) < np.clip(p_late, 0.01, 0.6)
    extra = disrupted * (1 + RNG.gamma(1.5, 1.2, N_ORDERS)).round()
    transit = transit + extra
    delivered = ship_date + pd.to_timedelta(transit, "D")

    weight = (qty * prod.unit_weight_kg.values).round(1)
    freight = ((90 + 14 * weight) * car.cost_mult.values * mode_cost * (1 + 0.08 * base)
               * RNG.normal(1, 0.06, N_ORDERS)).round(2)

    reason = np.where(disrupted, RNG.choice(DELAY_REASONS, N_ORDERS), "")
    # bias reasons by context
    reason = np.where(disrupted & peak & (RNG.random(N_ORDERS) < .5), "Festive peak volume", reason)
    reason = np.where(disrupted & monsoon & (RNG.random(N_ORDERS) < .55), "Monsoon / flooding", reason)
    reason = np.where(disrupted & (base >= 4) & (RNG.random(N_ORDERS) < .25), "E-way bill / checkpost hold", reason)
    reason = np.where(disrupted & (wh == "WH-BOM") & (RNG.random(N_ORDERS) < .35), "Warehouse backlog", reason)

    damaged = RNG.random(N_ORDERS) < car.damage.values * (1 + (prod.category.values == "Electronics"))
    short = RNG.random(N_ORDERS) < 0.015

    shipments = pd.DataFrame({
        "shipment_id": [f"SH-{i:07d}" for i in range(N_ORDERS)],
        "order_id": orders.order_id,
        "carrier_code": car.carrier_code.values,
        "ship_date": ship_date,
        "promised_date": promised,
        "delivered_date": delivered,
        "weight_kg": weight,
        "freight_cost_inr": freight,
        "delay_reason": reason,
        "damaged_flag": np.where(damaged, "Y", "N"),
        "qty_delivered": np.where(short, np.maximum(0, qty - RNG.integers(1, 4, N_ORDERS)), qty),
        "status": "Delivered",
    })

    # ---- inject realistic mess ----
    in_transit = shipments.ship_date > END - pd.Timedelta(days=6)
    shipments.loc[in_transit, "delivered_date"] = pd.NaT
    shipments.loc[in_transit, "status"] = "In Transit"
    cancelled = RNG.random(N_ORDERS) < 0.008
    shipments.loc[cancelled, ["status", "delivered_date"]] = ["Cancelled", pd.NaT]

    s = shipments.copy()
    for col in ["ship_date", "promised_date", "delivered_date"]:
        s[col] = s[col].dt.strftime("%Y-%m-%d")
    alt = RNG.random(len(s)) < 0.07  # some rows exported in US format
    for col in ["ship_date", "delivered_date"]:
        m = alt & s[col].notna()
        s.loc[m, col] = pd.to_datetime(s.loc[m, col]).dt.strftime("%m/%d/%Y")
    lc = RNG.random(len(s)) < 0.05
    s.loc[lc, "carrier_code"] = " " + s.loc[lc, "carrier_code"].str.lower() + " "
    bad_w = RNG.random(len(s)) < 0.003
    s.loc[bad_w, "weight_kg"] = RNG.choice([0, -1.0], bad_w.sum())
    unk = RNG.random(len(s)) < 0.001
    s.loc[unk, "carrier_code"] = "ZZZ"
    dups = s.sample(frac=0.01, random_state=7)
    s = pd.concat([s, dups]).sample(frac=1, random_state=8).reset_index(drop=True)

    o = orders.copy()
    o["order_date"] = o.order_date.dt.strftime("%Y-%m-%d")
    o.loc[RNG.random(len(o)) < 0.04, "ship_mode"] = o.ship_mode.str.upper()

    o.to_csv(RAW / "orders.csv", index=False)
    s.to_csv(RAW / "shipments.csv", index=False)
    CARRIERS[["carrier_code", "carrier_name"]].to_csv(RAW / "carriers.csv", index=False)
    WAREHOUSES.to_csv(RAW / "warehouses.csv", index=False)
    customers.to_csv(RAW / "customers.csv", index=False)
    products.to_csv(RAW / "products.csv", index=False)
    print(f"raw: {len(o):,} orders, {len(s):,} shipment rows (incl. duplicates) -> {RAW}")


if __name__ == "__main__":
    main()
