"""
Generic API client for CourtListener ingestion.

Responsibilities:
- API communication
- pagination handling
- retry logic
- error handling

This module is intentionally generic so it can
be reused for multiple endpoints:
- dockets
- courts
- appeals
- events
"""

import time
import logging
from typing import List, Dict, Optional

import requests

from ingestion.config import (
    BASE_URL,
    HEADERS,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
)

# ============================================================
# LOGGING CONFIGURATION
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# ============================================================
# GENERIC PAGINATED FETCH FUNCTION
# ============================================================

def fetch_paginated_data(
    endpoint: str,
    max_records: Optional[int] = None
) -> List[Dict]:
    """
    Fetch paginated data from CourtListener API.

    Parameters
    ----------
    endpoint : str
        API endpoint (example: 'dockets/').

    max_records : Optional[int]
        Maximum number of records to fetch.

    Returns
    -------
    List[Dict]
        List of JSON records returned by the API.
    """

    url = f"{BASE_URL}/{endpoint}"
    all_records = []

    logger.info(f"Starting ingestion for endpoint: {endpoint}")

    while url:

        success = False

        # ====================================================
        # RETRY LOOP
        # ====================================================

        for attempt in range(MAX_RETRIES):

            try:
                response = requests.get(
                    url,
                    headers=HEADERS,
                    timeout=REQUEST_TIMEOUT
                )

                response.raise_for_status()

                data = response.json()

                success = True
                break

            except requests.RequestException as error:

                logger.warning(
                    f"Request failed "
                    f"(attempt {attempt + 1}/{MAX_RETRIES}) : {error}"
                )

                time.sleep(2)

        # ====================================================
        # STOP IF ALL RETRIES FAILED
        # ====================================================

        if not success:
            logger.error("Pipeline stopped after repeated failures.")
            break

        # ====================================================
        # EXTRACT RESULTS
        # ====================================================

        results = data.get("results", [])

        all_records.extend(results)

        logger.info(
            f"Downloaded {len(all_records)} total records"
        )

        # ====================================================
        # STOP CONDITION
        # ====================================================

        if max_records and len(all_records) >= max_records:
            logger.info("Maximum record limit reached.")
            all_records = all_records[:max_records]
            break

        # ====================================================
        # PAGINATION
        # ====================================================

        url = data.get("next")

    logger.info(
        f"Ingestion completed successfully : "
        f"{len(all_records)} records fetched"
    )

    return all_records