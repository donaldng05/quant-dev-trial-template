from kafka import KafkaConsumer
import json
import math
from itertools import product
import matplotlib.pyplot as plt
import pandas as pd
import random

# --- CONFIGURATION ---
KAFKA_TOPIC = "mock_l1_stream"
BOOTSTRAP_SERVERS = ["localhost:9092"]
GROUP_ID = "sor-backtest"
ORDER_SIZE = 5000


# --- ALLOCATOR FUNCTIONS ---
def compute_cost(split, venues, order_size, lambda_over, lambda_under, theta_queue):
    executed = 0
    cash_spent = 0.0
    queue_penalty = 0.0

    for i in range(len(venues)):
        venue = venues[i]
        queue = venue.get("queue_pos", 0)
        liquidity = venue["ask_sz"]

        # Only fills if you're ahead in queue
        fillable = max(0, liquidity - queue)
        fill = min(split[i], fillable)

        executed += fill
        cost = fill * (venue["ask_px"] + venue.get("fee", 0.0))
        rebate = (split[i] - fill) * venue.get("rebate", 0.0)
        cash_spent += cost - rebate

        queue_penalty += (
            theta_queue * split[i] * queue
        )  # Penalize orders behind large queues

    underfill = max(order_size - executed, 0)
    overfill = max(executed - order_size, 0)

    cost_penalty = lambda_under * underfill + lambda_over * overfill
    total_cost = cash_spent + cost_penalty + queue_penalty

    print(f"Split: {split}")
    print(f"  Fill: {executed}")
    print(f"  Underfill: {underfill}, Overfill: {overfill}")
    print(
        f"  Cash: {cash_spent:.2f}, Queue Penalty: {queue_penalty:.2f}, Total Cost: {total_cost:.2f}"
    )

    return total_cost


def allocate(order_size, venues, lambda_over, lambda_under, theta_queue, step=100):
    """
    Exhaustive allocator that finds the lowest-cost split across venues.

    Args:
        order_size (int): Total shares to execute
        venues (list): List of venue dicts with keys ask_px, ask_sz, fee, rebate
        lambda_over (float): Penalty for overfill
        lambda_under (float): Penalty for underfill
        theta_queue (float): Queue risk penalty
        step (int): Discrete step size for allocation (default 100 shares)

    Returns:
        (best_split, best_cost): Tuple of list[int] and float
    """
    from itertools import product

    num_venues = len(venues)
    bounds = [range(0, min(order_size, v["ask_sz"]) + 1, step) for v in venues]

    best_cost = float("inf")
    best_split = None

    for split in product(*bounds):
        if sum(split) != order_size:
            continue

        cost = compute_cost(
            split, venues, order_size, lambda_over, lambda_under, theta_queue
        )

        if cost < best_cost:
            best_cost = cost
            best_split = split

    if best_split is not None:
        return list(best_split), best_cost
    else:
        return None, float("inf")


# --- BASELINE STRATEGIES ---
def baseline_best_ask(snapshots, total_order_size):
    sorted_venues = sorted(snapshots, key=lambda v: v["ask_px"])
    remaining = total_order_size
    total_cash = 0
    for v in sorted_venues:
        fill = min(v["ask_sz"], remaining)
        total_cash += fill * (v["ask_px"] + 0.002)
        remaining -= fill
        if remaining <= 0:
            break
    return total_cash, total_order_size - remaining


