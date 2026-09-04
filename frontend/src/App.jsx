import { useEffect, useState } from "react";
import { Search, GitBranch, ShieldCheck, Zap, Activity, Check, ArrowRight, ShieldAlert, ArrowLeft } from "lucide-react";
import "./App.css";

const API = "https://payment-recovery-agent-q9bi.onrender.com";

const STATUS_LABELS = {
  recovered: "Payment recovered",
  escalated: "Recovery message sent",
  exhausted: "Recovery message sent",
  blocked: "Action blocked",
  pending: "Retry in progress",
  pending_approval: "Awaiting human approval",
};

const AGENT_STEPS = [
  { icon: Search, label: "Detect decline", detail: "First, it looks at why the payment failed. Some failures are temporary, like a bank timeout, and can be fixed with a retry. Others are permanent, like an expired card, and no amount of retrying will help." },
  { icon: GitBranch, label: "Decide action", detail: "Now it decides what to do. If the failure looks temporary and there is a saved card on file, it quietly tries the charge again. Otherwise, it writes a message to remind the customer instead." },
  { icon: ShieldCheck, label: "Compliance check", detail: "Before anything executes, the action is checked against hard rules: contact hours (8am–7pm IST), retry limits, opt-out status, whether the payment has a valid stored authorization to retry, and whether the amount requires human approval." },
  { icon: Zap, label: "Execute", detail: "Once it gets the green light, it takes one action only, either the retry or the message, never both, and never anything beyond what was approved." },
  { icon: Activity, label: "Track outcome", detail: "Whatever happens next, whether the payment gets recovered, escalated, or blocked, gets written down with the full reasoning behind it. That is exactly what you are seeing in the ledger below." },
];

function curateSample(list, perStatus = 4, cap = 18) {
  const buckets = {};
  list.forEach(p => {
    if (!buckets[p.status]) buckets[p.status] = [];
    buckets[p.status].push(p);
  });
  const picks = [];
  Object.values(buckets).forEach(arr => picks.push(...arr.slice(0, perStatus)));
  return picks.slice(0, cap);
}

