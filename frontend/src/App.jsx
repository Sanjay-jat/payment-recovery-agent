import { useEffect, useState } from "react";
import "./App.css";

const API = "http://localhost:8000";

export default function App() {
  const [dashboard, setDashboard] = useState(null);
  const [payments, setPayments] = useState([]);
  const [filter, setFilter] = useState("all");
  const [expandedId, setExpandedId] = useState(null);
  const [auditTrails, setAuditTrails] = useState({});

  useEffect(() => {
    fetch(`${API}/dashboard`).then(r => r.json()).then(setDashboard);
    fetch(`${API}/payments?limit=200`).then(r => r.json()).then(setPayments);
  }, []);

  const toggleExpand = async (id) => {
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    if (!auditTrails[id]) {
      const trail = await fetch(`${API}/payments/${id}/audit`).then(r => r.json());
      setAuditTrails(prev => ({ ...prev, [id]: trail }));
    }
  };

  const filtered = filter === "all" ? payments : payments.filter(p => p.status === filter);
  const recoveryPct = dashboard ? dashboard.recovery_rate_pct : 0;

  return (
    <div className="page">
      <header className="hero">
        <p className="eyebrow">Payment Recovery Agent</p>
        <h1>Revenue recovered, transparently.</h1>
        {dashboard && (
          <div className="hero-stats">
            <div className="ring" style={{ "--pct": recoveryPct }}>
              <span className="ring-number">{recoveryPct}%</span>
              <span className="ring-label">recovered</span>
            </div>
            <div className="hero-figures">
              <div>
                <span className="figure-value">
                  ₹{dashboard.recovered_amount.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                </span>
                <span className="figure-label">recovered of ₹{dashboard.total_amount.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</span>
              </div>
              <div>
                <span className="figure-value">{dashboard.recovered_count}/{dashboard.total_payments}</span>
                <span className="figure-label">payments resolved</span>
              </div>
            </div>
          </div>
        )}
      </header>

      {dashboard && (
        <section className="funnel">
          <h2>Retry funnel</h2>
          <p className="section-note">How many attempts it took to recover a payment</p>
          <div className="funnel-bars">
            {["attempt_1", "attempt_2", "attempt_3", "attempt_4"].map((key, i) => {
              const count = dashboard.retry_funnel[key] || 0;
              const max = Math.max(...Object.values(dashboard.retry_funnel), 1);
              return (
                <div className="funnel-row" key={key}>
                  <span className="funnel-index">0{i + 1}</span>
                  <div className="funnel-track">
                    <div className="funnel-fill" style={{ width: `${(count / max) * 100}%` }} />
                  </div>
                  <span className="funnel-count">{count}</span>
                </div>
              );
            })}
          </div>
        </section>
      )}

      <section className="ledger">
        <div className="ledger-header">
          <h2>The ledger</h2>
          <div className="filters">
            {["all", "recovered", "pending", "exhausted", "escalated", "blocked"].map(s => (
              <button
                key={s}
                className={filter === s ? "filter active" : "filter"}
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
                <span className="decline-code">{p.decline_code}</span>
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
                        <span className="trail-node">{step.node}</span>
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
  );
}