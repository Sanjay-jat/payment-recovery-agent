"""
Generates a synthetic batch of failed-payment records.
Run: python generate_dataset.py --n 200 --seed 42 --out payments.json
"""

import argparse
import json
import random
import uuid
from datetime import datetime, timedelta, timezone

from app.decline_codes import DECLINE_CODES

CHANNELS = ["upi", "card", "netbanking"]


def generate(n: int, seed: int) -> list[dict]:
    random.seed(seed)
    codes = list(DECLINE_CODES.keys())
    weights = [DECLINE_CODES[c]["weight"] for c in codes]

    records = []
    now = datetime.now(timezone.utc)
    for _ in range(n):
        code = random.choices(codes, weights=weights, k=1)[0]
        failed_at = now - timedelta(hours=random.randint(1, 240))
        records.append({
            "payment_id": f"pay_{uuid.uuid4().hex[:12]}",
            "customer_id": f"cust_{uuid.uuid4().hex[:8]}",
            "amount": round(random.uniform(199, 15000), 2),
            "channel": random.choice(CHANNELS),
            "decline_code": code,
            "failed_at": failed_at.isoformat(),
            "retry_count": 0,
            "status": "pending",
            "is_recurring": random.random() < 0.5,      # NEW: subscription/mandate vs one-time
            "opted_out": random.random() < 0.05,         # NEW: 5% customers opted out of contact
        })
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default="payments.json")
    args = parser.parse_args()

    data = generate(args.n, args.seed)
    with open(args.out, "w") as f:
        json.dump(data, f, indent=2)

    soft = sum(1 for r in data if DECLINE_CODES[r["decline_code"]]["type"] == "soft")
    print(f"Generated {len(data)} records -> {args.out}")
    print(f"Soft declines: {soft} ({soft/len(data)*100:.1f}%) | "
          f"Hard declines: {len(data)-soft} ({(len(data)-soft)/len(data)*100:.1f}%)")