export default function App() {
  const [view, setView] = useState("dashboard"); // "dashboard" | "approvals"
  const [dashboard, setDashboard] = useState(null);
  const [payments, setPayments] = useState([]);
  const [filter, setFilter] = useState("all");
  const [expandedId, setExpandedId] = useState(null);
  const [auditTrails, setAuditTrails] = useState({});
  const [showAgentFlow, setShowAgentFlow] = useState(false);
  const [activeStep, setActiveStep] = useState(0);

  const [declineCodes, setDeclineCodes] = useState([]);
  const [simForm, setSimForm] = useState({ amount: 5000, decline_code: "", is_recurring: true, opted_out: false });
  const [simResult, setSimResult] = useState(null);
  const [simLoading, setSimLoading] = useState(false);
  const [geminiKey, setGeminiKey] = useState("");

  const [queue, setQueue] = useState([]);
  const [approvalStats, setApprovalStats] = useState(null);
  const [actingOn, setActingOn] = useState(null);
  const [operatorToken, setOperatorToken] = useState(localStorage.getItem("operatorToken") || "");

  const loadDashboardData = () => {
    fetch(`${API}/dashboard`).then(r => r.json()).then(setDashboard);
    fetch(`${API}/payments?limit=200`).then(r => r.json()).then(data => setPayments(curateSample(data)));
  };

  const loadApprovalData = () => {
    fetch(`${API}/approval-queue`)
      .then(r => r.json())
      .then(data => setQueue(Array.isArray(data) ? data : []))
      .catch(() => setQueue([]));
    fetch(`${API}/approval-stats`)
      .then(r => r.json())
      .then(setApprovalStats)
      .catch(() => setApprovalStats(null));
  };

  useEffect(() => {
    loadDashboardData();
    loadApprovalData();
    fetch(`${API}/decline-codes`).then(r => r.json()).then(codes => {
      setDeclineCodes(codes);
      setSimForm(f => ({ ...f, decline_code: codes[0] }));
    });
  }, []);

  const toggleExpand = async (id) => {
    if (expandedId === id) { setExpandedId(null); return; }
    setExpandedId(id);
    if (!auditTrails[id]) {
      const trail = await fetch(`${API}/payments/${id}/audit`).then(r => r.json());
      setAuditTrails(prev => ({ ...prev, [id]: trail }));
    }
  };

  const scrollTo = (selector) => {
    document.querySelector(selector)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const handleExploreAgent = () => {
    setShowAgentFlow(true);
    setTimeout(() => scrollTo(".agent-flow-section"), 50);
  };

  const saveOperatorToken = (token) => {
    setOperatorToken(token);
    localStorage.setItem("operatorToken", token);
  };

  const runSimulation = async () => {
    setSimLoading(true);
    setSimResult(null);
    try {
      const result = await fetch(`${API}/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(geminiKey ? { "X-Gemini-Key": geminiKey } : {}) },
        body: JSON.stringify(simForm),
      }).then(r => r.json());
      setSimResult(result);
    } catch (err) {
      setSimResult({ summary: "Something went wrong reaching the agent.", final_status: "error", retry_count: 0, steps: [] });
    } finally {
      setSimLoading(false);
    }
  };

  const actOnApproval = async (paymentId, action) => {
    setActingOn(paymentId);
    try {
      await fetch(`${API}/payments/${paymentId}/${action}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Operator-Token": operatorToken,
          ...(geminiKey ? { "X-Gemini-Key": geminiKey } : {}),
        },
      });
      loadApprovalData();
      loadDashboardData();
    } finally {
      setActingOn(null);
    }
  };

  const filtered = filter === "all" ? payments : payments.filter(p => p.status === filter);
  const recentActivity = payments.slice(0, 5);
  const blockedCount = dashboard?.status_breakdown?.blocked || 0;
  const pendingApprovalCount = dashboard?.pending_approval_count || 0;

  return (
    <>
      <div className="topbar">
        <div className="brand">
          <div className="brand-mark">R</div>
          <span className="brand-name">Recoverly</span>
        </div>
        <div className="topbar-right">
          {view === "dashboard" ? (
            <span className="topbar-status">
              <span className="status-dot" /> Agent active
            </span>
          ) : (
            <button className="topbar-link" onClick={() => setView("dashboard")}>
              <ArrowLeft size={15} /> Back to dashboard
            </button>
          )}
        </div>
      </div>

      {view === "dashboard" ? (
        <div className="page">
          <header className="hero">
            <h1>Recoverly</h1>
            <p className="subtitle">
              When a payment fails, Recoverly finds out why it happened and does
              something about it. It might retry the charge, send the customer a
              reminder, or flag it for you to check. You can see the reasoning
              behind every single decision it makes.
            </p>
            <div className="hero-actions">
              <button className="btn-primary" onClick={() => scrollTo(".ledger-header")}>
                View recoveries <ArrowRight size={15} />
              </button>
              <button className="btn-secondary" onClick={handleExploreAgent}>
                Explore agent
              </button>
              <button className="btn-secondary" onClick={() => setView("approvals")}>
                <ShieldAlert size={16} style={{ marginRight: 6 }} />
                waiting for approval-
                {pendingApprovalCount > 0 && <span className="topbar-badge">{pendingApprovalCount}</span>}
              </button>
            </div>
          </header>

          {dashboard && dashboard.pending_approval_count > 0 && (
            <div className="approval-banner" onClick={() => setView("approvals")}>
              <ShieldAlert size={16} />
              <span>
                <strong>₹{dashboard.pending_approval_amount.toLocaleString("en-IN")}</strong> across{" "}
                <strong>{dashboard.pending_approval_count}</strong> payments is waiting on your approval right now
              </span>
              <ArrowRight size={15} />
            </div>
          )}

          {dashboard && (
            <section className="metrics">
              <div className="metric-card">
                <span className="metric-label">Recovered so far</span>
                <span className="metric-value mono">
                  ₹{dashboard.recovered_amount.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                </span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Payments handled</span>
                <span className="metric-value mono">{dashboard.recovered_count}/{dashboard.total_payments}</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Success rate</span>
                <span className="metric-value mono brand">{dashboard.recovery_rate_pct}%</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Needs a look</span>
                <span className="metric-value mono">{blockedCount + pendingApprovalCount}</span>
              </div>
            </section>
          )}

          {showAgentFlow && (
            <section className="panel agent-flow-section">
              <h2>How the agent thinks</h2>
              <p className="section-body">Tap on any step below to see what happens at that point and why.</p>
              <div className="flow-track">
                {AGENT_STEPS.map((step, i) => (
                  <div className="flow-track-item" key={i}>
                    <button className={`flow-node-btn ${activeStep === i ? "active" : ""}`} onClick={() => setActiveStep(i)}>
                      <step.icon size={18} />
                    </button>
                    <span className={`flow-node-caption ${activeStep === i ? "active" : ""}`}>{step.label}</span>
                    {i < AGENT_STEPS.length - 1 && <div className={`flow-track-line ${activeStep > i ? "filled" : ""}`} />}
                  </div>
                ))}
              </div>
              <div className="flow-detail">
                <span className="flow-detail-index mono">0{activeStep + 1}</span>
                <div>
                  <h3>{AGENT_STEPS[activeStep].label}</h3>
                  <p>{AGENT_STEPS[activeStep].detail}</p>
                </div>
              </div>
            </section>
          )}

          <section className="panel">
            <h2>Try it yourself</h2>
            <p className="section-body">Simulate any failed payment and watch the agent decide, live.</p>
            <div className="sim-form">
              <div className="sim-field">
                <label>Amount (₹)</label>
                <input type="number" value={simForm.amount} onChange={e => setSimForm({ ...simForm, amount: parseFloat(e.target.value) })} />
              </div>
              <div className="sim-field">
                <label>Decline reason</label>
                <select value={simForm.decline_code} onChange={e => setSimForm({ ...simForm, decline_code: e.target.value })}>
                  {declineCodes.map(code => <option key={code} value={code}>{code}</option>)}
                </select>
              </div>
              <div className="sim-toggles">
                <label className="sim-toggle">
                  <input type="checkbox" checked={simForm.is_recurring} onChange={e => setSimForm({ ...simForm, is_recurring: e.target.checked })} />
                  Recurring / saved instrument
                </label>
                <label className="sim-toggle">
                  <input type="checkbox" checked={simForm.opted_out} onChange={e => setSimForm({ ...simForm, opted_out: e.target.checked })} />
                  Customer opted out of contact
                </label>
              </div>
              <div className="sim-field" style={{ gridColumn: "1 / -1" }}>
                <label>Gemini API key (optional — only needed when Ollama isn't available)</label>
                <input type="password" placeholder="Paste your Gemini API key to enable live messages" value={geminiKey} onChange={e => setGeminiKey(e.target.value)} />
              </div>
              <button className="btn-primary sim-run" onClick={runSimulation} disabled={simLoading}>
                {simLoading ? "Running..." : "Run agent"}
              </button>
            </div>

            {simResult && (
              <div className="trail sim-trail">
                <p className="trail-summary">{simResult.summary}</p>
                <p style={{ fontSize: 13, fontWeight: 500, marginBottom: 16 }}>
                  Final status: <strong>{simResult.final_status.replace("_", " ")}</strong> · {simResult.retry_count} retries used
                </p>
                {simResult.steps.map((line, i) => (
                  <div className="trail-step" key={i}>
                    <div className="trail-dot" />
                    <div className="trail-content"><span className="trail-message">{line}</span></div>
                  </div>
                ))}

                {simResult.final_status === "pending_approval" && (
                  <div className="approve-inline">
                    <p className="section-body" style={{ marginBottom: 12 }}>
                      This payment is ₹10,000+ — it needs a human to approve before anything happens.
                    </p>
                    <button
                      className="btn-primary"
                      onClick={async () => {
                        const res = await fetch(`${API}/simulate/approve`, {
                          method: "POST",
                          headers: { "Content-Type": "application/json", ...(geminiKey ? { "X-Gemini-Key": geminiKey } : {}) },
                          body: JSON.stringify({
                            amount: simForm.amount,
                            decline_code: simForm.decline_code,
                            next_action: simResult.pending_action,
                            retry_count: simResult.retry_count,
                          }),
                        }).then(r => r.json());
                        setSimResult({
                          ...simResult,
                          final_status: res.final_status,
                          steps: [...simResult.steps, res.line],
                        });
                      }}
                    >
                      Approve now
                    </button>
                  </div>
                )}
              </div>
            )}
          </section>

          <section className="panel">
            <h2>Recovery activity</h2>
            <div className="timeline">
              {recentActivity.map((p, i) => (
                <div className="timeline-item" key={p.payment_id}>
                  <div className={`timeline-dot ${p.status === "recovered" ? "done" : ""}`}>
                    {p.status === "recovered" && <Check size={11} strokeWidth={3} />}
                  </div>
                  <div className="timeline-content">
                    <div className="timeline-top">
                      <span className="timeline-title">{STATUS_LABELS[p.status] || p.status}</span>
                      <span className="mono timeline-amount">₹{p.amount.toLocaleString("en-IN")}</span>
                    </div>
                    <span className="timeline-meta mono">{p.decline_code}</span>
                  </div>
                  {i < recentActivity.length - 1 && <div className="timeline-connector" />}
                </div>
              ))}
            </div>
          </section>

          <section className="panel">
            <div className="ledger-header">
              <div>
                <h2>Payments</h2>
                <p className="ledger-caption">
                  Showing {payments.length} representative payments across every outcome, from a full batch of {dashboard?.total_payments || 200}.
                </p>
              </div>
              <div className="filters">
                {["all", "recovered", "pending", "exhausted", "escalated", "blocked", "pending_approval"].map(s => (
                  <button key={s} className={filter === s ? "chip active" : "chip"} onClick={() => setFilter(s)}>
                    {s.replace("_", " ")}
                  </button>
                ))}
              </div>
            </div>

            <div className="ledger-list">
              {filtered.map(p => (
                <div key={p.payment_id} className="ledger-item">
                  <div className="ledger-row" onClick={() => toggleExpand(p.payment_id)}>
                    <span className="mono id">{p.payment_id}</span>
                    <span className="mono amount">₹{p.amount.toLocaleString("en-IN")}</span>
                    <span className="mono decline-code">{p.decline_code}</span>
                    <span className={`status-pill status-${p.status}`}>{p.status.replace("_", " ")}</span>
                    <span className="chevron">{expandedId === p.payment_id ? "−" : "+"}</span>
                  </div>
                  {expandedId === p.payment_id && auditTrails[p.payment_id] && (
                    <div className="trail">
                      <p className="trail-summary">{auditTrails[p.payment_id].summary}</p>
                      {auditTrails[p.payment_id].steps.map((step, i) => (
                        <div className="trail-step" key={i}>
                          <div className="trail-dot" />
                          <div className="trail-content">
                            <span className="trail-node mono">{step.node}</span>
                            <span className="trail-message">{step.message}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        </div>
      ) : (
        <div className="page">
          <header className="hero" style={{ textAlign: "center" }}>
            <h1 style={{ fontSize: 28 }}>Payment approvals</h1>
            <p className="subtitle">
              Any high-value retry over ₹10,000 waits here for a person to sign off,
              so the agent never moves real money entirely on its own.
            </p>
            <div className="operator-token-field">
              <label>Operator token</label>
              <input
                type="password"
                placeholder="Enter operator token to approve/reject"
                value={operatorToken}
                onChange={e => saveOperatorToken(e.target.value)}
              />
              <span className="token-hint">Demo token: 12345</span>
            </div>
          </header>

          {approvalStats && (
            <section className="metrics">
              <div className="metric-card">
                <span className="metric-label">Pending</span>
                <span className="metric-value mono brand">{approvalStats.pending}</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Approved</span>
                <span className="metric-value mono">{approvalStats.approved_total ?? 0}</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Rejected</span>
                <span className="metric-value mono">{approvalStats.rejected_total ?? 0}</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Auto-resolved (below threshold)</span>
                <span className="metric-value mono">{approvalStats.auto_resolved}</span>
              </div>
            </section>
          )}

          <section className="panel">
            <h2>Pending approvals</h2>
            <p className="section-body">
              Each request shows the agent's intended action and its historical
              recovery probability for that decline reason, computed from the batch.
            </p>

            {queue.length === 0 && <p className="section-body">No pending approvals right now.</p>}
            <div className="queue-grid">
              {queue.map(item => (
                <div className="queue-card" key={item.payment_id}>
                  <div className="queue-card-top">
                    <div>
                      <span className="mono queue-amount">₹{item.amount.toLocaleString("en-IN")}</span>
                      <span className="mono queue-id">{item.payment_id}</span>
                    </div>
                    {item.recovery_probability !== null && (
                      <span className={`prob-pill ${item.recovery_probability >= 50 ? "prob-high" : "prob-low"}`}>
                        P(recovery) {item.recovery_probability}%
                      </span>
                    )}
                  </div>

                  <div className="queue-card-mid">
                    <span className="decline-code">{item.decline_code}</span>
                    <span className="queue-action">
                      {item.pending_action === "retry_charge" ? "→ wants to retry the charge" : "→ wants to message the customer"}
                    </span>
                  </div>

                  <div className="queue-card-buttons">
                    <button className="btn-reject" disabled={actingOn === item.payment_id} onClick={() => actOnApproval(item.payment_id, "reject")}>
                      Reject
                    </button>
                    <button className="btn-approve" disabled={actingOn === item.payment_id} onClick={() => actOnApproval(item.payment_id, "approve")}>
                      {actingOn === item.payment_id ? "Working..." : "Approve"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </>
  );
}