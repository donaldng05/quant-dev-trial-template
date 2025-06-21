Understood! Here's **everything in one clean Markdown block** – no shell formatting, just a single copy-paste-friendly `README.md` section:

---

```markdown
# Blockhouse Work Trial Repo

This repository consists of the following components:

1. **Benchmarks** – Code for TWAP and VWAP strategies.  
2. **Cost Calculations** – Code for calculating various costs within the rewards component.  
3. **Datasets** – Example datasets used in the backtesting pipeline.  
4. **Kafka Producer** – Simulates streaming market snapshots via Kafka.  
5. **Backtest Engine** – Consumes snapshots and performs SOR backtesting.  

---

## ✅ Local Functionality

The entire pipeline (Kafka producer → backtester) has been verified **end-to-end on local setup**:

- Kafka topic is created locally.  
- Snapshots are streamed via `kafka_producer.py`.  
- `backtest.py` consumes and processes the snapshots, outputs results.  
- Output files include cost analysis and savings visualization (`savings_plot.png`).  

---

## ⚠️ EC2 Deployment Notes

Due to persistent system-level issues with the package manager on an EC2 instance (specifically related to `apt`, `venv`, and `pip` under PEP 668 protections), the full Kafka + Python pipeline **was not able to run successfully on EC2**.

However, the following setup was completed on EC2:

- ✅ EC2 instance launched (Ubuntu, t3.micro)  
- ✅ Kafka downloaded and Zookeeper + Broker started  
- ✅ Project code transferred and structured  
- ⚠️ Python environment setup partially blocked by `pip` system restriction  
- ⚠️ Kafka client connection failed due to heap/memory limits and dependency errors  

---

## 📦 Project Structure

```

sor-project/
├── allocator\_pseudocode.txt
├── backtest.py
├── kafka\_producer.py
├── l1\_day.csv
├── l1\_inspect.ipynb
├── docker-compose.yml
├── README.md
├── results.json
├── savings\_plot.png
├── sor-backtest.pem
└── grid\_results.json

````

---

## 💻 How to Run (Locally)

1. **Create virtual environment**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install kafka-python matplotlib pandas
    ```

2. **Start Kafka (in separate terminals)**:
    ```bash
    # Terminal 1
    bin/zookeeper-server-start.sh config/zookeeper.properties

    # Terminal 2
    bin/kafka-server-start.sh config/server.properties
    ```

3. **Create Kafka topic**:
    ```bash
    bin/kafka-topics.sh --create --topic test-topic --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
    ```

4. **Run Producer**:
    ```bash
    python kafka_producer.py
    ```

5. **Run Backtester**:
    ```bash
    python backtest.py
    ```

6. **Inspect Output**:
    - `results.json`: SOR output
    - `savings_plot.png`: Cost savings visualization

---

## 🛠 EC2 Setup Instructions (Reference Only)

Steps used for deployment on AWS EC2 (Ubuntu 22.04):

```bash
# Launch t3.micro instance from AWS Console
# SSH into EC2
ssh -i sor-backtest.pem ubuntu@<public-ip>

# Install Java
sudo apt update && sudo apt install default-jdk -y

# Download and extract Kafka
wget https://archive.apache.org/dist/kafka/3.6.0/kafka_2.13-3.6.0.tgz
tar -xzf kafka_2.13-3.6.0.tgz
cd kafka_2.13-3.6.0

# Start services in separate terminals
bin/zookeeper-server-start.sh config/zookeeper.properties
bin/kafka-server-start.sh config/server.properties

# Transfer project code
scp -i sor-backtest.pem -r ./quant-dev-trial-template ubuntu@<public-ip>:~/sor-project
````

> ⚠️ Full Kafka pipeline not functional due to Python install restrictions and memory limits on EC2.

---

## 📎 Notes

* The allocator logic follows the pseudocode in `allocator_pseudocode.txt`.
* Future improvements may include Dockerized Kafka setup, better error handling, and performance optimizations.

```

