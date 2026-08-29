"""
Shared state that flows through every LangGraph node.
"""

from typing import TypedDict, Literal, Optional


class RecoveryState(TypedDict):
    payment_id: str
    customer_id: str
    amount: float
    channel: str
    decline_code: str
    decline_type: Optional[Literal["soft", "hard"]]

    is_recurring: bool          # NEW
    opted_out: bool             # NEW

    retry_count: int
    max_retries: int

    status: Literal["pending", "recovered", "exhausted", "blocked", "escalated", "skipped_too_early"]  # added one
    next_action: Optional[Literal["retry_charge", "send_message", "none"]]
    action_allowed: Optional[bool]

    audit_log: list[str]                    # human-readable trail, one line per node