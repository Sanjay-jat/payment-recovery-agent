"""
Quick manual test: run ONE payment through the full graph and print the trail.
"""

import json

from app.agent.graph import app_graph
from app.decline_codes import MAX_RETRIES

with open("payments.json") as f:
    payments = json.load(f)

# pick a soft-decline record and a hard-decline record to test both paths
sample = payments[0]  # change index to test different records

initial_state = {
    "payment_id": sample["payment_id"],
    "customer_id": sample["customer_id"],
    "amount": sample["amount"],
    "channel": sample["channel"],
    "decline_code": sample["decline_code"],
    "decline_type": None,
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