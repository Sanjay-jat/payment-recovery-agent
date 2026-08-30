"""
LangGraph nodes for the payment recovery agent.
"""

from datetime import datetime, timezone, timedelta

from app.decline_codes import DECLINE_CODES, is_hard_decline, get_retry_plan, MAX_RETRIES
from app.decline_codes import ALLOWED_CONTACT_START_HOUR, ALLOWED_CONTACT_END_HOUR
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
    # Rule: a non-recurring payment has no stored authorization — can never be silently retried
    if state["decline_type"] == "soft" and not state["is_recurring"]:
        log_line = "[decide_action] Soft decline but one-time payment (no saved instrument) -> cannot silently retry, sending message instead"
        return {
            "next_action": "send_message",
            "audit_log": state["audit_log"] + [log_line],
        }

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
from datetime import timedelta

IST = timezone(timedelta(hours=5, minutes=30))
def compliance_gate(state: RecoveryState) -> dict:
    """Check whether the decided action is actually allowed to happen right now."""
    if state["opted_out"] and state["next_action"] == "send_message":
        log_line = "[compliance_gate] BLOCKED: customer has opted out of contact"
        return {
            "action_allowed": False,
            "status": "blocked",
            "audit_log": state["audit_log"] + [log_line],
        }

    # Rule: double safety - never retry a non-recurring payment even if decide_action somehow allowed it
    if state["next_action"] == "retry_charge" and not state["is_recurring"]:
        log_line = "[compliance_gate] BLOCKED: cannot retry a non-recurring payment (no stored authorization)"
        return {
            "action_allowed": False,
            "status": "blocked",
            "audit_log": state["audit_log"] + [log_line],
        }
    now_hour = datetime.now(IST).hour

    # Rule 1: contact window (RBI Fair Practices Code style — no contact outside 8AM-7PM)
    if state["next_action"] == "send_message":
        if not (ALLOWED_CONTACT_START_HOUR <= now_hour < ALLOWED_CONTACT_END_HOUR):
            log_line = f"[compliance_gate] BLOCKED: message attempted at hour {now_hour}, outside allowed window ({ALLOWED_CONTACT_START_HOUR}-{ALLOWED_CONTACT_END_HOUR})"
            return {
                "action_allowed": False,
                "status": "blocked",
                "audit_log": state["audit_log"] + [log_line],
            }

    # Rule 2: never retry a hard decline, no matter what decide_action said
    if state["next_action"] == "retry_charge" and state["decline_type"] == "hard":
        log_line = "[compliance_gate] BLOCKED: attempted to retry a hard decline — not allowed"
        return {
            "action_allowed": False,
            "status": "blocked",
            "audit_log": state["audit_log"] + [log_line],
        }

    # Rule 3: retry cap already enforced in decide_action, but double-check here too
    if state["next_action"] == "retry_charge" and state["retry_count"] >= state["max_retries"]:
        log_line = f"[compliance_gate] BLOCKED: retry cap reached ({state['retry_count']}/{state['max_retries']})"
        return {
            "action_allowed": False,
            "status": "blocked",
            "audit_log": state["audit_log"] + [log_line],
        }

    log_line = f"[compliance_gate] ALLOWED: {state['next_action']} can proceed"
    return {
        "action_allowed": True,
        "audit_log": state["audit_log"] + [log_line],
    }

import random
from app.llm import get_llm

MESSAGE_PROMPT = """You are a polite payment reminder assistant for an Indian fintech.
Write a short, respectful message (2-3 sentences) in natural Hinglish reminding the
customer about payment_id {payment_id} of amount Rs.{amount} that failed due to: {reason}.
Do not use pressure or threatening language. Keep it warm and helpful."""


def execute(state: RecoveryState, llm_provider: str = "ollama") -> dict:
    """Perform the allowed action: simulate a retry, or generate a reminder message."""
    if state["next_action"] == "retry_charge":
        idempotency_key = f"{state['payment_id']}_attempt_{state['retry_count'] + 1}"
        success = random.random() < 0.65
        outcome = "success" if success else "failed"
        log_line = f"[execute] Retry attempt {state['retry_count'] + 1} (idempotency_key={idempotency_key}) -> {outcome}"
        return {
            "retry_count": state["retry_count"] + 1,
            "status": "recovered" if success else "pending",
            "audit_log": state["audit_log"] + [log_line],
        }

    if not state["action_allowed"]:
        # Nothing to execute, compliance_gate already blocked it.
        return {"audit_log": state["audit_log"] + ["[execute] Skipped — action was blocked"]}

    if state["next_action"] == "retry_charge":
        # Simulate outcome: soft declines succeed more often than not, but not always.
        success = random.random() < 0.65
        outcome = "success" if success else "failed"
        log_line = f"[execute] Retry attempt {state['retry_count'] + 1} -> {outcome}"
        return {
            "retry_count": state["retry_count"] + 1,
            "status": "recovered" if success else "pending",
            "audit_log": state["audit_log"] + [log_line],
        }

    elif state["next_action"] == "send_message":
        try:
            llm = get_llm(provider=llm_provider)
            prompt = MESSAGE_PROMPT.format(
                payment_id=state["payment_id"],
                amount=state["amount"],
                reason=DECLINE_CODES[state["decline_code"]]["description"],
            )
            response = llm.invoke(prompt)
            message = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            message = f"[LLM unavailable: {e}]"

        log_line = f"[execute] Message generated: {message[:80]}..."
        new_status = "escalated" if state["decline_type"] == "hard" else "exhausted"
        return {
            "status": new_status,
            "audit_log": state["audit_log"] + [log_line],
        }

    return {"audit_log": state["audit_log"] + ["[execute] No action taken"]}

def track_outcome(state: RecoveryState) -> dict:
    """Decide whether to loop back for another retry, or the payment is done."""

    if state["status"] == "recovered":
        log_line = f"[track_outcome] Payment recovered after {state['retry_count']} attempt(s)"
        return {"audit_log": state["audit_log"] + [log_line]}

    if state["status"] in ("exhausted", "escalated", "blocked"):
        log_line = f"[track_outcome] Terminal status reached: {state['status']}"
        return {"audit_log": state["audit_log"] + [log_line]}

    # status is still "pending" -> retry failed, will loop back if attempts remain
    log_line = f"[track_outcome] Still pending after attempt {state['retry_count']}, looping if retries remain"
    return {"audit_log": state["audit_log"] + [log_line]}

