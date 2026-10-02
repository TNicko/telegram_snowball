-- Telegram Snowball schema. Applied on API/worker boot.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS telegram_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id BIGINT NOT NULL UNIQUE,
    phone TEXT,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    photo_path TEXT,
    photo_media_kind TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE telegram_accounts ADD COLUMN IF NOT EXISTS photo_path TEXT;
ALTER TABLE telegram_accounts ADD COLUMN IF NOT EXISTS photo_media_kind TEXT;

-- v1: at most one Telethon session.
CREATE TABLE IF NOT EXISTS telegram_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES telegram_accounts (id) ON DELETE CASCADE,
    session_enc TEXT NOT NULL,
    auth_state TEXT NOT NULL DEFAULT 'healthy',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT telegram_sessions_singleton CHECK (id IS NOT NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS telegram_sessions_one_row
    ON telegram_sessions ((true));

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    progress JSONB NOT NULL DEFAULT '{}'::jsonb,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS jobs_status_created_idx ON jobs (status, created_at);

CREATE TABLE IF NOT EXISTS peers (
    external_id BIGINT PRIMARY KEY,
    peer_type TEXT NOT NULL,
    title TEXT,
    username TEXT,
    access_hash BIGINT,
    about TEXT,
    participants_count INTEGER,
    photo_path TEXT,
    photo_media_kind TEXT,
    is_scraping BOOLEAN NOT NULL DEFAULT false,
    scrape_detail TEXT,
    messages_scraped INTEGER NOT NULL DEFAULT 0,
    last_message_id INTEGER,
    last_message_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT peers_type_check CHECK (
        peer_type = ANY (ARRAY['channel', 'megagroup', 'chat', 'user', 'bot'])
    )
);

CREATE INDEX IF NOT EXISTS peers_username_idx ON peers (lower(username));
CREATE INDEX IF NOT EXISTS peers_updated_idx ON peers (updated_at DESC);
CREATE INDEX IF NOT EXISTS peers_created_idx ON peers (created_at DESC);

ALTER TABLE peers ADD COLUMN IF NOT EXISTS photo_media_kind TEXT;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS usernames JSONB;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS first_name TEXT;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS last_name TEXT;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS telegram_date TIMESTAMPTZ;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS verified BOOLEAN;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS scam BOOLEAN;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS fake BOOLEAN;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS restricted BOOLEAN;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS restriction_reason JSONB;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS noforwards BOOLEAN;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS forum BOOLEAN;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS gigagroup BOOLEAN;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS join_to_send BOOLEAN;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS join_request BOOLEAN;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS has_link BOOLEAN;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS has_geo BOOLEAN;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS deleted BOOLEAN;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS premium BOOLEAN;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS deactivated BOOLEAN;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS linked_chat_id BIGINT;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS linked_monoforum_id BIGINT;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS migrated_from_chat_id BIGINT;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS migrated_to_channel_id BIGINT;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS slowmode_enabled BOOLEAN;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS slowmode_seconds INTEGER;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS hidden_prehistory BOOLEAN;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS available_min_id INTEGER;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS participants_hidden BOOLEAN;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS admins_count INTEGER;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS kicked_count INTEGER;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS banned_count INTEGER;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS online_count INTEGER;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS ttl_period INTEGER;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS pinned_msg_id INTEGER;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS location_address TEXT;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS location_lat DOUBLE PRECISION;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS location_lng DOUBLE PRECISION;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS common_chats_count INTEGER;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS first_message_id INTEGER;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS first_message_at TIMESTAMPTZ;

UPDATE telegram_accounts a
SET photo_path = p.photo_path
FROM peers p
WHERE a.telegram_user_id = p.external_id
  AND a.photo_path IS NULL
  AND p.photo_path IS NOT NULL;

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    peer_external_id BIGINT NOT NULL REFERENCES peers (external_id) ON DELETE CASCADE,
    telegram_message_id INTEGER NOT NULL,
    date TIMESTAMPTZ NOT NULL,
    content TEXT,
    from_external_id BIGINT,
    fwd_from JSONB,
    media JSONB,
    UNIQUE (peer_external_id, telegram_message_id)
);

