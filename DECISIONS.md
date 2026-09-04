Decisions & Issues Log

A running record of what was decided, what broke, and why — kept during the build rather than reconstructed after, for the Razorpay AI Buildathon 2026 (Track 03: AI Revenue Recovery) submission.

Scope decisions

Chose Track 03 (AI Revenue Recovery) over AI Growth & Agentic Commerce, AI Risk Manager, AI Finance Controller, and Open Track. Reasoning: Track 1 was expected to be the most crowded/shallow-demo-prone track; Track 3's "Payment degradation → root cause → recovery action" example direction mapped directly to a learnable, well-scoped LangGraph problem.

Scoped to failed-payment recovery only — not checkout abandonment, not B2B receivables. One thing done rigorously beats four things done shallowly.

Refined understanding of what "retry" can honestly mean: silent, automatic retry is only possible for recurring/mandate-based payments (subscriptions, UPI autopay, e-mandates) because only those have a stored authorization to charge against. A one-time checkout payment with no saved instrument can never be silently retried, no matter how obviously temporary the failure was — the only honest action there is a customer-facing reminder. This is why the recovery rate sits around 38%, not 90%+.

Added real-world safety guardrails deliberately kept simple: never retry a non-recurring payment, respect playbook retry-delay timing (logged, not literally slept), an idempotency key per retry attempt to prevent double-charging, and honoring a customer opt-out flag.

Bugs found and fixed

Bug: double-timezone timestamp in the dataset generator. generate_dataset.py wrote failed_at as isoformat() + "Z", but isoformat() on a timezone-aware datetime already includes the UTC offset (+00:00), producing an invalid string like "...+00:00Z" that Postgres rejected. Fixed by dropping the extra "Z".

Bug: LangGraph loop ended before routing a fully-retried payment to a final message. should_continue originally checked retry_count < max_retries to decide whether to loop — so the moment the last retry was used, the graph ended immediately, skipping the step where decide_action would have routed to send_message once retries were exhausted. Fixed by having should_continue only check status == "pending"; decide_action already handles routing to a final message once retries run out, so the loop naturally terminates once status changes.

Bug: Ollama unreachable from WSL2 via 127.0.0.1. WSL2's networking doesn't forward 127.0.0.1 to the Windows host by default. Fixed by resolving the Windows host IP via ip route show default | awk '{print $3}' and passing it as base_url to ChatOllama. Documented that this IP can change on restart.

Bug: compliance_gate checked business hours in UTC instead of IST. The 8am–7pm contact-hours rule was being evaluated against server UTC time, so a message could be incorrectly blocked at what was actually a valid hour in India (e.g. blocked at server-read "5am" when it was really 10:30am IST). Fixed by converting to IST (UTC+5:30) before the hour check.

Bug: Postgres port conflict with a native Windows Postgres install. Docker's Postgres container and a pre-existing Windows Postgres both wanted port 5432, causing password-authentication failures that looked like a credentials problem but were actually a wrong-server problem. Fixed by mapping the Docker container to port 5433 instead.

Bug: no timeout on the Ollama LLM call. If Ollama was down, the /simulate request hung indefinitely with no feedback to the user. Fixed by adding client_kwargs={"timeout": 8.0} to ChatOllama — now it fails fast, and the agent still completes gracefully (the message just reads [LLM unavailable: ...]) instead of the whole request hanging.

Bug: duplicate get_audit_trail endpoint definitions. An older version of /payments/{id}/audit (returning a flat list) and a newer version (returning {summary, steps}) were both left in app/main.py. FastAPI silently used the first-registered one, so the frontend — built against the new format — crashed with Cannot read properties of undefined (reading 'map'). Fixed by deleting the duplicate.

Bug: generate_summary() had no branch for a blocked/high-value case. Before the approval queue existed, a hard-decline + opted-out combination fell through the if/elif chain into a generic fallback, producing an unhelpful summary sentence. After the approval queue was added, the same issue reappeared for pending_approval: the function fell into the "else" branch and also grabbed the wrong audit-log line as the "final status," producing a garbled sentence like "ended up 'Still pending after attempt 0...' because of the rules below." Fixed by adding an explicit check for "requires human approval" in the audit text, checked first.

