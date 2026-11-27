"""Data-quality and KPI-logic tests against the loaded Delhivery warehouse."""
import sqlite3
import sys
from pathlib import Path
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from config import DB, MARTS, SLA_FACTOR  # noqa: E402


@pytest.fixture(scope="module")
def con():
    c = sqlite3.connect(DB)
    yield c
    c.close()


def q(con, sql):
    return con.execute(sql).fetchone()[0]


def test_leg_ids_unique(con):
    assert q(con, "SELECT COUNT(*) - COUNT(DISTINCT leg_id) FROM fact_leg") == 0


def test_every_raw_leg_loaded(con):
    raw = pd.read_csv(Path(DB).parents[1] / "raw" / "delhivery_data.csv",
                      usecols=["trip_uuid", "source_center", "destination_center"])
    assert q(con, "SELECT COUNT(*) FROM fact_leg") == raw.drop_duplicates().shape[0]


def test_no_orphan_keys(con):
    for col, dim, key in [("source_key", "dim_facility", "facility_key"),
                          ("destination_key", "dim_facility", "facility_key"),
                          ("route_key", "dim_route", "route_key"), ("trip_date_key", "dim_date", "date_key")]:
        assert q(con, f"SELECT COUNT(*) FROM fact_leg f LEFT JOIN {dim} d ON d.{key} = f.{col} "
                      f"WHERE d.{key} IS NULL") == 0, col


def test_times_positive_and_ordered(con):
    assert q(con, "SELECT COUNT(*) FROM fact_leg WHERE actual_time_min <= 0 OR osrm_time_min <= 0") == 0
    assert q(con, "SELECT COUNT(*) FROM fact_leg WHERE leg_end_at < leg_start_at") == 0


def test_sla_flag_matches_ratio(con):
    assert q(con, f"SELECT COUNT(*) FROM fact_leg WHERE meets_sla <> (delay_ratio <= {SLA_FACTOR} + 1e-9)") == 0


def test_handling_not_negative(con):
    assert q(con, "SELECT COUNT(*) FROM fact_leg WHERE handling_min < 0") == 0


def test_route_types_known(con):
    assert {r[0] for r in con.execute("SELECT DISTINCT route_type FROM fact_leg")} <= {"FTL", "Carting"}


def test_daily_legs_sum_to_total(con):
    daily = pd.read_csv(MARTS / "daily.csv")
    assert daily.legs.sum() == q(con, "SELECT COUNT(*) FROM fact_leg")


def test_overall_sla_matches_fact(con):
    overall = pd.read_csv(MARTS / "overall.csv").iloc[0]
    assert abs(overall.sla_rate - q(con, "SELECT AVG(meets_sla) FROM fact_leg")) < 1e-4


def test_rates_between_zero_and_one():
    for f in ["daily", "route_type", "distance_band", "hour", "state", "corridor", "hub"]:
        df = pd.read_csv(MARTS / f"{f}.csv")
        assert df.sla_rate.between(0, 1).all(), f
