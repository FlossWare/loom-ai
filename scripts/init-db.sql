-- loom-ai PostgreSQL schema
-- Run: psql -U loom -d loom -f init-db.sql

CREATE EXTENSION IF NOT EXISTS vector;

-- auth schema for API keys (used by FreeModelRouter)
CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE IF NOT EXISTS auth.secrets (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT DEFAULT '',
    tags JSONB DEFAULT '{}',
    encrypted BOOLEAN DEFAULT false
);

-- documents, chunks, embeddings (storage backend)
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    url TEXT DEFAULT '',
    category TEXT DEFAULT '',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content TEXT NOT NULL DEFAULT '',
    chunk_index INTEGER NOT NULL DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS embeddings (
    id TEXT PRIMARY KEY,
    chunk_id TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    vector JSONB,
    model TEXT DEFAULT '',
    provider TEXT DEFAULT '',
    dimensions INTEGER DEFAULT 0
);

-- full-text + semantic search index
CREATE TABLE IF NOT EXISTS search_index (
    chunk_id TEXT PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
    content TEXT NOT NULL DEFAULT '',
    vector JSONB,
    document_title TEXT DEFAULT '',
    source TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_search_index_fts
    ON search_index USING gin(to_tsvector('english', content));

-- secrets (encrypted-at-rest via loom-ai)
CREATE TABLE IF NOT EXISTS secrets (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- persistent memory
CREATE TABLE IF NOT EXISTS memories (
    id TEXT NOT NULL,
    name TEXT PRIMARY KEY,
    content TEXT NOT NULL DEFAULT '',
    memory_type TEXT DEFAULT '',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- knowledge store (RAG pipeline)
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    metadata JSONB DEFAULT '{}'
);
