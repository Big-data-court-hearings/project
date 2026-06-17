import subprocess
import sys
import platform
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_ROOT = Path(__file__).resolve().parent
PIPELINES_DIR = PROJECT_ROOT / "gold" / "pipelines"

# Multi-machine configuration.
# For single-machine usage, keep one entry with host="localhost".
# For multi-machine, add entries with the remote host IP and container name.
# Requires passwordless SSH to be configured on remote hosts.
MACHINES = [
    {"host": "localhost", "container": "court_hearings_bdt"},
    # {"host": "192.168.1.11", "container": "court_hearings_bdt"},
]

# Assign heavier pipelines to specific machines (by index in MACHINES).
# If a pipeline is not listed here, it defaults to machine 0.
PIPELINE_MACHINE_MAP = {
    "build_longitudinal_analysis.py": 0,
    "build_duration_metrics.py":      1 % len(MACHINES),  # falls back to 0 if only one machine
    "build_temporal_metrics.py":      0,
    "build_metrics.py":               1 % len(MACHINES),
    "build_court_backlog.py":         0,
    "build_juris_backlog.py":         1 % len(MACHINES),
}

# Stage definitions — order matters, stages run sequentially,
# pipelines within a stage run in parallel.
STAGES = [
    ["build_enhanced_cases.py"],
    [
        "build_metrics.py",
        "build_temporal_metrics.py",
        "build_longitudinal_analysis.py",
        "build_duration_metrics.py",
        "build_court_backlog.py",
        "build_juris_backlog.py",
    ],
    ["build_circuit_backlog.py"],
]


def build_command(pipeline: str) -> list[str]:
    """Build the subprocess command for a pipeline, routing to the correct machine."""
    machine_idx = PIPELINE_MACHINE_MAP.get(pipeline, 0)
    machine = MACHINES[machine_idx]
    host = machine["host"]
    container = machine["container"]
    docker_cmd = ["docker", "compose"] if platform.system() == "Linux" else ["docker-compose"]
    inner_cmd = ["docker", "exec", "-i", container, "python", f"gold/pipelines/{pipeline}"]

    if host == "localhost":
        return inner_cmd
    else:
        # SSH into remote host, then run docker exec there
        return ["ssh", host] + inner_cmd


def run_pipeline(pipeline: str) -> str:
    cmd = build_command(pipeline)
    print(f"  Starting : {pipeline} → {cmd}")
    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        stdout=sys.stdout,
        stderr=sys.stderr
    )
    if result.returncode != 0:
        raise RuntimeError(f"Pipeline failed: {pipeline}")
    return pipeline


def run_stage(pipelines: list[str], stage_num: int) -> None:
    print(f"\n{'='*60}")
    print(f"Stage {stage_num}: {len(pipelines)} pipeline(s)")
    print(f"{'='*60}")

    failures = []
    with ThreadPoolExecutor(max_workers=len(pipelines)) as executor:
        futures = {executor.submit(run_pipeline, p): p for p in pipelines}
        for future in as_completed(futures):
            try:
                done = future.result()
                print(f"  Completed: {done}")
            except RuntimeError as e:
                failures.append(str(e))
                print(f"  FAILED   : {e}")

    if failures:
        raise RuntimeError(f"Stage {stage_num} failed: {failures}")


def main():
    print("\nInitiating Gold Analytical Pipelines...")
    print(f"Machines available: {[m['host'] for m in MACHINES]}")

    for i, stage_pipelines in enumerate(STAGES, start=1):
        try:
            run_stage(stage_pipelines, stage_num=i)
        except RuntimeError as e:
            print(f"\nAborting: {e}")
            sys.exit(1)

    print("\nAll Gold pipelines completed successfully.")


if __name__ == "__main__":
    main()