import pandas as pd
import json
import time
from kafka import KafkaProducer

# --- CONFIGURATION ---
CSV_PATH = "l1_day.csv"
KAFKA_TOPIC = "mock_l1_stream"
BOOTSTRAP_SERVERS = ["localhost:9092"]
SIMULATION_START = "2024-08-01T13:36:32Z"
SIMULATION_END = "2024-08-01T13:45:14Z"
SLEEP_SCALE = 1.0  # Use < 1.0 for faster simulation

# --- INIT KAFKA PRODUCER ---
producer = KafkaProducer(
    bootstrap_servers=BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)

# --- LOAD AND FILTER DATA ---
df = pd.read_csv(CSV_PATH)

# Convert timestamps
df["ts_event"] = pd.to_datetime(df["ts_event"])

# Filter time window
start_ts = pd.to_datetime(SIMULATION_START)
end_ts = pd.to_datetime(SIMULATION_END)
df = df[(df["ts_event"] >= start_ts) & (df["ts_event"] <= end_ts)]

# Sort for proper stream order
df = df.sort_values("ts_event")

# --- STREAM TO KAFKA ---
last_ts = None

for current_ts, group in df.groupby("ts_event"):
    # Simulate real-time pacing
    if last_ts is not None:
        delta = (current_ts - last_ts).total_seconds()
        time.sleep(delta * SLEEP_SCALE)
    last_ts = current_ts

    # Build snapshot per venue
    snapshots = []
    for _, row in group.iterrows():
        snapshots.append(
            {
                "publisher_id": row["publisher_id"],
                "ask_px": row["ask_px_00"],
                "ask_sz": row["ask_sz_00"],
            }
        )

    # Final message structure
    message = {"timestamp": current_ts.isoformat(), "snapshots": snapshots}

    # Publish to Kafka
    producer.send(KAFKA_TOPIC, value=message)
    print(f"Published {len(snapshots)} snapshots at {current_ts}")

# --- CLEANUP ---
producer.flush()
producer.close()
print("Kafka stream finished.")
