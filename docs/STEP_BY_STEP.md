# Step-by-step guide: Delhivery India delivery analytics, end to end

This guide rebuilds the whole project on your own computer: real data in, a report and a dashboard out. Every file it uses or creates is in this one folder.

## 0. What is in the folder

```
supply-chain-delivery-analytics/
├── README.md                     project overview and findings
├── requirements.txt              Python packages
├── run_pipeline.py               runs every step below in order
├── docs/
│   └── STEP_BY_STEP.md           this guide
├── src/
│   ├── config.py                 paths, data URL, SLA_FACTOR setting
│   ├── download_data.py          step 2: get the raw data
│   ├── etl.py                    step 3: clean + load the database
│   ├── build_marts.py            step 4: KPI tables for BI
│   ├── late_risk_model.py        step 5: prediction model
│   └── build_dashboard.py        step 6: offline dashboard + Excel
├── sql/
│   ├── schema.sql                star-schema tables
│   └── kpi_views.sql             KPI definitions (SQL views)
├── tests/
│   └── test_data_quality.py      step 7: 10 automated checks
├── data/
│   ├── raw/delhivery_data.csv    real Delhivery data (144,867 rows)
│   ├── processed/delivery.db     SQLite warehouse (created in step 3)
│   └── marts/*.csv               KPI tables (created in steps 4-5)
├── dashboard/
│   ├── delhivery_dashboard.html  open in any browser, works offline
│   ├── delhivery_marts.xlsx      same tables for Power BI / Tableau / Excel
│   └── claude_artifact_page.html source of the online Claude dashboard
├── reports/
│   ├── Delhivery_India_Delivery_Report.pdf   the written report
│   ├── data_quality_report.csv   what the cleaning step found and fixed
│   └── model_metrics.json        model accuracy
└── legacy_synthetic/             earlier synthetic-data version (reference only)
```

## 1. Install the tools (once)

You need Python 3.10 or newer. Check with `python --version`.

Open a terminal in this folder, create a virtual environment and install the packages:

```bash
python -m venv .venv
```

On Windows:

```bash
.venv\Scripts\activate
```

On macOS or Linux:

```bash
source .venv/bin/activate
```

Then:

```bash
pip install -r requirements.txt
```

## 2. Get the data — `src/download_data.py`

```bash
python src/download_data.py
```

This downloads Delhivery's public trip dataset into `data/raw/delhivery_data.csv` and checks its SHA-256 fingerprint. The file is already in the folder, so the script will say `already present and verified`.

**What the data is:** one row per checkpoint on a truck's journey between two Delhivery facilities. Each row has the trip, source and destination facility, timestamps, actual minutes travelled and the OSRM routing engine's estimated minutes and kilometres. It covers 12 Sep to 3 Oct 2018.

## 3. Clean and load — `src/etl.py`

```bash
python src/etl.py
```

What it does, in order:

1. Reads the raw CSV (144,867 rows) and drops exact duplicate rows.
2. Parses all timestamps; drops rows that fail.
3. Fills missing facility names where another row has the same facility code, otherwise labels them "Unknown".
4. Rolls checkpoints up to **legs**: one row per trip from one facility to the next (26,368 legs).
5. Calculates per leg: delay ratio (actual ÷ planned time), extra minutes, time at facilities, distance band, start hour, and whether the leg is **within SLA** (actual ≤ 2× planned).
6. Parses each facility name such as `Bhiwandi_Mankoli_HB (Maharashtra)` into city, state and type.
7. Loads a **star schema** into `data/processed/delivery.db` (`fact_leg` + `dim_facility`, `dim_route`, `dim_date`), then creates the KPI views from `sql/kpi_views.sql`.
8. Writes `reports/data_quality_report.csv`.

**Try it yourself:** open the database in [DB Browser for SQLite](https://sqlitebrowser.org/) and run:

```sql
SELECT source_state, COUNT(*) AS legs, ROUND(AVG(meets_sla), 3) AS sla_rate
FROM vw_leg GROUP BY source_state ORDER BY sla_rate;
```

## 4. Build KPI tables — `src/build_marts.py`

```bash
python src/build_marts.py
```

Exports one CSV per business question into `data/marts/`: `overall`, `daily`, `route_type`, `distance_band`, `hour`, `day_of_week`, `state`, `corridor`, `hub`. These are the tables a BI tool reads.

## 5. Train the prediction model — `src/late_risk_model.py`

```bash
python src/late_risk_model.py
```

Trains a logistic regression that predicts, at dispatch, whether a leg will miss the SLA. It uses route type, planned distance, start time, day, inter-state flag, origin state and facility type. It trains on trips before 27 Sep 2018 and tests on later trips, so it never sees the future. Results go to `data/marts/risk_drivers.csv`, `data/marts/model_metrics.csv` and `reports/model_metrics.json`. Expect ROC AUC of about 0.71.

## 6. Build the dashboard — `src/build_dashboard.py`

```bash
python src/build_dashboard.py
```

Creates:

- `dashboard/delhivery_dashboard.html`: double-click to open in any browser. It needs no internet and has tooltips on every chart.
- `dashboard/delhivery_marts.xlsx`: every KPI table on its own sheet.

**To use Power BI instead:** Home → Get data → Excel workbook → pick `delhivery_marts.xlsx` → tick all sheets → Load. Then build visuals. For example, a line chart of `daily[date]` against `daily[sla_rate]`, or a bar chart of `state[state]` against `state[sla_rate]`. Tableau works the same way (Connect → Microsoft Excel).

## 7. Test everything — `tests/test_data_quality.py`

```bash
python -m pytest -q tests
```

Ten checks must pass. They cover unique legs, every raw leg loaded, no broken keys, times in order, the SLA flag matching its rule, and mart totals matching the database.

## 8. Or run it all at once

```bash
python run_pipeline.py
```

It runs steps 2 to 7 in order and stops at the first failure.

## 9. Change the business rule

Open `src/config.py` and change `SLA_FACTOR = 2.0`, for example to `1.5` for a stricter target. Then run `python run_pipeline.py` again; every table, the model and the dashboard update.

## 10. Use your own data

Put your own shipment checkpoint file in `data/raw/` with the same column names as `delhivery_data.csv`. Then set `RAW_SHA256` in `src/config.py` to your file's fingerprint, or remove the check in `download_data.py`, and run the pipeline.

## Key results you should see

| Measure | Value |
|---|---|
| Legs analysed | 26,368 |
| Legs within SLA (≤ 2× plan) | 50.7% |
| Median actual vs planned time | 2.0× |
| FTL vs carting within SLA | 56.9% vs 43.8% |
| Worst / best origin state | West Bengal 26% / Kerala 72% |
| Model ROC AUC | 0.71 |
