"""
FastAPI app exposing the recovery agent's batch runner and dashboard data.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func

from app.db import SessionLocal
from app.models import Payment, AuditLog

app = FastAPI(title="Payment Recovery Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/dashboard")
def get_dashboard():
    db = SessionLocal()
    try:
        total = db.query(Payment).count()
        total_amount = db.query(func.sum(Payment.amount)).scalar() or 0
        recovered_amount = db.query(func.sum(Payment.recovered_amount)).scalar() or 0
        recovered_count = db.query(Payment).filter_by(status="recovered").count()

        status_breakdown = (
            db.query(Payment.status, func.count(Payment.payment_id))
            .group_by(Payment.status)
            .all()
        )

        retry_funnel = (
            db.query(Payment.retry_count, func.count(Payment.payment_id))
            .filter(Payment.status == "recovered")
            .group_by(Payment.retry_count)
            .all()
        )

        return {
            "total_payments": total,
            "total_amount": float(total_amount),
            "recovered_amount": float(recovered_amount),
            "recovered_count": recovered_count,
            "recovery_rate_pct": round(recovered_count / total * 100, 1) if total else 0,
            "status_breakdown": {status: count for status, count in status_breakdown},
            "retry_funnel": {f"attempt_{n}": count for n, count in retry_funnel},
        }
    finally:
        db.close()


@app.get("/payments")
def list_payments(limit: int = 50):
    db = SessionLocal()
    try:
        payments = db.query(Payment).limit(limit).all()
        return [
            {
                "payment_id": p.payment_id,
                "amount": float(p.amount),
                "decline_code": p.decline_code,
                "decline_type": p.decline_type,
                "status": p.status,
                "retry_count": p.retry_count,
                "is_recurring": p.is_recurring,
            }
            for p in payments
        ]
    finally:
        db.close()


def generate_summary(logs: list[dict]) -> str:
    """Turn the raw audit trail into one plain-English sentence."""
    text = " ".join(l["message"] for l in logs)

    if "hard" in text.lower() and "will not retry" in text.lower():
        reason = "the payment method itself is invalid or expired"
    elif "one-time payment" in text.lower():
        reason = "it was a one-time payment with no saved method to retry"
    elif "opted out" in text.lower():
        reason = "the customer had opted out of being contacted"
    elif "recovered" in text.lower():
        reason = "a retry succeeded"
    elif "retry limit reached" in text.lower():
        reason = "all retry attempts were used up"
    else:
        reason = "of the rules below"

    final_status = logs[-1]["message"] if logs else ""
    return f"This payment ended up '{final_status.split(':')[-1].strip()}' because {reason}."


@app.get("/payments/{payment_id}/audit")
def get_audit_trail(payment_id: str):
    db = SessionLocal()
    try:
        logs = (
            db.query(AuditLog)
            .filter_by(payment_id=payment_id)
            .order_by(AuditLog.created_at)
            .all()
        )
        steps = [
            {"node": log.node_name, "message": log.message, "at": log.created_at.isoformat()}
            for log in logs
        ]
        return {
            "summary": generate_summary(steps),
            "steps": steps,
        }
    finally:
        db.close()

from pydantic import BaseModel
from app.agent.graph import app_graph
from app.decline_codes import MAX_RETRIES, DECLINE_CODES


class SimulateRequest(BaseModel):
    amount: float
    decline_code: str
    is_recurring: bool
    opted_out: bool = False


@app.post("/simulate")
def simulate_payment(req: SimulateRequest):
    initial_state = {
        "payment_id": "sim_preview",
        "customer_id": "sim_customer",
        "amount": req.amount,
        "channel": "upi",
        "decline_code": req.decline_code,
        "decline_type": None,
        "is_recurring": req.is_recurring,
        "opted_out": req.opted_out,
        "retry_count": 0,
        "max_retries": MAX_RETRIES,
        "status": "pending",
        "next_action": None,
        "action_allowed": None,
        "audit_log": [],
    }
    final_state = app_graph.invoke(initial_state)
    steps = [{"message": line} for line in final_state["audit_log"]]
    return {
        "final_status": final_state["status"],
        "retry_count": final_state["retry_count"],
        "summary": generate_summary(steps),
        "steps": final_state["audit_log"],
    }


@app.get("/decline-codes")
def list_decline_codes():
    return list(DECLINE_CODES.keys())