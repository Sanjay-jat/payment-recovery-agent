Bug: When retries were exhausted, the graph ended immediately without sending a
final message to the customer — should_continue was checking retry_count < max_retries,
which cut the loop before decide_action could route to send_message.
Fix: should_continue now only checks status == "pending"; decide_action already
handles routing to send_message once retries are exhausted, so the loop naturally
terminates once status changes.