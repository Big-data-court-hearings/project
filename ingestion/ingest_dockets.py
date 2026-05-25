"""
Docket ingestion script.

Downloads docket data from CourtListener API
and stores raw JSONL data in the Bronze layer.
"""

import json

from ingestion.api_client import fetch_paginated_data

from ingestion.config import (
    DOCKETS_PATH,
    MAX_RECORDS
)

# ============================================================
# FETCH DOCKET DATA
# ============================================================

dockets = fetch_paginated_data(
    endpoint="dockets/",
    max_records=MAX_RECORDS
)

# ============================================================
# OUTPUT FILE
# ============================================================

output_file = DOCKETS_PATH / "dockets_raw.jsonl"

# ============================================================
# SAVE JSONL
# ============================================================

with open(output_file, "w", encoding="utf-8") as file:

    for row in dockets:
        file.write(json.dumps(row) + "\n")

# ============================================================
# FINAL LOG
# ============================================================

print(f"\nSaved {len(dockets)} records")
print(f"Output file : {output_file}")