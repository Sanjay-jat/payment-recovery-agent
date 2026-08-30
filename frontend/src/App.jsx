import { useEffect, useState } from "react";
import { Search, GitBranch, ShieldCheck, Zap, Activity, Check, ArrowRight, PlayCircle } from "lucide-react";
import "./App.css";

const API = "http://localhost:8000";

const STATUS_LABELS = {
  recovered: "Payment recovered",
  escalated: "Recovery message sent",
  exhausted: "Recovery message sent",
  blocked: "Action blocked",
  pending: "Retry in progress",
};


const AGENT_STEPS = [
  {
    icon: Search,
    label: "Detect decline",
    detail: "The agent reads the failure reason code and classifies it as a soft decline (recoverable — e.g. a bank timeout) or a hard decline (permanent — e.g. an expired card).",
  },
  {
    icon: GitBranch,
    label: "Decide action",
    detail: "Based on the decline type and whether the payment method is a saved/recurring instrument, the agent picks one of two paths: silently retry the charge, or draft a customer-facing reminder.",
  },
  {
    icon: ShieldCheck,
    label: "Compliance check",
    detail: "Before anything executes, the action is checked against hard rules: contact hours (8am–7pm), retry limits, opt-out status, and whether the payment even has a valid stored authorization to retry.",
  },
  {
    icon: Zap,
    label: "Execute",
    detail: "If allowed, the agent either triggers the retry or generates a short, polite reminder message in Hinglish/English via an LLM — never both, and never more than the compliance check allows.",
  },
  {
    icon: Activity,
    label: "Track outcome",
    detail: "The result — recovered, exhausted, escalated, or blocked — is logged with full reasoning to the audit trail, which is what powers every row in the ledger below.",
  },
];

