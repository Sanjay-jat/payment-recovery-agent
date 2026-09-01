"""
LangGraph nodes for the payment recovery agent.
"""

from datetime import datetime, timezone, timedelta

from app.decline_codes import DECLINE_CODES, is_hard_decline, get_retry_plan, MAX_RETRIES
from app.decline_codes import ALLOWED_CONTACT_START_HOUR, ALLOWED_CONTACT_END_HOUR
from app.agent.state import RecoveryState
from app.decline_codes import HIGH_VALUE_THRESHOLD
from langgraph.config import get_config


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
IST = timezone(timedelta(hours=5, minutes=30))

def compliance_gate(state: RecoveryState) -> dict:
    if state["next_action"] == "retry_charge" and state["amount"] >= HIGH_VALUE_THRESHOLD:
        log_line = f"[compliance_gate] High-value retry (₹{state['amount']}) -> requires human approval before retry_charge"
        return {
            "status": "pending_approval",
            "action_allowed": False,
            "audit_log": state["audit_log"] + [log_line],
        }

    now_hour = datetime.now(IST).hour

    if state["next_action"] == "send_message":
        if not (ALLOWED_CONTACT_START_HOUR <= now_hour < ALLOWED_CONTACT_END_HOUR):
            log_line = f"[compliance_gate] BLOCKED: message attempted at hour {now_hour}, outside allowed window ({ALLOWED_CONTACT_START_HOUR}-{ALLOWED_CONTACT_END_HOUR})"
            return {"action_allowed": False, "status": "blocked", "audit_log": state["audit_log"] + [log_line]}
        if state["opted_out"]:
            log_line = "[compliance_gate] BLOCKED: customer has opted out of contact"
            return {"action_allowed": False, "status": "blocked", "audit_log": state["audit_log"] + [log_line]}

    if state["next_action"] == "retry_charge":
        if not state["is_recurring"]:
            log_line = "[compliance_gate] BLOCKED: cannot retry a non-recurring payment (no stored authorization)"
            return {"action_allowed": False, "status": "blocked", "audit_log": state["audit_log"] + [log_line]}
        if state["decline_type"] == "hard":
            log_line = "[compliance_gate] BLOCKED: cannot retry a hard decline"
            return {"action_allowed": False, "status": "blocked", "audit_log": state["audit_log"] + [log_line]}
        if state["retry_count"] >= state["max_retries"]:
            log_line = f"[compliance_gate] BLOCKED: retry cap reached ({state['retry_count']}/{state['max_retries']})"
            return {"action_allowed": False, "status": "blocked", "audit_log": state["audit_log"] + [log_line]}

    log_line = f"[compliance_gate] ALLOWED: {state['next_action']} can proceed"
    return {"action_allowed": True, "audit_log": state["audit_log"] + [log_line]}

import random
from app.llm import get_llm

MESSAGE_PROMPT = """You are a polite payment reminder assistant for an Indian fintech.
Write a short, respectful message (2-3 sentences) in natural Hinglish reminding the
customer about payment_id {payment_id} of amount Rs.{amount} that failed due to: {reason}.
Do not use pressure or threatening language. Keep it warm and helpful."""


def execute(state: RecoveryState) -> dict:
    if not state["action_allowed"]:
        return {"audit_log": state["audit_log"] + ["[execute] Skipped — action was blocked"]}

    config = get_config()
    llm_provider = config.get("configurable", {}).get("llm_provider", "ollama")
    gemini_key = config.get("configurable", {}).get("gemini_key")

    if state["next_action"] == "retry_charge":
        success = random.random() < 0.65
        outcome = "success" if success else "failed"
        idempotency_key = f"{state['payment_id']}_attempt_{state['retry_count'] + 1}"
        log_line = f"[execute] Retry attempt {state['retry_count'] + 1} (idempotency_key={idempotency_key}) -> {outcome}"
        return {
            "retry_count": state["retry_count"] + 1,
            "status": "recovered" if success else "pending",
            "audit_log": state["audit_log"] + [log_line],
        }

    elif state["next_action"] == "send_message":
        try:
            llm = get_llm(provider=llm_provider, api_key=gemini_key)
            prompt = MESSAGE_PROMPT.format(
                payment_id=state["payment_id"], amount=state["amount"],
                reason=DECLINE_CODES[state["decline_code"]]["description"],
            )
            response = llm.invoke(prompt)
            message = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            message = f"[LLM unavailable: {e}]"
        log_line = f"[execute] Message generated: {message[:80]}..."
        new_status = "escalated" if state["decline_type"] == "hard" else "exhausted"
        return {"status": new_status, "audit_log": state["audit_log"] + [log_line]}

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