def baseline_twap(snapshots_over_time, total_order_size, interval_count=5):
    shares_per_tick = total_order_size // interval_count
    total_cash = 0
    executed = 0
    selected_ticks = snapshots_over_time[
        :: max(1, len(snapshots_over_time) // interval_count)
    ]
    for snapshot in selected_ticks:
        sorted_venues = sorted(snapshot, key=lambda v: v["ask_px"])
        remaining = shares_per_tick
        for v in sorted_venues:
            fill = min(v["ask_sz"], remaining)
            total_cash += fill * (v["ask_px"] + 0.002)
            remaining -= fill
            executed += fill
            if remaining <= 0:
                break
    return total_cash, executed


def baseline_vwap(snapshots_over_time, total_order_size):
    all_venues = []
    for snap in snapshots_over_time:
        all_venues.extend(snap)
    sorted_venues = sorted(all_venues, key=lambda v: v["ask_px"])
    total_cash = 0
    executed = 0
    remaining = total_order_size
    for v in sorted_venues:
        fill = min(v["ask_sz"], remaining)
        total_cash += fill * (v["ask_px"] + 0.002)
        executed += fill
        remaining -= fill
        if remaining <= 0:
            break
    return total_cash, executed


def savings_bps(baseline_cash, optimized_cash):
    return ((baseline_cash - optimized_cash) / baseline_cash) * 10000


# --- LOAD SNAPSHOTS FROM KAFKA ---
consumer = KafkaConsumer(
    KAFKA_TOPIC,
    bootstrap_servers=BOOTSTRAP_SERVERS,
    auto_offset_reset="earliest",
    enable_auto_commit=False,
    group_id=None,
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
)

print("📡 Listening to Kafka topic...")
snapshots_over_time = []
for message in consumer:
    data = message.value
    snapshots_over_time.append(
        [
            {
                "ask_px": v["ask_px"],
                "ask_sz": v["ask_sz"],
                "fee": 0.002,
                "rebate": 0.001,
                "queue_pos": int(v["ask_sz"] * random.uniform(0.2, 1.2)),
            }
            for v in data["snapshots"]
        ]
    )

    # Artificially reduce total liquidity in ~20% of snapshots
    # Artificially reduce total liquidity in ~20% of snapshots
    if random.random() < 0.2:
        for venue in snapshots_over_time[-1]:
            venue["ask_sz"] = int(venue["ask_sz"] * 0.7)

    print(f"📊 Snapshot count loaded: {len(snapshots_over_time)}")
    print(
        f"Example liquidity: {[sum(v['ask_sz'] for v in snap) for snap in snapshots_over_time[:5]]}"
    )

    if len(snapshots_over_time) >= 200:  # Limit number of snapshots used
        break

# --- GRID SEARCH ---
# Expand grid with more price-sensitive options
lambda_over_range = [0.05, 0.1, 0.2, 0.4]
lambda_under_range = [0.1, 0.2, 0.4]
theta_queue_range = [0.01, 0.05, 0.1, 0.3]
param_grid = list(product(lambda_over_range, lambda_under_range, theta_queue_range))

results = []
best_result = {"optimized_total_cash": math.inf}

for lambda_over, lambda_under, theta_queue in param_grid:
    unfilled = ORDER_SIZE
    total_executed = 0
    total_cash = 0.0

    for snapshots in snapshots_over_time:
        if unfilled <= 0:
            break

        total_liquidity = sum(v["ask_sz"] for v in snapshots)
        if total_liquidity == 0:
            continue

        alloc_size = min(unfilled, ORDER_SIZE)
        split, _ = allocate(
            alloc_size, snapshots, lambda_over, lambda_under, theta_queue
        )
        if split is None:
            continue

        executed = 0
        cash = 0.0
        for i, shares in enumerate(split):
            fill = min(shares, snapshots[i]["ask_sz"])
            executed += fill
            cash += fill * (snapshots[i]["ask_px"] + snapshots[i]["fee"])
            rebate = max(shares - fill, 0) * snapshots[i]["rebate"]
            cash -= rebate

        total_executed += executed
        total_cash += cash
        unfilled = ORDER_SIZE - total_executed

    print(
        f"Params: λo={lambda_over}, λu={lambda_under}, θ={theta_queue} → executed={total_executed}"
    )

    if total_executed > 0:
        avg_price = total_cash / total_executed
    else:
        avg_price = float("inf")

    if total_executed == 0:
        continue

    if total_executed < ORDER_SIZE:
        print("⚠️ Skipping partial fill config")
        continue

    # ✅ Baseline Debugging
    ba_cash, ba_exec = baseline_best_ask(snapshots_over_time[-1], ORDER_SIZE)
    twap_cash, twap_exec = baseline_twap(snapshots_over_time, ORDER_SIZE)
    vwap_cash, vwap_exec = baseline_vwap(snapshots_over_time, ORDER_SIZE)

    print(f"  ⤷ Baseline best ask cost: {ba_cash:.2f}, exec: {ba_exec}")
    print(f"  ⤷ TWAP cost: {twap_cash:.2f}, exec: {twap_exec}")
    print(f"  ⤷ VWAP cost: {vwap_cash:.2f}, exec: {vwap_exec}")
    print(f"  ⤷ Optimized cash: {total_cash:.2f}, exec: {total_executed}")

    avg_price = total_cash / total_executed

    result = {
        "lambda_over": lambda_over,
        "lambda_under": lambda_under,
        "theta_queue": theta_queue,
        "optimized_total_cash": round(total_cash, 2),
        "avg_fill_px": round(avg_price, 4),
        "savings_vs_best_ask_bps": round(savings_bps(ba_cash, total_cash), 2),
        "savings_vs_twap_bps": round(savings_bps(twap_cash, total_cash), 2),
        "savings_vs_vwap_bps": round(savings_bps(vwap_cash, total_cash), 2),
    }

    results.append(result)

    current_savings = savings_bps(vwap_cash, total_cash)
    best_savings = savings_bps(vwap_cash, best_result["optimized_total_cash"])
    if current_savings > best_savings:
        best_result = result

# --- FINAL OUTPUT ---
print("\n🏁 Best Result Found:")
print(json.dumps(best_result, indent=2))

with open("grid_results.json", "w") as f:
    json.dump(results, f, indent=2)

# --- PLOT SAVINGS ---
df = pd.DataFrame(results)
plt.figure(figsize=(10, 6))
plt.scatter(df.index, df["savings_vs_best_ask_bps"], label="Best Ask", marker="o")
plt.scatter(df.index, df["savings_vs_twap_bps"], label="TWAP", marker="s")
plt.scatter(df.index, df["savings_vs_vwap_bps"], label="VWAP", marker="^")
plt.axhline(0, color="gray", linestyle="--", linewidth=1)
plt.title("Savings vs Baselines (bps)")
plt.xlabel("Parameter Grid Index")
plt.ylabel("Savings (bps)")
plt.legend()
plt.tight_layout()
plt.savefig("savings_plot.png")
print("📈 Saved savings plot as savings_plot.png")

top_results = sorted(results, key=lambda x: -x["savings_vs_vwap_bps"])[:5]
print("\n🏆 Top 5 Performers vs VWAP:")
for res in top_results:
    print(json.dumps(res, indent=2))
