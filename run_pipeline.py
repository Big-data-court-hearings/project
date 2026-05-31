import subprocess
import time
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

PIPELINES_DIR = (
    PROJECT_ROOT
    / "gold"
    / "pipelines"
)

PIPELINES = [
    "build_case_metrics.py",
    "build_metrics.py",
    "build_quarter_metrics.py"
    "build_temporal_metrics.py",
    "build_backlog_metrics.py",
    "build_clearance_rate.py",
    "build_duration_metrics.py",
    "build_court_performance.py",
    "build_advanced_metrics.py"
]

def main():
    print("Starting Docker Compose containers...")
    answered = False
    while not answered:
        question = input("Is this the first time you use this programme? (y/n): ")
        if question.lower() in ["yes", "y"]:
            docker_process = subprocess.Popen(
                ["docker-compose", "up", "--build", "-d"],
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            time.sleep(120)
            answered = True
        elif question.lower() in ["no", "n"]:
            docker_process = subprocess.Popen(
                ["docker-compose", "up", "-d"],
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            time.sleep(5)
            answered = True
        else:
            print("I didn't understand. Let's retry")


    try:
        # 1. START THE PRODUCER
        print("Starting the Producer script to fetch data from API...")
        subprocess.run(["python", str(PROJECT_ROOT / "ingestion" / "kafkaProducer.py")], check=True)
        print("Producer completed its run and successfully pushed page data to Bronze.")

        # 2. START THE SILVER LAYER
        print("Starting Kafka to Silver ingestion script...")
        subprocess.run(["python", str(PROJECT_ROOT / "processing" / "kafkaToSilver.py")], check=True)
        print("Silver cleaner completed processing.")

        print("\nInitiating Gold Analytical Pipelines...")
        for pipeline in PIPELINES:
            pipeline_path = PIPELINES_DIR / pipeline

            print("\n" + "=" * 60)
            print(f"Running: {pipeline}")
            print("=" * 60)

            # Using sys.executable guarantees it uses your exact miniconda environment Python
            result = subprocess.run(
                [sys.executable, str(pipeline_path)],
                cwd=PROJECT_ROOT  # Now a valid directory folder!
            )

            if result.returncode != 0:
                print(f"\nPipeline failed: {pipeline}")
                sys.exit(1)

        print("\nAll Gold pipelines completed successfully.")

    except subprocess.CalledProcessError as e:
        print(f"A pipeline component script failed: {e}")
    except KeyboardInterrupt:
        print("\nPipeline stopped by user control.")
    finally:
        # Gracefully shut down Docker whether things finished perfectly or crashed
        print("Shutting down Docker containers...")
        docker_process.terminate()
        docker_process.wait()
        print("Cleaned up successfully.")

if __name__ == "__main__":
    main()