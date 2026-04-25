CREATE TABLE rag_chunk (
    id BIGSERIAL PRIMARY KEY,
    volume_key VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    embedding DOUBLE PRECISION[]
);

CREATE INDEX idx_rag_chunk_volume ON rag_chunk (volume_key);
