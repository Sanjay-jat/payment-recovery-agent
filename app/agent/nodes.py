"""
LangGraph nodes for the payment recovery agent.
"""

from datetime import datetime, timezone, timedelta

from app.decline_codes import DECLINE_CODES, is_hard_decline, get_retry_plan, MAX_RETRIES
from app.agent.state import RecoveryState


def detect_decline(state: RecoveryState) -> dict:
    """Classify the decline code as soft (recoverable) or hard (never retry)."""
    code = state["decline_code"]
    decline_type = DECLINE_CODES[code]["type"]
    description = DECLINE_CODES[code]["description"]

    log_line = f"[detect_decline] {code} -> {decline_type} ({description})"

    return {
        "decline_type": decline_type,
        "audit_log": state["audit_log"] + [log_line],
    }


def decide_action(state: RecoveryState) -> dict:
    """Pick the next action based on decline type and retries remaining."""

    # Hard decline -> never retry, always route to a message instead.
    if state["decline_type"] == "hard":
        log_line = f"[decide_action] Hard decline ({state['decline_code']}) -> will not retry, sending message"
        return {
            "next_action": "send_message",
            "audit_log": state["audit_log"] + [log_line],
        }

    # Soft decline but retries exhausted -> also route to a message, mark exhausted after.
    if state["retry_count"] >= state["max_retries"]:
        log_line = f"[decide_action] Retry limit reached ({state['retry_count']}/{state['max_retries']}) -> sending final message"
        return {
            "next_action": "send_message",
            "audit_log": state["audit_log"] + [log_line],
        }

    # Soft decline, retries left -> retry charge.
    delay_hours, channel = get_retry_plan(state["decline_code"])
    log_line = (f"[decide_action] Soft decline, attempt {state['retry_count'] + 1}/{state['max_retries']} "
                f"-> retry via {channel} channel (playbook delay: {delay_hours}h)")
    return {
        "next_action": "retry_charge",
        "audit_log": state["audit_log"] + [log_line],
    }