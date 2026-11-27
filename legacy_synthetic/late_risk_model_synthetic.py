"""Late-delivery risk model, scored at the moment a shipment leaves the DC.

Logistic regression on carrier, warehouse, ship mode, destination region,
peak season, lane length proxy and DC processing days. Validated on a
time split (train: before 2026-05-01, test: after) to avoid look-ahead.
Outputs data/marts/late_risk_drivers.csv and reports/model_metrics.json.
"""
from pathlib import Path
import json
import sqlite3
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "processed" / "delivery.db"
CAT = ["carrier_name", "warehouse_name", "ship_mode", "dest_region", "segment", "category"]
NUM = ["processing_days", "is_peak_season", "weight_kg"]
SPLIT = "2026-05-01"


def main():
    con = sqlite3.connect(DB)
    df = pd.read_sql("SELECT * FROM vw_shipment WHERE status='Delivered' AND carrier_code <> 'UNK'", con)
    con.close()
    df["late"] = (df.is_on_time == 0).astype(int)
    train, test = df[df.order_date < SPLIT], df[df.order_date >= SPLIT]

    # Baseline = the most common value of each category, so odds ratios read
    # "compared with a typical shipment".
    baseline = [train[c].mode()[0] for c in CAT]
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", drop=baseline), CAT),
        ("num", StandardScaler(), NUM),
    ])
    model = Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=2000, C=1.0))])
    model.fit(train[CAT + NUM], train.late)
    p = model.predict_proba(test[CAT + NUM])[:, 1]

    top_decile = test.assign(p=p).nlargest(len(test) // 10, "p")
    metrics = {
        "train_rows": int(len(train)), "test_rows": int(len(test)),
        "test_late_rate": round(float(test.late.mean()), 4),
        "roc_auc": round(float(roc_auc_score(test.late, p)), 4),
        "pr_auc": round(float(average_precision_score(test.late, p)), 4),
        "top_decile_late_rate": round(float(top_decile.late.mean()), 4),
        "top_decile_lift": round(float(top_decile.late.mean() / test.late.mean()), 2),
    }
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "model_metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))
    metrics_rows = dict(metrics, train_period=f"before {SPLIT}", test_period=f"{SPLIT} onward",
                        baseline=", ".join(baseline))
    pd.DataFrame({"metric": list(metrics_rows), "value": list(metrics_rows.values())}) \
        .to_csv(ROOT / "data" / "marts" / "model_metrics.csv", index=False)

    names = model.named_steps["pre"].get_feature_names_out()
    coefs = model.named_steps["clf"].coef_[0]
    drivers = pd.DataFrame({"feature": names, "coefficient": coefs})
    drivers["odds_ratio"] = np.exp(drivers.coefficient).round(3)
    drivers["feature"] = (drivers.feature.str.replace(r"^cat__", "", regex=True)
                          .str.replace(r"^num__", "", regex=True)
                          .str.replace(r"^(carrier_name|warehouse_name|ship_mode|dest_region|segment|category)_",
                                       lambda m: {"carrier_name": "Carrier", "warehouse_name": "Warehouse",
                                                  "ship_mode": "Ship mode", "dest_region": "Destination",
                                                  "segment": "Segment", "category": "Category"}[m.group(1)] + ": ",
                                       regex=True)
                          .replace({"processing_days": "DC processing days (+1 SD)",
                                    "is_peak_season": "Festive peak (Oct-Nov)", "weight_kg": "Shipment weight (+1 SD)"}))
    drivers = drivers.reindex(drivers.coefficient.abs().sort_values(ascending=False).index)
    drivers["coefficient"] = drivers.coefficient.round(4)
    drivers.head(15).to_csv(ROOT / "data" / "marts" / "late_risk_drivers.csv", index=False)
    print(drivers.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
