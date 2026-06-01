import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

PIPELINES_DIR = (
    PROJECT_ROOT
    / "gold"
    / "pipelines2"
)

# FIXED: Added missing comma to prevent string concatenation bug
PIPELINES = [
    "build_case_metrics.py",
    "build_metrics.py",
    "build_temporal_metrics.py",
    "build_longitudinal_analysis.py",
    "build_duration_metrics.py",
    "build_court_backlog.py",
    "build_backlog_metrics.py",
    "build_clearance_rate.py",
    "build_court_performance.py",
    "build_advanced_metrics.py"
]

HOURS = 2

def ask_date():
    """Chiede la data all'utente nel terminale locale, prima di entrare in Docker."""
    from datetime import datetime, timedelta
    default = (datetime.today() - timedelta(hours=HOURS)).strftime('%Y-%m-%dT%H:%M:%S')
    
    answered = False
    while not answered:
        print("Considering Courtlistener updates at around 2AM in Italy, please answer the following question.")
        response = input(f"\nCurrent focus date: {HOURS} hours ago ({default}). Do you want to use a different one (y/n): ")
        if response.lower() == "n":
            return default
        elif response.lower() == "y":
            raw = input("Please, enter a date in the 'YYYY-MM-DDTHH:MM:SS' format:\n")
            try:
                datetime.strptime(raw, '%Y-%m-%dT%H:%M:%S')
                return raw
            except ValueError:
                print("Format not valid. Please, retry.")
        else:
            print("Digit 'y' or 'n'.")

def main():
    print("Starting Docker Compose containers...")
    answered = False
    
    while not answered:
        question = input("Has the docker container already been configured? (y/n): ")
        if question.lower() in ["no", "n"]:
            print("Building and starting containers. This will wait until completion...")
            # FIXED: Using subprocess.run ensures Python stops here until Docker finishes building
            subprocess.run(
                ["docker-compose", "up", "--build", "-d"],
                check=True,
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            answered = True
        elif question.lower() in ["yes", "y"]:
            print("Starting existing containers...")
            subprocess.run(
                ["docker-compose", "up", "-d"],
                check=True,
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            answered = True
        else:
            print("I didn't understand. Let's retry")

    try:
        # 1. START THE PRODUCER
        # This will ONLY run after the subprocess.run functions above finish successfully!
        print("\nDocker is up! Starting the Producer script to fetch data from API...")
        date_focus = ask_date()

        # 1. START THE PRODUCER — passa la data come argomento
        subprocess.run(
            ["docker", "exec", "-i", "court_hearings_bdt", 
            "python", "ingestion/kafkaProducer.py", "--start-date", date_focus], 
            check=True)
        print("Producer completed its run and successfully pushed page data to Bronze.")

        # 2. START THE SILVER LAYER
        print("Starting Kafka to Silver ingestion script...")
        subprocess.run(
                    ["docker", "exec", "-i", "court_hearings_bdt", "python", "processing/kafkaToSilver.py"], 
                    check=True)        
        print("Silver cleaner completed processing.")

        print("\nInitiating Gold Analytical Pipelines...")
        for pipeline in PIPELINES:
            pipeline_path = f"gold/pipelines2/{pipeline}"

            print("\n" + "=" * 60)
            print(f"Running: {pipeline}")
            print("=" * 60)

            result = subprocess.run(
                ["docker", "exec", "-i", "court_hearings_bdt",
                "python", pipeline_path],
                cwd=PROJECT_ROOT
            )

            if result.returncode != 0:
                print(f"\nPipeline failed: {pipeline}")
                sys.exit(1)

        print("\nAll Gold pipelines completed successfully.")

    except subprocess.CalledProcessError as e:
        print(f"A pipeline component script failed: {e}")
        print("Shutting down Docker containers...")
        subprocess.run(["docker-compose", "down"], stdout=sys.stdout, stderr=sys.stderr)
        print("Cleaned up successfully.")

    except KeyboardInterrupt:
        print("\nPipeline stopped by user control.")
        print("Shutting down Docker containers...")
        subprocess.run(["docker-compose", "down"], stdout=sys.stdout, stderr=sys.stderr)
        print("Cleaned up successfully.")

if __name__ == "__main__":
    main()