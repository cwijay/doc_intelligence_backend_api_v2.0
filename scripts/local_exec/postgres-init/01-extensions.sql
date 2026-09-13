-- Runs once, on first boot of an empty data volume.
-- pgvector is required by biz2bricks_core's AI models (RAG semantic caching).
CREATE EXTENSION IF NOT EXISTS vector;
