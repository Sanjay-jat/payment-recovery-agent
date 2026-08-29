"""
Decline code reference + retry playbook.
"""

from typing import TypedDict, Literal

DeclineType = Literal["soft", "hard"]


class DeclineRule(TypedDict):
    type: DeclineType
    description: str
    retry_delay_hours: int
    retry_channel: str
    weight: float


DECLINE_CODES: dict[str, DeclineRule] = {
    "INSUFFICIENT_FUNDS": {
        "type": "soft", "description": "Insufficient balance in account",
        "retry_delay_hours": 72, "retry_channel": "same", "weight": 0.28,
    },
    "BANK_SERVER_TIMEOUT": {
        "type": "soft", "description": "Issuer bank server did not respond in time",
        "retry_delay_hours": 1, "retry_channel": "alt", "weight": 0.18,
    },
    "NETWORK_ERROR": {
        "type": "soft", "description": "Network/processor-side connection error",
        "retry_delay_hours": 0, "retry_channel": "alt", "weight": 0.12,
    },
    "VELOCITY_LIMIT_EXCEEDED": {
        "type": "soft", "description": "Too many attempts in a short window (bank-side throttle)",
        "retry_delay_hours": 6, "retry_channel": "same", "weight": 0.08,
    },
    "ISSUER_TEMPORARY_DECLINE": {
        "type": "soft", "description": "Issuer flagged transaction for temporary manual review",
        "retry_delay_hours": 24, "retry_channel": "same", "weight": 0.07,
    },
    "UPI_PIN_RETRY_LIMIT": {
        "type": "soft", "description": "Too many wrong UPI PIN attempts, temporary UPI-side lock",
        "retry_delay_hours": 24, "retry_channel": "same", "weight": 0.05,
    },
    "CARD_EXPIRED": {
        "type": "hard", "description": "Card has expired",
        "retry_delay_hours": 0, "retry_channel": "same", "weight": 0.08,
    },
    "CARD_REPORTED_LOST_STOLEN": {
        "type": "hard", "description": "Card reported lost or stolen",
        "retry_delay_hours": 0, "retry_channel": "same", "weight": 0.03,
    },
    "INVALID_VPA": {
        "type": "hard", "description": "UPI VPA does not exist / mistyped",
        "retry_delay_hours": 0, "retry_channel": "same", "weight": 0.05,
    },
    "RISK_FRAUD_BLOCK": {
        "type": "hard", "description": "Transaction blocked by issuer/network risk engine",
        "retry_delay_hours": 0, "retry_channel": "same", "weight": 0.04,
    },
    "MANDATE_NOT_REGISTERED": {
        "type": "hard", "description": "Autopay/e-mandate not set up or was revoked",
        "retry_delay_hours": 0, "retry_channel": "same", "weight": 0.02,
    },
}

MAX_RETRIES = 4
ALLOWED_CONTACT_START_HOUR = 8
ALLOWED_CONTACT_END_HOUR = 19


def is_hard_decline(code: str) -> bool:
    return DECLINE_CODES[code]["type"] == "hard"


def get_retry_plan(code: str) -> tuple[int, str]:
    rule = DECLINE_CODES[code]
    return rule["retry_delay_hours"], rule["retry_channel"]