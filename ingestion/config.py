"""
Central configuration file for the CourtListener ingestion pipeline.

This module centralizes:
- API configuration
- authentication
- ingestion parameters
- project paths
- Bronze / Silver / Gold storage paths
"""

from pathlib import Path
import os

from dotenv import load_dotenv

# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

# ============================================================
# PROJECT ROOT
# ============================================================

# Robust project root detection
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ============================================================
# STORAGE LAYERS
# ============================================================

# Bronze layer
BRONZE_PATH = PROJECT_ROOT / "bronze"

DOCKETS_PATH = BRONZE_PATH / "dockets"
COURTS_PATH = BRONZE_PATH / "courts"
APPEALS_PATH = BRONZE_PATH / "appeals"

# Silver layer
SILVER_PATH = PROJECT_ROOT / "silver"

# Gold layer
GOLD_PATH = PROJECT_ROOT / "gold" / "metrics"

# ============================================================
# CREATE DIRECTORIES AUTOMATICALLY
# ============================================================

DOCKETS_PATH.mkdir(parents=True, exist_ok=True)
COURTS_PATH.mkdir(parents=True, exist_ok=True)
APPEALS_PATH.mkdir(parents=True, exist_ok=True)

SILVER_PATH.mkdir(parents=True, exist_ok=True)
(PROJECT_ROOT / "gold").mkdir(
    parents=True,
    exist_ok=True
)

GOLD_PATH.mkdir(
    parents=True,
    exist_ok=True
)

# ============================================================
# API CONFIGURATION
# ============================================================

API_TOKEN = os.getenv("COURTLISTENER_TOKEN")

if API_TOKEN is None:
    raise ValueError(
        "COURTLISTENER_TOKEN not found in .env file."
    )

BASE_URL = "https://www.courtlistener.com/api/rest/v4"

HEADERS = {
    "Authorization": f"Token {API_TOKEN}"
}

# ============================================================
# INGESTION PARAMETERS
# ============================================================

# Maximum number of records to fetch
MAX_RECORDS = 1000

# Timeout for API requests (seconds)
REQUEST_TIMEOUT = 30

# Retry attempts before failure
MAX_RETRIES = 3

# Delay between requests (seconds)
REQUEST_SLEEP = 0.5