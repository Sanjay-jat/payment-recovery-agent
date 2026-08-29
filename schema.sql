-- Core table: one row per failed payment being tracked by the agent
CREATE TABLE payments (
    payment_id        TEXT PRIMARY KEY,
    customer_id       TEXT NOT NULL,
    amount            NUMERIC(10, 2) NOT NULL,
    channel           TEXT NOT NULL,
    decline_code      TEXT NOT NULL,
    decline_type      TEXT,
    is_recurring      BOOLEAN NOT NULL DEFAULT FALSE,
    opted_out         BOOLEAN NOT NULL DEFAULT FALSE,
    failed_at         TIMESTAMPTZ NOT NULL,
    retry_count       INT NOT NULL DEFAULT 0,
    max_retries       INT NOT NULL DEFAULT 4,
    status            TEXT NOT NULL DEFAULT 'pending',
    recovered_amount  NUMERIC(10, 2),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per retry/message attempt made on a payment
CREATE TABLE retry_attempts (
    id                SERIAL PRIMARY KEY,
    payment_id        TEXT NOT NULL REFERENCES payments(payment_id),
    attempt_number    INT NOT NULL,
    action_type       TEXT NOT NULL,
    idempotency_key   TEXT,
    outcome           TEXT,
    attempted_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Full audit trail: every decision the agent makes, with the reason
CREATE TABLE audit_log (
    id                SERIAL PRIMARY KEY,
    payment_id        TEXT NOT NULL REFERENCES payments(payment_id),
    node_name         TEXT NOT NULL,
    message           TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_payments_status ON payments(status);
CREATE INDEX idx_audit_payment ON audit_log(payment_id);