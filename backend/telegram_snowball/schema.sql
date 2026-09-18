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
    forward_count INTEGER NOT NULL DEFAULT 0,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (from_external_id, to_external_id)
);
