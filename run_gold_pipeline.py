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

# Pipelines that OOM under the container's default memory limit.
# Use this for steps whose memory needs exceed what the container has
# (e.g. build_enhanced_cases.py's MERGE INTO step needs more headroom
# than a 3.7GB cgroup limit allows).
#
# LARGE_CONTAINER = True  → assume the container itself has enough memory
#                           now (e.g. you bumped its limit), so these run
#                           inside Docker as normal.
# LARGE_CONTAINER = False → route these to run on the HOST instead,
#                           bypassing the container's memory cap entirely.
LARGE_CONTAINER = False

# When LARGE_CONTAINER = True, the container's actual memory limit is
# checked at startup and must be at least this much, or we refuse to
# proceed silently into another OOM. Bump this if you raise the limit
# further and want a stricter floor. ~6GB default — comfortably above
# the 3.7GB that was previously OOM-ing on the MERGE INTO step.
MIN_MEMORY_BYTES_FOR_LARGE_CONTAINER = 6 * 1024**3

# Python interpreter to use for HOST_PIPELINES. Uses whatever interpreter
# is currently running this script (sys.executable).
#
# IMPORTANT: activate the environment that has duckdb/xgboost/pandas/numpy
# installed (the same one you use to run build_enhanced_cases.py
# standalone) before running run_gold_pipeline.py — HOST_PIPELINES will
# run under that same environment, unchecked.
HOST_PYTHON = sys.executable

HOST_PIPELINES = {
    "build_enhanced_cases.py",
}

# Containers belonging to the Kafka stack (see compose.yaml: zookeeper,
# kafka, init-kafka). None of the gold pipelines talk to Kafka, and on a
# memory-constrained machine these JVM services sit there eating Docker
# Desktop's shared VM memory pool for no benefit during this run. Stopped
# before any stage runs, so the gold pipelines get the VM to themselves.
# Stop order matters (init-kafka has nothing to stop; kafka depends on
# zookeeper, so kafka stops first to shut down cleanly).
KAFKA_STACK_CONTAINERS = ["kafka", "zookeeper"]
STOP_KAFKA_STACK_DURING_RUN = True

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


def get_compose_command() -> list[str]:
    """
    Return the right Docker Compose invocation for the OS this script runs on:
    the `docker compose` plugin on Linux, the standalone `docker-compose`
    binary elsewhere (Windows/macOS). Adjust here if your setup differs.
    """
    return ["docker", "compose"] if platform.system() == "Linux" else ["docker-compose"]


def build_command(pipeline: str) -> list[str]:
    """Build the subprocess command for a pipeline, routing to the correct machine."""
    if pipeline in HOST_PIPELINES and not LARGE_CONTAINER:
        # Run directly on the host (outside Docker) to avoid the container's
        # memory cap. Script paths are still resolved relative to its own
        # location, so this works as long as the host can see the same
        # data directory layout the container would (bind mount, etc.).
        return [HOST_PYTHON, str(PIPELINES_DIR / pipeline)]

    machine_idx = PIPELINE_MACHINE_MAP.get(pipeline, 0)
    machine = MACHINES[machine_idx]
    host = machine["host"]
    container = machine["container"]
    inner_cmd = ["docker", "exec", "-i", container, "python", f"gold/pipelines/{pipeline}"]

    if host == "localhost":
        return inner_cmd
    else:
        # SSH into remote host, then run docker exec there
        return ["ssh", host] + inner_cmd


