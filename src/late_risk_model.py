"""SLA-breach risk model, scored when a leg is dispatched.

Logistic regression on what is known at dispatch: route type, planned distance and
OSRM time, start hour, day of week, inter-state flag, source state and facility type.
Time split: train on trips created before 2018-09-27, test on the rest.
Outputs data/marts/risk_drivers.csv, data/marts/model_metrics.csv, reports/model_metrics.json.
"""
import json
import sqlite3
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from config import DB, MARTS, MIN_LEGS_RANKED, REPORTS

SPLIT = "2018-09-27"
CAT = ["route_type", "time_of_day", "source_state", "source_type", "day_name"]
NUM = ["log_osrm_distance", "is_interstate"]
SLOTS = [(0, 4, "Night (0-4h)"), (4, 9, "Early morning (4-9h)"), (9, 17, "Daytime (9-17h)"), (17, 24, "Evening (17-24h)")]
LABELS = {"route_type": "Route", "time_of_day": "Starts", "source_state": "From", "source_type": "Facility",
          "day_name": "Day"}


def main():
    con = sqlite3.connect(DB)
    df = pd.read_sql("SELECT * FROM vw_leg", con)
    con.close()
    df["breach"] = 1 - df.meets_sla
    df["time_of_day"] = pd.cut(df.start_hour, [s[0] for s in SLOTS] + [24], right=False,
                               labels=[s[2] for s in SLOTS]).astype(str)
    small = df.source_state.map(df.source_state.value_counts()) < MIN_LEGS_RANKED
    df.loc[small, "source_state"] = "Other states"
    df["log_osrm_distance"] = np.log(df.osrm_distance_km)
    train, test = df[df.trip_date < SPLIT], df[df.trip_date >= SPLIT]

    baseline = [train[c].mode()[0] for c in CAT]
    model = Pipeline([
        ("pre", ColumnTransformer([("cat", OneHotEncoder(drop=baseline, handle_unknown="ignore"), CAT),
                                   ("num", StandardScaler(), NUM)])),
        ("clf", LogisticRegression(max_iter=3000))])
    model.fit(train[CAT + NUM], train.breach)
    p = model.predict_proba(test[CAT + NUM])[:, 1]
    top = test.assign(p=p).nlargest(len(test) // 10, "p")
    metrics = {
        "train_legs": int(len(train)), "test_legs": int(len(test)),
        "test_breach_rate": round(float(test.breach.mean()), 4),
        "roc_auc": round(float(roc_auc_score(test.breach, p)), 4),
        "pr_auc": round(float(average_precision_score(test.breach, p)), 4),
        "top_decile_breach_rate": round(float(top.breach.mean()), 4),
        "top_decile_lift": round(float(top.breach.mean() / test.breach.mean()), 2),
    }
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "model_metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))
    rows = dict(metrics, train_period=f"trips before {SPLIT}", test_period=f"trips from {SPLIT}",
                baseline=", ".join(baseline))
    pd.DataFrame({"metric": list(rows), "value": list(rows.values())}).to_csv(MARTS / "model_metrics.csv", index=False)

    names = model.named_steps["pre"].get_feature_names_out()
    coef = model.named_steps["clf"].coef_[0]
    def label(n):
        n = n.split("__", 1)[1]
        for col, lab in LABELS.items():
            if n.startswith(col + "_"):
                return f"{lab}: {n[len(col) + 1:]}"
        return {"log_osrm_distance": "Longer planned distance (+1 SD, log km)",
                "is_interstate": "Inter-state leg"}.get(n, n)
    d = pd.DataFrame({"feature": [label(n) for n in names], "coefficient": coef.round(4),
                      "odds_ratio": np.exp(coef).round(3)})
    d = d.reindex(d.coefficient.abs().sort_values(ascending=False).index).head(15)
    d.to_csv(MARTS / "risk_drivers.csv", index=False)
    print(d.to_string(index=False))


if __name__ == "__main__":
    main()
