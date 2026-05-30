import subprocess
import time
import sys

def main():
    print("Starting Docker Compose containers...")
    answered = False
    while not answered:
        question = input("Is this the first time you use this programme? 'y' or 'n': ")
        if question.lower() in ["yes", "y"]:
            docker_process = subprocess.Popen(
                ["docker-compose", "up", "--build"],
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            answered = True
        elif question.lower() in ["no", "n"]:
            docker_process = subprocess.Popen(
                ["docker-compose", "up"],
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            answered = True
        else:
            print("I didn't understand. Let's retry")

    # Give Docker a few seconds to spin up Kafka brokers before producing
    print("⏳ Waiting 20 seconds for services to initialize...")
    time.sleep(20) 

    try:
        # 1. START THE PRODUCER (subprocess.run blocks until the producer is 100% finished)
        print("🚀 Starting the Producer script to fetch data from API...")
        subprocess.run(["python", "ingestion/kafkaProducer.py"], check=True)
        print("✅ Producer completed its run and successfully pushed page data to Bronze.")

        # 2. START THE SILVER LAYER (Only starts now because the line above finished)
        print("📥 Starting Kafka to Silver ingestion script...")
        subprocess.run(["python", "processing/kafkaToSilver.py"], check=True)
        print("✅ Silver cleaner completed processing.")

    except subprocess.CalledProcessError as e:
        print(f"❌ A pipeline component script failed: {e}")
    except KeyboardInterrupt:
        print("\n👋 Pipeline stopped by user control.")
    finally:
        # Gracefully shut down Docker whether the scripts finished perfectly or crashed
        print("🛑 Shutting down Docker containers...")
        docker_process.terminate()
        docker_process.wait()
        print("✅ Cleaned up successfully.")

if __name__ == "__main__":
    main()