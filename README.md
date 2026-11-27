# Supply-Chain Delivery Analytics: Delhivery India

An end-to-end analytics project on **real Indian logistics data**: Delhivery's public trip dataset (144,867 checkpoint rows, 14,817 trips, 26,368 legs between 1,657 facilities, 12 Sep – 3 Oct 2018). It goes from raw download to a star-schema warehouse, a KPI layer in SQL, an SLA-breach risk model, a BI dashboard and a written report.

```
download (checksum) ──► ETL: clean, roll checkpoints up to legs ──► SQLite star schema ──► KPI views (SQL)
 download_data.py           etl.py                                   delivery.db           kpi_views.sql
                                                                                               │
                              BI dashboard ◄── CSV marts ◄── build_marts.py ◄──────────────────┤
                                                                                               └─► late_risk_model.py
```

## Run it

New to this? Follow [docs/STEP_BY_STEP.md](docs/STEP_BY_STEP.md).

```bash
pip install -r requirements.txt
python run_pipeline.py        # download → ETL → marts → model → dashboard → tests
```

The download step fetches the public CSV and verifies its SHA-256. If the file is already in `data/raw/`, it is reused.

## The SLA definition

The dataset has no promised delivery dates. Each leg carries an **OSRM estimate**: the drive time an open-source routing engine predicts. A leg is **within SLA** when its actual transit time is at most `SLA_FACTOR` × that estimate. The default is 2.0, set in `src/config.py`; change it and rerun to test a stricter or looser target.

## Project layout

| Path | What it does |
|---|---|
| `src/config.py` | Paths, data URL and checksum, `SLA_FACTOR`, ranking threshold |
| `src/download_data.py` | Downloads and verifies the raw Delhivery file |
| `src/etl.py` | Cleans checkpoints, fills missing names, rolls up to legs, parses facility city, state and type, then loads the star schema and writes `reports/data_quality_report.csv` |
| `sql/schema.sql` | `fact_leg` plus `dim_facility`, `dim_route`, `dim_date` |
| `sql/kpi_views.sql` | `vw_leg` and the `mart_*` views: daily, route type, distance band, hour, day of week, state, corridor, hub |
| `src/build_marts.py` | Exports marts to `data/marts/*.csv` and adds medians |
| `src/late_risk_model.py` | Logistic regression for SLA breach at dispatch, validated on a time split |
| `src/build_dashboard.py` | Builds `dashboard/delhivery_dashboard.html` (offline, open in any browser) and `dashboard/delhivery_marts.xlsx` (for Power BI, Tableau or Excel) |
| `tests/test_data_quality.py` | 10 checks: unique legs, every raw leg loaded, keys, time order, SLA flag logic, mart totals |
| `dashboard/claude_artifact_page.html` | Source of the online Claude dashboard page |
| `reports/Delhivery_India_Delivery_Report.pdf` | The written report (8 pages, with charts) |
| `docs/STEP_BY_STEP.md` | Step-by-step guide to rebuild everything yourself |
| `legacy_synthetic/` | The earlier synthetic-data version of the pipeline, kept for reference |

## Key findings

1. **Plans are badly calibrated.** Only 50.7% of legs finish within 2× the OSRM estimate. The median leg takes 2.0× plan, and only 1.8% beat it.
2. **Geography drives performance.** Legs from West Bengal (26%), Bihar (28%), Assam (28%) and Maharashtra (29%) rarely meet the SLA. Kerala (72%), Punjab (67%) and Karnataka (65%) lead.
3. **A few hubs drag the network.** Mumbai Hub is at 13%, Kolkata Dankuni at 20% and Bhiwandi at 30%; Bhiwandi sends 821 legs.
4. **Carting, short and early-morning legs lag.** Carting is at 44% vs 57% for FTL. Carting legs under 25 km are at 35%. Legs starting 04:00–09:00 are at 41%, against 59% for evening starts.
5. **Breaches are partly predictable.** ROC AUC is 0.71. The riskiest 10% of legs breach 78% of the time, against 49% overall.

## Recommendations

- Recalibrate planned times by corridor and route type
- Run a hub turnaround programme at Mumbai Hub, Bhiwandi and Kolkata Dankuni
- Review eastern operations (West Bengal, Bihar, Assam)
- Move carting dispatch out of the 04:00–09:00 window where possible
- Score legs at dispatch and alert on the riskiest 10%

## Limitations

The data covers three weeks in 2018, with no promised dates, customer outcomes or costs. It measures movement against plan, not customer-facing on-time delivery. Facility types are parsed from naming codes.
