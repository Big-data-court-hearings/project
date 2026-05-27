"""
Gold layer orchestration pipeline.

Runs all Gold analytical pipelines sequentially.
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PIPELINES_DIR = (
    PROJECT_ROOT
    / "gold"
    / "pipelines"
)

PIPELINES = [

    "build_case_metrics.py",

    "build_metrics.py",

    "build_temporal_metrics.py",

    "build_backlog_metrics.py",

    "build_clearance_rate.py",

    "build_duration_metrics.py",

    "build_court_performance.py"
]

# ============================================================
# RUN PIPELINES
# ============================================================

for pipeline in PIPELINES:

    pipeline_path = PIPELINES_DIR / pipeline

    print("\n" + "=" * 60)
    print(f"Running: {pipeline}")
    print("=" * 60)

    result = subprocess.run(
        [sys.executable, str(pipeline_path)],
        cwd=PROJECT_ROOT
    )

    if result.returncode != 0:

        print(f"\nPipeline failed: {pipeline}")

        sys.exit(1)

print("\nAll Gold pipelines completed successfully.")