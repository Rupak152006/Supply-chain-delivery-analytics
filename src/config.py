"""Shared settings for the Delhivery delivery-analytics pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
MARTS = ROOT / "data" / "marts"
REPORTS = ROOT / "reports"
DB = PROC / "delivery.db"

DATA_URL = ("https://d2beiqkhq929f0.cloudfront.net/public_assets/assets/000/001/551/"
            "original/delhivery_data.csv?1642751181")
RAW_FILE = RAW / "delhivery_data.csv"
RAW_SHA256 = "203535609bb2e2fe60030705b18bb5a2685f137e81bcd3b16579b75891c40422"

# A leg meets SLA when its actual transit time is at most this multiple of the
# OSRM (open-source routing engine) drive-time estimate. The dataset carries no
# promised date, so this buffer stands in for one; change it here to re-run.
SLA_FACTOR = 2.0
# Hubs and corridors need this many legs before they are ranked.
MIN_LEGS_RANKED = 100
