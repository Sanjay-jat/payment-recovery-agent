"""
Shared state that flows through every LangGraph node.
"""

from typing import TypedDict, Literal, Optional


class RecoveryState(TypedDict):
    payment_id: str
    customer_id: str
    amount: float
    channel: str                              # upi / card / netbanking
    decline_code: str
    decline_type: Optional[Literal["soft", "hard"]]

    retry_count: int
    max_retries: int

    status: Literal["pending", "recovered", "exhausted", "blocked", "escalated"]
    next_action: Optional[Literal["retry_charge", "send_message", "none"]]
    action_allowed: Optional[bool]            # set by compliance_gate

    audit_log: list[str]                      # human-readable trail, one line per node