ALTER TABLE messages ADD COLUMN IF NOT EXISTS text_embedded BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS image_embedded BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS messages_peer_date_idx
    ON messages (peer_external_id, date DESC);

CREATE INDEX IF NOT EXISTS messages_date_idx
    ON messages (date DESC);

-- Message-history coverage. Missing row → Posts shows "—".
CREATE TABLE IF NOT EXISTS peer_fetch_coverage (
    peer_external_id BIGINT PRIMARY KEY REFERENCES peers (external_id) ON DELETE CASCADE,
    covered_after TIMESTAMPTZ,
    covered_before TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Media-download coverage. Missing row → Images/Videos/… show "—".
CREATE TABLE IF NOT EXISTS peer_media_coverage (
    peer_external_id BIGINT PRIMARY KEY REFERENCES peers (external_id) ON DELETE CASCADE,
    covered_after TIMESTAMPTZ,
    covered_before TIMESTAMPTZ NOT NULL,
    videos_excluded BOOLEAN NOT NULL DEFAULT false,
    large_excluded BOOLEAN NOT NULL DEFAULT false,
    max_media_bytes BIGINT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS forward_edges (
    from_external_id BIGINT NOT NULL,
    to_external_id BIGINT NOT NULL,
    from_peer_type TEXT,
    to_peer_type TEXT,
    last_from_name TEXT,
    forward_count INTEGER NOT NULL DEFAULT 0,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (from_external_id, to_external_id)
);

ALTER TABLE forward_edges ADD COLUMN IF NOT EXISTS from_peer_type TEXT;
ALTER TABLE forward_edges ADD COLUMN IF NOT EXISTS to_peer_type TEXT;
ALTER TABLE forward_edges ADD COLUMN IF NOT EXISTS last_from_name TEXT;
ALTER TABLE forward_edges ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS forward_edges_from_count_idx
    ON forward_edges (from_external_id, forward_count DESC);
CREATE INDEX IF NOT EXISTS forward_edges_to_count_idx
    ON forward_edges (to_external_id, forward_count DESC);

-- Fan-out: each forwarded message on a unique (from → to) edge.
CREATE TABLE IF NOT EXISTS forward_edge_messages (
    from_external_id BIGINT NOT NULL,
    to_external_id BIGINT NOT NULL,
    message_id UUID NOT NULL REFERENCES messages (id) ON DELETE CASCADE,
    message_date TIMESTAMPTZ NOT NULL,
    telegram_message_id INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (from_external_id, to_external_id, message_id)
);

CREATE INDEX IF NOT EXISTS forward_edge_messages_from_idx
    ON forward_edge_messages (from_external_id);
CREATE INDEX IF NOT EXISTS forward_edge_messages_to_idx
    ON forward_edge_messages (to_external_id);
CREATE INDEX IF NOT EXISTS forward_edge_messages_message_idx
    ON forward_edge_messages (message_id);
CREATE INDEX IF NOT EXISTS forward_edge_messages_date_idx
    ON forward_edge_messages (message_date DESC);

-- One row per unique exact 16-hex pHash. Canonical file is never replaced.
CREATE TABLE IF NOT EXISTS image_blobs (
    phash TEXT PRIMARY KEY,
    canonical_path TEXT,
    refcount INTEGER NOT NULL DEFAULT 1,
    image_embedded BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT image_blobs_phash_hex_chk CHECK (phash ~ '^[0-9a-f]{16}$'),
    CONSTRAINT image_blobs_refcount_chk CHECK (refcount >= 0)
);

-- Fan-out: exact pHash → every message it appeared in.
CREATE TABLE IF NOT EXISTS image_blob_messages (
    phash TEXT NOT NULL REFERENCES image_blobs (phash) ON DELETE CASCADE,
    message_id UUID NOT NULL REFERENCES messages (id) ON DELETE CASCADE,
    message_date TIMESTAMPTZ NOT NULL,
    peer_external_id BIGINT NOT NULL REFERENCES peers (external_id) ON DELETE CASCADE,
    telegram_message_id INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (phash, message_id),
    CONSTRAINT image_blob_messages_phash_hex_chk CHECK (phash ~ '^[0-9a-f]{16}$')
);

CREATE INDEX IF NOT EXISTS image_blob_messages_message_idx
    ON image_blob_messages (message_id);
CREATE INDEX IF NOT EXISTS image_blob_messages_peer_idx
    ON image_blob_messages (peer_external_id);
CREATE INDEX IF NOT EXISTS image_blob_messages_date_idx
    ON image_blob_messages (message_date DESC);

ALTER TABLE image_blobs ALTER COLUMN canonical_path DROP NOT NULL;

CREATE TABLE IF NOT EXISTS image_cache (
    phash TEXT PRIMARY KEY REFERENCES image_blobs (phash) ON DELETE CASCADE,
    cache_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS image_cache_created_idx ON image_cache (created_at ASC);

CREATE INDEX IF NOT EXISTS messages_video_kind_idx
    ON messages ((media->>'kind'))
    WHERE media->>'kind' = 'video';

CREATE INDEX IF NOT EXISTS messages_video_document_idx
    ON messages ((media->>'document_id'))
    WHERE media->>'kind' = 'video' AND media->>'document_id' IS NOT NULL;

UPDATE image_blob_messages ibm
SET telegram_message_id = msg.telegram_message_id
FROM messages msg
WHERE ibm.message_id = msg.id
  AND ibm.telegram_message_id IS NULL;

-- Fixed-width pgvector slots. Shorter models are L2-normalized then zero-padded
-- so cosine order is unchanged. Width covers MobileNet (1280) and BGE-M3 (1024).
CREATE TABLE IF NOT EXISTS message_text_embeddings (
    message_id UUID PRIMARY KEY REFERENCES messages (id) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    dim SMALLINT NOT NULL,
    embedding vector(1280) NOT NULL
);

CREATE INDEX IF NOT EXISTS message_text_embeddings_hnsw
    ON message_text_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS message_text_embeddings_model_idx
    ON message_text_embeddings (model_id);

CREATE TABLE IF NOT EXISTS image_embeddings (
    phash TEXT PRIMARY KEY REFERENCES image_blobs (phash) ON DELETE CASCADE,
    model_id TEXT NOT NULL,
    dim SMALLINT NOT NULL,
    embedding vector(1280) NOT NULL,
    CONSTRAINT image_embeddings_phash_hex_chk CHECK (phash ~ '^[0-9a-f]{16}$')
);

CREATE INDEX IF NOT EXISTS image_embeddings_hnsw
    ON image_embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS image_embeddings_model_idx
    ON image_embeddings (model_id);

CREATE INDEX IF NOT EXISTS messages_text_embed_pending_idx
    ON messages (peer_external_id)
    WHERE text_embedded = false AND NULLIF(BTRIM(content), '') IS NOT NULL;

CREATE INDEX IF NOT EXISTS image_blobs_embed_pending_idx
    ON image_blobs (phash)
    WHERE image_embedded = false;

-- Scope: vision-space steering. Scores live on peers; inputs are user prompts/files.
ALTER TABLE peers ADD COLUMN IF NOT EXISTS scope_r DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS scope_j INTEGER NOT NULL DEFAULT 0;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS scope_score DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS forward_r DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS forward_j INTEGER NOT NULL DEFAULT 0;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS forward_n_events INTEGER NOT NULL DEFAULT 0;
ALTER TABLE peers ADD COLUMN IF NOT EXISTS forward_score DOUBLE PRECISION NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS peers_scope_score_idx ON peers (scope_score DESC);
CREATE INDEX IF NOT EXISTS peers_forward_score_idx ON peers (forward_score DESC);

CREATE TABLE IF NOT EXISTS scope_state (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    tau DOUBLE PRECISION NOT NULL DEFAULT 0.4,
    gamma DOUBLE PRECISION NOT NULL DEFAULT 2.0,
    alpha DOUBLE PRECISION NOT NULL DEFAULT 2.0,
    delta DOUBLE PRECISION NOT NULL DEFAULT 0.15,
    lambda_fwd DOUBLE PRECISION NOT NULL DEFAULT 0.05,
    version INTEGER NOT NULL DEFAULT 0,
    last_rerank_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO scope_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS scope_inputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind TEXT NOT NULL CHECK (kind IN ('text', 'file')),
    body TEXT NOT NULL,
    filename TEXT,
    content_type TEXT,
    embedding vector(1280),
    model_id TEXT,
    dim SMALLINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS image_scope_scores (
    phash TEXT PRIMARY KEY REFERENCES image_blobs (phash) ON DELETE CASCADE,
    s DOUBLE PRECISION NOT NULL,
    r DOUBLE PRECISION NOT NULL,
    version INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT image_scope_scores_phash_hex_chk CHECK (phash ~ '^[0-9a-f]{16}$')
);

CREATE INDEX IF NOT EXISTS image_scope_scores_version_idx ON image_scope_scores (version);

-- Unique phashes credited to a peer's scrape (scope) or origin (forward) mix.
CREATE TABLE IF NOT EXISTS peer_scope_evidence (
    peer_external_id BIGINT NOT NULL REFERENCES peers (external_id) ON DELETE CASCADE,
    pile TEXT NOT NULL CHECK (pile IN ('scope', 'forward')),
    phash TEXT NOT NULL,
    PRIMARY KEY (peer_external_id, pile, phash),
    CONSTRAINT peer_scope_evidence_phash_hex_chk CHECK (phash ~ '^[0-9a-f]{16}$')
);

CREATE INDEX IF NOT EXISTS peer_scope_evidence_pile_idx
    ON peer_scope_evidence (pile, phash);

-- One row per forwarded image occurrence, so events stay idempotent on re-score.
CREATE TABLE IF NOT EXISTS peer_scope_forward_events (
    origin_peer_id BIGINT NOT NULL REFERENCES peers (external_id) ON DELETE CASCADE,
    message_id UUID NOT NULL REFERENCES messages (id) ON DELETE CASCADE,
    phash TEXT NOT NULL,
    PRIMARY KEY (message_id, phash),
    CONSTRAINT peer_scope_forward_events_phash_hex_chk CHECK (phash ~ '^[0-9a-f]{16}$')
);

CREATE INDEX IF NOT EXISTS peer_scope_forward_events_origin_idx
    ON peer_scope_forward_events (origin_peer_id);

-- Running totals for the catalog. Updated as rows are inserted, never by scanning messages.
CREATE TABLE IF NOT EXISTS peer_counts (
    peer_external_id BIGINT PRIMARY KEY REFERENCES peers (external_id) ON DELETE CASCADE,
    posts INTEGER NOT NULL DEFAULT 0,
    text_total INTEGER NOT NULL DEFAULT 0,
    text_embedded INTEGER NOT NULL DEFAULT 0,
    image_total INTEGER NOT NULL DEFAULT 0,
    image_hashed INTEGER NOT NULL DEFAULT 0,
    image_downloaded INTEGER NOT NULL DEFAULT 0,
    image_unique INTEGER NOT NULL DEFAULT 0,
    image_persisted INTEGER NOT NULL DEFAULT 0,
    image_embeddable INTEGER NOT NULL DEFAULT 0,
    image_embedded_unique INTEGER NOT NULL DEFAULT 0,
    video_total INTEGER NOT NULL DEFAULT 0,
    video_downloaded INTEGER NOT NULL DEFAULT 0,
    audio_total INTEGER NOT NULL DEFAULT 0,
    audio_downloaded INTEGER NOT NULL DEFAULT 0,
    gif_total INTEGER NOT NULL DEFAULT 0,
    gif_downloaded INTEGER NOT NULL DEFAULT 0,
    document_total INTEGER NOT NULL DEFAULT 0,
    document_downloaded INTEGER NOT NULL DEFAULT 0,
    unique_forwards INTEGER NOT NULL DEFAULT 0,
    total_forwards INTEGER NOT NULL DEFAULT 0
);
