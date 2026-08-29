"""
SQLAlchemy ORM models mapping to schema.sql tables.
"""

from sqlalchemy import Column, String, Numeric, Boolean, Integer, TIMESTAMP, ForeignKey, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Payment(Base):
    __tablename__ = "payments"

    payment_id = Column(String, primary_key=True)
    customer_id = Column(String, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    channel = Column(String, nullable=False)
    decline_code = Column(String, nullable=False)
    decline_type = Column(String)
    is_recurring = Column(Boolean, nullable=False, default=False)
    opted_out = Column(Boolean, nullable=False, default=False)
    failed_at = Column(TIMESTAMP(timezone=True), nullable=False)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=4)
    status = Column(String, nullable=False, default="pending")
    recovered_amount = Column(Numeric(10, 2))
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class RetryAttempt(Base):
    __tablename__ = "retry_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    payment_id = Column(String, ForeignKey("payments.payment_id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    action_type = Column(String, nullable=False)
    idempotency_key = Column(String)
    outcome = Column(String)
    attempted_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    payment_id = Column(String, ForeignKey("payments.payment_id"), nullable=False)
    node_name = Column(String, nullable=False)
    message = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())