"""
Quick manual test: run ONE payment through the full graph and print the trail.
"""

import json

from more_itertools import sample

from app.agent.graph import app_graph
from app.decline_codes import MAX_RETRIES

with open("payments.json") as f:
    payments = json.load(f)

# pick a soft-decline record and a hard-decline record to test both paths
# non-recurring soft decline test
sample1 = next(p for p in payments if p["opted_out"])
# sample1 = next(p for p in payments if p["is_recurring"] and p["decline_code"] in
    # ("CARD_EXPIRED", "INVALID_VPA", "RISK_FRAUD_BLOCK"))
 # change index to test different records
# sample1 = next(p for p in payments if p["is_recurring"] and p["decline_code"] == "INSUFFICIENT_FUNDS")

initial_state = {
    "payment_id": sample1["payment_id"],
    "customer_id": sample1["customer_id"],
    "amount": sample1["amount"],
    "channel": sample1["channel"],
    "decline_code": sample1["decline_code"],
    "decline_type": None,
    "is_recurring": sample1["is_recurring"],      # NEW
    "opted_out": sample1["opted_out"],             # NEW
    "retry_count": 0,
    "max_retries": MAX_RETRIES,
    "status": "pending",
    "next_action": None,
    "action_allowed": None,
    "audit_log": [],
}

final_state = app_graph.invoke(initial_state)

print(f"\nPayment: {final_state['payment_id']}")
print(f"Final status: {final_state['status']}")
print(f"Retries used: {final_state['retry_count']}\n")
print("--- Audit trail ---")
for line in final_state["audit_log"]:
    print(line)