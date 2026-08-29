"""
Runs the full payment batch through the agent and persists results to Postgres.
"""

import json
from datetime import datetime, timezone

from app.db import SessionLocal
from app.models import Payment, RetryAttempt, AuditLog
from app.agent.graph import app_graph
from app.decline_codes import MAX_RETRIES

with open("payments.json") as f:
    payments = json.load(f)

db = SessionLocal()

for record in payments:
    # 1. Insert the payment as "pending" first (if not already there)
    existing = db.query(Payment).filter_by(payment_id=record["payment_id"]).first()
    if not existing:
        db.add(Payment(
            payment_id=record["payment_id"],
            customer_id=record["customer_id"],
            amount=record["amount"],
            channel=record["channel"],
            decline_code=record["decline_code"],
            is_recurring=record["is_recurring"],
            opted_out=record["opted_out"],
            failed_at=record["failed_at"],
            max_retries=MAX_RETRIES,
            status="pending",
        ))
        db.commit()

    # 2. Run it through the agent
    initial_state = {
        "payment_id": record["payment_id"],
        "customer_id": record["customer_id"],
        "amount": record["amount"],
        "channel": record["channel"],
        "decline_code": record["decline_code"],
        "decline_type": None,
        "is_recurring": record["is_recurring"],
        "opted_out": record["opted_out"],
        "retry_count": 0,
        "max_retries": MAX_RETRIES,
        "status": "pending",
        "next_action": None,
        "action_allowed": None,
        "audit_log": [],
    }
    final_state = app_graph.invoke(initial_state)

    # 3. Update the payment row with the final outcome
    payment_row = db.query(Payment).filter_by(payment_id=record["payment_id"]).first()
    payment_row.decline_type = final_state["decline_type"]
    payment_row.retry_count = final_state["retry_count"]
    payment_row.status = final_state["status"]
    if final_state["status"] == "recovered":
        payment_row.recovered_amount = record["amount"]

    # 4. Save the audit trail (one row per log line, node name parsed from "[node] message")
    for line in final_state["audit_log"]:
        node_name = line.split("]")[0].strip("[") if line.startswith("[") else "unknown"
        message = line.split("]", 1)[1].strip() if "]" in line else line
        db.add(AuditLog(payment_id=record["payment_id"], node_name=node_name, message=message))

    db.commit()

print(f"Processed {len(payments)} payments.")

recovered = db.query(Payment).filter_by(status="recovered").count()
total = db.query(Payment).count()
print(f"Recovered: {recovered}/{total}")

db.close()