Bug: high-value approval requirement applied even to message-only actions. Originally, any payment ≥ ₹10,000 required human approval regardless of whether the pending action was a retry (money moving) or a message (no money moving) — so even a ₹50,000 expired-card case, which was only ever going to get a reminder message, got stuck waiting on approval for no real reason. Fixed so the high-value check only fires when next_action == "retry_charge".

Bug: screenshots not rendering in the GitHub README. Markdown image syntax (![]()) doesn't reliably render when nested inside raw HTML <div> blocks — GitHub's renderer treats the div's contents as raw HTML rather than re-parsing markdown inside it. Fixed by using plain <img> tags instead of markdown image syntax wherever images sit inside a <div align="center">.

Bug: GitHub Docker port already bound, blocking local uvicorn. After running the full Docker Compose stack once, the containerized backend kept occupying port 8000, so a later attempt to run uvicorn locally failed with "Address already in use." Resolved by explicitly stopping the Docker backend/frontend containers when doing fast local iteration, and only rebuilding Docker when testing the containerized path.

Bug: Approved/Rejected stats reset misleadingly. The approval-queue stats originally scoped "Approved" and "Rejected" counts to "today" only (via a date filter on the audit log), so approvals done in an earlier session showed as 0 in a later one — confusing for a reviewer testing the app once rather than using it daily. Changed to all-time totals.

Bug: blank Approved/Rejected metric cards. After renaming the stats keys, the frontend rendered undefined (blank) instead of 0 when a count was legitimately zero. Fixed with a ?? 0 fallback in the JSX.

Features added beyond the base track requirements

Live "Try it yourself" simulator (/simulate endpoint + frontend panel): lets a reviewer pick any decline reason, amount, and recurring/opt-out combination and watch the agent's real decision and full audit trail render live, rather than only browsing a pre-run batch.

Human-in-the-loop approval queue for high-value (₹10,000+) retry actions: compliance_gate routes these to a pending_approval status instead of executing automatically. A separate "Payment approvals" page lists each request as a card with its amount, decline reason, and a recovery-probability score, with Approve/Reject actions. The main dashboard shows a clickable banner summarizing how much is waiting on approval.

Recovery-probability scoring, computed from real historical outcomes in the batch (recovered count ÷ total count per decline code) — not a decorative or hardcoded number. Hard-decline codes correctly show 0%, since they're never retried; this was a deliberate signal that the number is genuine rather than for show.

Operator-token guardrail on the approve/reject endpoints. Without it, anyone who had the deployed URL could call the API directly and approve/reject payments, which would undermine the human-in-the-loop story — a UI button alone isn't governance if the underlying endpoint has no access control. A demo token is shown in the UI and documented in the README for reviewers to test with.

Gemini BYOK (bring-your-own-key) support: the LLM provider is swappable between local Ollama (dev) and Gemini (deployed) via one config flag, and a deployed instance never needs the owner's own API key — a reviewer can paste their own Gemini key into the simulator, sent per-request only, never stored or logged.

"Cool Slate Minimal" visual redesign: took inspiration from a front-end design brief (teal accent, ink/paper palette, Inter + JetBrains Mono, restrained pill styles) and adapted it into the existing Vite/React app rather than doing a full framework migration — kept the existing stack, avoided scope creep into Next.js/TypeScript/Tailwind.

Notes on a competing public repo

While building, came across another public GitHub project attempting a similar payment-recovery agent concept. Its README made several unverifiable claims (unsourced "$500B" market-size figures, a static "Tests Passing" badge with no linked CI) and its WhatsApp-messaging feature relied on local browser automation (PyWhatKit), which only works on the presenter's own machine and can't be tested by a reviewer on a deployed instance. Rather than copying any of it, took inspiration from two ideas that were genuinely good — human-in-the-loop approval for high-value actions, and a visible recovery-confidence score — and implemented both independently, grounded in this project's own architecture and real historical batch data rather than a decorative number.