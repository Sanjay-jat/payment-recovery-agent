Bug: When retries were exhausted, the graph ended immediately without sending a
final message to the customer — should_continue was checking retry_count < max_retries,
which cut the loop before decide_action could route to send_message.
Fix: should_continue now only checks status == "pending"; decide_action already
handles routing to send_message once retries are exhausted, so the loop naturally
terminates once status changes.

"Local Windows Postgres was already occupying port 5432, causing password auth to hit the wrong server. Moved Docker Postgres to port 5433 to avoid conflict."

Bug: dataset generator wrote a double-timezone timestamp ("+00:00Z"), Postgres
rejected it as invalid. Fixed by removing the extra "Z" since isoformat()
already includes the UTC offset.

Note: full 200-record batch takes several minutes because ~half the records
route through an Ollama LLM call (message generation) sequentially on CPU.
This is expected batch-processing behavior, not a bug.

Bug: had two get_audit_trail functions defined for the same route — the older one (returning a flat list) silently took precedence over the new summary+steps version. Fixed by removing the duplicate."


---

Bug: Simulate feature initially showed no delay and no LLM-generated message for
several test cases — turned out those specific inputs (soft decline + recurring +
retry succeeded, or opted-out customer) never reach the LLM node at all by design,
since retry_charge and blocked paths don't call execute's message branch. Not a
bug — confirmed correct routing by testing CARD_EXPIRED (hard decline) instead.

---

Bug: compliance_gate checked business hours (8am-7pm) using UTC instead of IST,
causing incorrect blocks even during valid Indian business hours (e.g. blocked at
what was actually 10:30am IST because the server read it as 5:00am UTC). Fixed by
converting to IST (UTC+5:30) before the hour check.

---

Feature: Added a "Simulate a Payment" interactive panel (/simulate endpoint +
frontend form) so a judge/reviewer can input any decline reason, amount, and
recurring/opt-out flags and watch the agent's live decision + full audit trail,
without needing to browse the pre-run batch. Reused the same generate_summary()
helper as the ledger for consistency.

Bug: ChatOllama had no timeout, so if Ollama was down, the request hung indefinitely with no feedback. Fixed with client_kwargs={'timeout': 8.0} — now fails fast and the agent still completes gracefully (message just says '[LLM unavailable]'), rather than the whole request hanging

---

Bug: generate_summary() had no branch for the pending_approval case, so it
fell through to the generic "else" fallback while also picking the wrong
audit-log line as the "final status" — producing a garbled summary sentence
like "ended up 'Still pending after attempt 0...' because of the rules
below." Fixed by adding an explicit check for "requires human approval" in
the audit text, checked first in the if/elif chain.

---

Bug: compliance_gate originally required human approval for ANY high-value
(₹10,000+) payment, including message-only actions on hard declines (e.g. a
₹50,000 expired card). Since a message carries no financial risk — no money
moves — this was over-cautious. Fixed to only require approval when the
pending action is specifically retry_charge (i.e. money is about to move).

---

Feature: Added a human-in-the-loop approval queue for high-value
(₹10,000+) retry actions. compliance_gate now routes these to a
"pending_approval" status instead of executing automatically. New
endpoints: GET /approval-queue, GET /approval-stats,
POST /payments/{id}/approve, POST /payments/{id}/reject. The dashboard
shows a clickable banner with the pending amount/count, and a separate
"Approval Queue" page lists each request with its recovery probability.

---

Feature: Added a recovery-probability score per decline code, computed
from real historical outcomes in the batch (recovered count / total count
per decline_code) rather than a hardcoded or fake ML score. Hard-decline
codes correctly show 0% since they're never retried — this was a deliberate
signal that the number is genuine, not decorative.

---

Decision: Changed "Approved today" / "Rejected today" stats to all-time
totals ("Approved" / "Rejected"). Date-scoped stats reset misleadingly
across demo sessions (e.g. approvals done yesterday showed as 0 today),
which is confusing for a reviewer testing the app once rather than using
it daily.

Added a lightweight operator-token check on approve/reject endpoints — without it, anyone with the deployed URL could approve/reject payments directly via API, undermining the human-in-the-loop story.