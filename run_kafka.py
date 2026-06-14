import subprocess
import sys
from pathlib import Path
import platform
DOCKER_COMMAND = ["docker-compose"] if platform.system() != "Linux" else ["docker", "compose"]
PROJECT_ROOT = Path(__file__).resolve().parent


HOURS = 12

def ask_date():
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
            print("Building and starting containers...")
            subprocess.run([*DOCKER_COMMAND, "up", "--build", "-d"], check=True)
            answered = True
        elif question.lower() in ["yes", "y"]:
            print("Starting existing containers...")
            subprocess.run([*DOCKER_COMMAND, "up", "-d"], check=True)
            answered = True
        else:
            print("I didn't understand. Let's retry")

    try:
        date_focus = ask_date()

        # 1. START THE PRODUCER (Non-blocking using subprocess.Popen)
        print("\nLaunching Producer in the background...")

        # Build the producer command. If USE_LAST_UPDATE is enabled in the
        # producer config, omit --start-date entirely so the producer falls
        # back to its own last_update.json checkpoint; otherwise pass the
        # interactively chosen focus date as before.
        try:
            from ingestion.kafkaProducer import USE_LAST_UPDATE
        except ImportError:
            USE_LAST_UPDATE = False

        producer_cmd = ["docker", "exec", "court_hearings_bdt",
                        "python", "ingestion/kafkaProducer.py"]

        if USE_LAST_UPDATE:
            print("USE_LAST_UPDATE is enabled — producer will resume from its last recorded update.")
        else:
            print(f"USE_LAST_UPDATE is disabled — using focus date: {date_focus}")
            producer_cmd += ["--start-date", date_focus]

        # Note the removal of '-i' so it can run safely detached from this script's TTY
        producer_process = subprocess.Popen(producer_cmd)

        # 2. START THE SILVER LAYER (Non-blocking using subprocess.Popen)
        print("Launching Kafka to Silver consumer in the background...")
        consumer_process = subprocess.Popen(
            ["docker", "exec", "court_hearings_bdt", "python", "processing/kafkaToSilver.py"]
        )        

        print("\n>>> BOTH PRODUCER AND CONSUMER ARE RUNNING SIMULTANEOUSLY! <<<")
        print("To view the Producer, open a new terminal and run: docker logs -f court_hearings_bdt (or check your script output)")
        print("Press Ctrl+C in this terminal when you are ready to stop them and proceed to Gold pipelines.")
        
        # Keep the script alive while they run side-by-side
        try:
            producer_process.wait()
            consumer_process.wait()
        except KeyboardInterrupt:
            print("\nStopping streaming layers.")
            producer_process.terminate()
            consumer_process.terminate()

    except subprocess.CalledProcessError as e:
        print(f"A pipeline component script failed: {e}")
        print("Shutting down Docker containers...")
        subprocess.run([*DOCKER_COMMAND, "down"])
    except KeyboardInterrupt:
        print("\nPipeline stopped by user control.")
        subprocess.run([*DOCKER_COMMAND, "down"])

if __name__ == "__main__":
    main()