def is_container_running(host: str, container: str) -> bool:
    """Check whether a container is running, locally or over SSH."""
    check_cmd = ["docker", "inspect", "-f", "{{.State.Running}}", container]
    if host != "localhost":
        check_cmd = ["ssh", host] + check_cmd

    result = subprocess.run(check_cmd, capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() == "true"


def get_container_memory_limit_bytes(host: str, container: str) -> int | None:
    """
    Return the container's hard memory limit in bytes, locally or over SSH.
    Returns 0 if Docker reports no limit set (i.e. limited only by host RAM).
    Returns None if the limit couldn't be determined (inspect failed/parsed badly).
    """
    check_cmd = ["docker", "inspect", "-f", "{{.HostConfig.Memory}}", container]
    if host != "localhost":
        check_cmd = ["ssh", host] + check_cmd

    result = subprocess.run(check_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def warn_if_large_container_assumption_is_wrong() -> None:
    """
    LARGE_CONTAINER=True means "trust the container has enough memory."
    That's just a flag — it doesn't itself raise any Docker memory limit.
    This checks the assumption actually holds before we run anything,
    instead of finding out via another OOM mid-pipeline.
    """
    if not LARGE_CONTAINER:
        return

    pipelines_needing_memory = HOST_PIPELINES
    if not pipelines_needing_memory:
        return

    # Every machine that could end up running one of HOST_PIPELINES
    # (defaults to machine 0 if unmapped — mirror build_command's logic).
    machines_to_check = set()
    for pipeline in pipelines_needing_memory:
        idx = PIPELINE_MACHINE_MAP.get(pipeline, 0)
        m = MACHINES[idx]
        machines_to_check.add((m["host"], m["container"]))

    problems = []
    for host, container in machines_to_check:
        limit = get_container_memory_limit_bytes(host, container)
        where = "locally" if host == "localhost" else f"on {host}"

        if limit is None:
            problems.append(
                f"  - '{container}' ({where}): could not determine memory limit "
                f"(is the container running and is Docker reachable?)"
            )
        elif limit == 0:
            # 0 means "no limit set" in Docker — effectively capped by host RAM,
            # which on a small machine is its own risk, so flag it rather than
            # assume it's fine.
            problems.append(
                f"  - '{container}' ({where}): no memory limit set on the "
                f"container (unbounded by Docker, capped only by host RAM)"
            )
        elif limit < MIN_MEMORY_BYTES_FOR_LARGE_CONTAINER:
            got_gb = limit / 1024**3
            need_gb = MIN_MEMORY_BYTES_FOR_LARGE_CONTAINER / 1024**3
            problems.append(
                f"  - '{container}' ({where}): memory limit is {got_gb:.1f}GB, "
                f"below the {need_gb:.1f}GB minimum expected for LARGE_CONTAINER=True"
            )

    if problems:
        print(
            "\n[ERROR] LARGE_CONTAINER=True, but the container memory limit "
            "doesn't back that up:"
        )
        for p in problems:
            print(p)
        print(
            "\nEither raise the container's memory limit (e.g. in "
            "docker-compose.yml: deploy.resources.limits.memory, or "
            "`docker update --memory <size> <container>`), or set "
            "LARGE_CONTAINER = False to run these pipelines on the host instead."
        )
        sys.exit(1)


def stop_kafka_stack() -> None:
    """
    Stop the Kafka/Zookeeper containers (local only — they're not part of
    the multi-machine MACHINES setup). Frees up Docker Desktop's shared VM
    memory pool for the gold pipelines, which don't need Kafka running.
    Safe to call even if they're already stopped or don't exist.
    """
    if not STOP_KAFKA_STACK_DURING_RUN:
        return

    print("\nStopping Kafka stack (not needed for this run)...")
    for container in KAFKA_STACK_CONTAINERS:
        result = subprocess.run(
            ["docker", "stop", container],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"  Stopped  : {container}")
        else:
            # Don't fail the whole run over this — most likely cause is
            # the container was already stopped or doesn't exist.
            print(f"  Skipped  : {container} ({result.stderr.strip() or 'not running'})")


def start_container(host: str, container: str) -> bool:
    """
    Try to bring up a container that isn't running, locally or over SSH.

    Two-step attempt:
      1. `docker start <container>` -- fast path, works if the container
         already exists but is just stopped.
      2. `docker compose up -d <container>` -- fallback for when the
         container doesn't exist yet (e.g. first run, or it was removed),
         using whichever compose syntax matches the OS this script runs on.

    Remote hosts only get step 1 over SSH: compose needs to run from the
    directory containing compose.yaml, and this script doesn't track a
    remote project path. If a remote container needs `compose up`, start
    it manually there first.

    Returns True if the container ends up running, False otherwise.
    """
    where = "locally" if host == "localhost" else f"on {host}"

    start_cmd = ["docker", "start", container]
    if host != "localhost":
        start_cmd = ["ssh", host] + start_cmd

    print(f"  Starting : '{container}' ({where}) via docker start...")
    subprocess.run(start_cmd, capture_output=True, text=True)
    if is_container_running(host, container):
        print(f"  Started  : {container}")
        return True

    if host != "localhost":
        print(
            f"  [ERROR] '{container}' ({where}) couldn't be started via "
            f"docker start, and remote 'compose up' isn't automated -- "
            f"start it manually on {host}."
        )
        return False

    print(f"  '{container}' not found or wouldn't start; trying docker compose up -d...")
    compose_cmd = get_compose_command() + ["up", "-d", container]
    result = subprocess.run(compose_cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [ERROR] docker compose up -d failed for '{container}':")
        print(f"    {result.stderr.strip()}")
        return False

    if is_container_running(host, container):
        print(f"  Started  : {container} (via compose)")
        return True

    print(f"  [ERROR] '{container}' still not running after compose up.")
    return False


def ensure_containers_running() -> None:
    """Preflight check: start any required container that isn't running, fail fast if it can't be."""
    seen = set()
    to_check = []

    for machine in MACHINES:
        key = (machine["host"], machine["container"])
        if key in seen:
            continue
        seen.add(key)
        to_check.append(machine)

    still_not_running = []
    for machine in to_check:
        host, container = machine["host"], machine["container"]
        if is_container_running(host, container):
            continue

        where = "locally" if host == "localhost" else f"on {host}"
        print(f"\n'{container}' ({where}) is not running -- attempting to start it...")
        if not start_container(host, container):
            still_not_running.append(machine)

    if still_not_running:
        print("\n[ERROR] The following containers could not be started:")
        for machine in still_not_running:
            where = "locally" if machine["host"] == "localhost" else f"on {machine['host']}"
            print(f"  - '{machine['container']}' ({where})")
        print("\nStart them manually before running the pipeline, e.g.:")
        for machine in still_not_running:
            if machine["host"] == "localhost":
                print(f"  docker start {machine['container']}")
                print(f"  (or: {' '.join(get_compose_command())} up -d)")
            else:
                print(f"  ssh {machine['host']} docker start {machine['container']}")
        sys.exit(1)


def run_pipeline(pipeline: str) -> str:
    cmd = build_command(pipeline)
    print(f"  Starting : {pipeline}")
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

    ensure_containers_running()
    stop_kafka_stack()
    warn_if_large_container_assumption_is_wrong()

    for i, stage_pipelines in enumerate(STAGES, start=1):
        try:
            run_stage(stage_pipelines, stage_num=i)
        except RuntimeError as e:
            print(f"\nAborting: {e}")
            sys.exit(1)

    print("\nAll Gold pipelines completed successfully.")


if __name__ == "__main__":
    main()