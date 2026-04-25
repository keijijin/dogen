CREATE TABLE chat_session (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    client_subject VARCHAR(256),
    volume_scope VARCHAR(512)
);

CREATE TABLE chat_message (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES chat_session (id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_message_session ON chat_message (session_id, created_at);

CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    event VARCHAR(64) NOT NULL,
    payload_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE user_feedback (
    id UUID PRIMARY KEY,
    message_id UUID NOT NULL REFERENCES chat_message (id) ON DELETE CASCADE,
    rating SMALLINT NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