// Pick a diverse, representative sample instead of dumping the full batch
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
  const [declineCodes, setDeclineCodes] = useState([]);
  const [simForm, setSimForm] = useState({ amount: 5000, decline_code: "", is_recurring: true, opted_out: false });
  const [simResult, setSimResult] = useState(null);
  const [simLoading, setSimLoading] = useState(false);
  const [dashboard, setDashboard] = useState(null);
  const [payments, setPayments] = useState([]);
  const [filter, setFilter] = useState("all");
  const [expandedId, setExpandedId] = useState(null);
  const [auditTrails, setAuditTrails] = useState({});
  const [showAgentFlow, setShowAgentFlow] = useState(false);
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    fetch(`${API}/dashboard`).then(r => r.json()).then(setDashboard);
    fetch(`${API}/payments?limit=200`).then(r => r.json()).then(data => setPayments(curateSample(data)));
    fetch(`${API}/decline-codes`).then(r => r.json()).then(codes => {
      setDeclineCodes(codes);
      setSimForm(f => ({ ...f, decline_code: codes[0] }));
    });
  }, []);

  const runSimulation = async () => {
    setSimLoading(true);
    setSimResult(null);
    const result = await fetch(`${API}/simulate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(simForm),
    }).then(r => r.json());
    setSimResult(result);
    setSimLoading(false);
  };
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

  const filtered = filter === "all" ? payments : payments.filter(p => p.status === filter);
  const recentActivity = payments.slice(0, 5);
  const blockedCount = dashboard?.status_breakdown?.blocked || 0;

  return (
    <>
      <div className="topbar">
        <div className="brand">
          <div className="brand-mark">R</div>
          <span className="brand-name">Recoverly</span>
        </div>
        <div className="topbar-right">
          <span className="topbar-status">
            <span className="status-dot" /> Agent active
          </span>
        </div>
      </div>

      <div className="page">
        <header className="hero">
          <h1>AI Revenue Recovery Agent</h1>
          <p className="subtitle">
            Recoverly detects payment failures, understands why they happened,
            and takes the right recovery action automatically — with every
            decision logged and explainable.
          </p>
          <div className="hero-actions">
            <button className="btn-primary" onClick={() => scrollTo(".ledger-header")}>
              View recoveries <ArrowRight size={15} />
            </button>
            <button className="btn-secondary" onClick={handleExploreAgent}>
              Explore agent
            </button>
          </div>
        </header>

        {dashboard && (
          <section className="metrics">
            <div className="metric-card">
              <span className="metric-label">Amount recovered</span>
              <span className="metric-value mono">
                ₹{dashboard.recovered_amount.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
              </span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Payments resolved</span>
              <span className="metric-value mono">{dashboard.recovered_count}/{dashboard.total_payments}</span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Recovery rate</span>
              <span className="metric-value mono brand">{dashboard.recovery_rate_pct}%</span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Needs attention</span>
              <span className="metric-value mono">{blockedCount}</span>
            </div>
          </section>
        )}

        {showAgentFlow && (
          <section className="panel agent-flow-section">
            <h2>How the agent thinks</h2>
            <p className="section-body">
              Click any step to see exactly what the agent checks and decides at that point.
            </p>

            <div className="flow-track">
              {AGENT_STEPS.map((step, i) => (
                <div className="flow-track-item" key={i}>
                  <button
                    className={`flow-node-btn ${activeStep === i ? "active" : ""}`}
                    onClick={() => setActiveStep(i)}
                  >
                    <step.icon size={18} />
                  </button>
                  <span className={`flow-node-caption ${activeStep === i ? "active" : ""}`}>
                    {step.label}
                  </span>
                  {i < AGENT_STEPS.length - 1 && (
                    <div className={`flow-track-line ${activeStep > i ? "filled" : ""}`} />
                  )}
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
          <p className="section-body">
            Simulate any failed payment and watch the agent decide, live.
          </p>

          <div className="sim-form">
            <div className="sim-field">
              <label>Amount (₹)</label>
              <input
                type="number"
                value={simForm.amount}
                onChange={e => setSimForm({ ...simForm, amount: parseFloat(e.target.value) })}
              />
            </div>

            <div className="sim-field">
              <label>Decline reason</label>
              <select
                value={simForm.decline_code}
                onChange={e => setSimForm({ ...simForm, decline_code: e.target.value })}
              >
                {declineCodes.map(code => <option key={code} value={code}>{code}</option>)}
              </select>
            </div>

            <div className="sim-toggles">
              <label className="sim-toggle">
                <input
                  type="checkbox"
                  checked={simForm.is_recurring}
                  onChange={e => setSimForm({ ...simForm, is_recurring: e.target.checked })}
                />
                Recurring / saved instrument
              </label>
              <label className="sim-toggle">
                <input
                  type="checkbox"
                  checked={simForm.opted_out}
                  onChange={e => setSimForm({ ...simForm, opted_out: e.target.checked })}
                />
                Customer opted out of contact
              </label>
            </div>

            <button className="btn-primary sim-run" onClick={runSimulation} disabled={simLoading}>
              <PlayCircle size={16} /> {simLoading ? "Running..." : "Run agent"}
            </button>
          </div>

          {simResult && (
            <div className="trail sim-trail">
              <p className="trail-summary">{simResult.summary}</p>
              <p className="trail-summary" style={{background: "transparent", padding: 0, fontWeight: 500}}>
                Final status: <strong>{simResult.final_status}</strong> · {simResult.retry_count} retries used
              </p>
              {simResult.steps.map((line, i) => (
                <div className="trail-step" key={i}>
                  <div className="trail-dot" />
                  <div className="trail-content">
                    <span className="trail-message">{line}</span>
                  </div>
                </div>
              ))}
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
              {["all", "recovered", "pending", "exhausted", "escalated", "blocked"].map(s => (
                <button
                  key={s}
                  className={filter === s ? "chip active" : "chip"}
                  onClick={() => setFilter(s)}
                >
                  {s}
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
                  <span className={`status-pill status-${p.status}`}>{p.status}</span>
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
    </>
  );
}