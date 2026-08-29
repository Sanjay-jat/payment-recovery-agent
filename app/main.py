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
    allow_origins=["*"],       # fine for a hackathon demo; tighten for real prod
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
        return [
            {"node": log.node_name, "message": log.message, "at": log.created_at.isoformat()}
            for log in logs
        ]
    finally:
        db.close()