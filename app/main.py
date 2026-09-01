"""
FastAPI app exposing the recovery agent's batch runner and dashboard data.
"""

import os
from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func

from app.db import SessionLocal
from app.models import Payment, AuditLog
import random
from datetime import datetime, timezone
from fastapi import HTTPException
from app.agent.nodes import MESSAGE_PROMPT
from app.decline_codes import DECLINE_CODES
from app.llm import get_llm

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")

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
        pending_approval_amount = db.query(func.sum(Payment.amount)).filter_by(status="pending_approval").scalar() or 0
        pending_approval_count = db.query(Payment).filter_by(status="pending_approval").count()

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
            "pending_approval_amount": float(pending_approval_amount),
            "pending_approval_count": pending_approval_count,
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
    status_text = final_status.split(':')[-1].strip() if ':' in final_status else final_status
    return f"This payment ended up '{status_text}' because {reason}."


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


class SimApproveRequest(BaseModel):
    amount: float
    decline_code: str
    next_action: str
    retry_count: int = 0


@app.post("/simulate")
def simulate_payment(req: SimulateRequest, x_gemini_key: str | None = Header(default=None)):
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
    final_state = app_graph.invoke(
        initial_state,
        config={"configurable": {"llm_provider": LLM_PROVIDER, "gemini_key": x_gemini_key}},
    )
    steps = []
    for line in final_state["audit_log"]:
        node = line.split("]")[0].strip("[") if line.startswith("[") else "unknown"
        msg = line.split("]", 1)[1].strip() if "]" in line else line
        steps.append({"node": node, "message": msg})

    return {
        "final_status": final_state["status"],
        "retry_count": final_state["retry_count"],
        "pending_action": final_state.get("next_action"),
        "summary": generate_summary(steps),
        "steps": final_state["audit_log"],
    }


@app.post("/simulate/approve")
def simulate_approve(req: SimApproveRequest, x_gemini_key: str | None = Header(default=None)):
    if req.next_action == "retry_charge":
        success = random.random() < 0.65
        line = f"[execute] Approved retry (idempotency_key=sim_preview_attempt_{req.retry_count + 1}) -> {'success' if success else 'failed'}"
        status = "recovered" if success else "pending"
    else:
        try:
            llm = get_llm(provider=LLM_PROVIDER, api_key=x_gemini_key)
            prompt = MESSAGE_PROMPT.format(
                payment_id="sim_preview", amount=req.amount,
                reason=DECLINE_CODES[req.decline_code]["description"],
            )
            response = llm.invoke(prompt)
            message = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            message = f"[LLM unavailable: {e}]"
        line = f"[execute] Approved message sent: {message[:80]}..."
        status = "escalated" if DECLINE_CODES[req.decline_code]["type"] == "hard" else "exhausted"
    return {"final_status": status, "line": line}


@app.get("/decline-codes")
def list_decline_codes():
    return list(DECLINE_CODES.keys())

def compute_recovery_probability(db, decline_code: str):
    total = db.query(Payment).filter_by(decline_code=decline_code).count()
    recovered = db.query(Payment).filter_by(decline_code=decline_code, status="recovered").count()
    if total == 0:
        return None
    return round(recovered / total * 100, 1)


@app.get("/approval-queue")
def get_approval_queue():
    db = SessionLocal()
    try:
        rows = db.query(Payment).filter_by(status="pending_approval").all()
        return [
            {
                "payment_id": r.payment_id,
                "amount": float(r.amount),
                "decline_code": r.decline_code,
                "pending_action": r.pending_action,
                "recovery_probability": compute_recovery_probability(db, r.decline_code),
            }
            for r in rows
        ]
    finally:
        db.close()


@app.get("/approval-stats")
def approval_stats():
    db = SessionLocal()
    try:
        pending = db.query(Payment).filter_by(status="pending_approval").count()
        today = datetime.now(timezone.utc).date()
        approved_today = db.query(AuditLog).filter(
            AuditLog.node_name == "approval",
            AuditLog.message.like("[approval] Approved%"),
            func.date(AuditLog.created_at) == today,
        ).count()
        rejected_today = db.query(AuditLog).filter(
            AuditLog.node_name == "approval",
            AuditLog.message.like("[approval] Rejected%"),
            func.date(AuditLog.created_at) == today,
        ).count()
        auto_resolved = db.query(Payment).filter(
            Payment.status.in_(["recovered", "exhausted", "escalated", "blocked"])
        ).count()
        return {
            "pending": pending,
            "approved_today": approved_today,
            "rejected_today": rejected_today,
            "auto_resolved": auto_resolved,
        }
    finally:
        db.close()


@app.post("/payments/{payment_id}/approve")
def approve_payment(payment_id: str, x_gemini_key: str | None = Header(default=None)):
    db = SessionLocal()
    try:
        row = db.query(Payment).filter_by(payment_id=payment_id).first()
        if not row or row.status != "pending_approval":
            raise HTTPException(404, "No pending approval found")

        lines = []
        if row.pending_action == "retry_charge":
            success = random.random() < 0.65
            key = f"{payment_id}_attempt_{row.retry_count + 1}_approved"
            lines.append(f"[execute] Approved retry (idempotency_key={key}) -> {'success' if success else 'failed'}")
            row.retry_count += 1
            row.status = "recovered" if success else "pending"
            if success:
                row.recovered_amount = row.amount

        elif row.pending_action == "send_message":
            try:
                llm = get_llm(provider=LLM_PROVIDER, api_key=x_gemini_key)
                prompt = MESSAGE_PROMPT.format(
                    payment_id=payment_id, amount=row.amount,
                    reason=DECLINE_CODES[row.decline_code]["description"],
                )
                response = llm.invoke(prompt)
                message = response.content if hasattr(response, "content") else str(response)
            except Exception as e:
                message = f"[LLM unavailable: {e}]"
            lines.append(f"[execute] Approved message sent: {message[:80]}...")
            row.status = "escalated" if row.decline_type == "hard" else "exhausted"

        lines.append("[approval] Approved by operator")
        for line in lines:
            db.add(AuditLog(payment_id=payment_id, node_name="approval", message=line))
        db.commit()
        return {"payment_id": payment_id, "new_status": row.status}
    finally:
        db.close()


@app.post("/payments/{payment_id}/reject")
def reject_payment(payment_id: str):
    db = SessionLocal()
    try:
        row = db.query(Payment).filter_by(payment_id=payment_id).first()
        if not row or row.status != "pending_approval":
            raise HTTPException(404, "No pending approval found")
        row.status = "blocked"
        db.add(AuditLog(payment_id=payment_id, node_name="approval", message="[approval] Rejected by operator — no action taken"))
        db.commit()
        return {"payment_id": payment_id, "new_status": "blocked"}
    finally:
        db.close()