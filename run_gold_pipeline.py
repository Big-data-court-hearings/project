import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

PIPELINES_DIR = PROJECT_ROOT / "gold" / "pipelines"

PIPELINES = [
    "build_enhanced_cases.py",
    "build_metrics.py",
    "build_temporal_metrics.py",
    "build_longitudinal_analysis.py",
    "build_duration_metrics.py",
    "build_court_backlog.py",
    "build_circuit_backlog.py"
    ]

def main():
    print("\nInitiating Gold Analytical Pipelines...")
    for pipeline in PIPELINES:
        pipeline_path = f"gold/pipelines/{pipeline}"
        print("\n" + "=" * 60)
        print(f"Running: {pipeline}")
        print("=" * 60)

        # Added stdout=sys.stdout and stderr=sys.stderr to guarantee logs print directly
        result = subprocess.run(
            ["docker", "exec", "-i", "court_hearings_bdt", "python", pipeline_path],
            cwd=PROJECT_ROOT,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        
        if result.returncode != 0:
            print(f"\nPipeline failed: {pipeline}")
            sys.exit(1)

    print("\nAll Gold pipelines completed successfully.")

if __name__ == "__main__":
    main()