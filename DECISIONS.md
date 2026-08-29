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