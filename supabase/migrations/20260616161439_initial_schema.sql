-- PaperPilot initial schema on Supabase Postgres + pgvector.
-- Ported from the ClickHouse schema in paperpilot/clickhouse_client.py.
--
-- Design notes:
--   * Embeddings are vector(1536) (openai/text-embedding-3-small), replacing
--     ClickHouse Array(Float32). Cosine similarity uses the <=> operator.
--   * cfp and arxiv are shared, read-only corpora: readable by any authenticated
--     user, writable only by the service role (seed scripts and the backend).
--   * Per-user tables key user_id to auth.users(id) and are isolated by RLS to
--     (select auth.uid()) = user_id. The FastAPI backend connects as the service
--     role (app-enforced scoping); RLS protects any direct reads the Next.js
--     client makes (profile, evidence, sessions).
--   * ClickHouse ReplacingMergeTree soft-deletes become real rows with hard
--     DELETE in Postgres; the tombstone column is dropped.

create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------------------
-- Shared corpora (read-only to authenticated; writes via service role only)
-- ---------------------------------------------------------------------------

create table public.cfp (
    id          text primary key,
    name        text not null,
    scope       text not null default '',
    deadline    date,
    format      text not null default '',
    url         text not null default '',
    scope_emb   vector(1536)
);

create table public.arxiv (
    id          text primary key,
    title       text not null,
    abstract    text not null default '',
    year        smallint,
    authors     text[] not null default '{}',
    emb         vector(1536)
);

-- HNSW cosine indexes for similarity search.
create index cfp_scope_emb_hnsw on public.cfp using hnsw (scope_emb vector_cosine_ops);
create index arxiv_emb_hnsw on public.arxiv using hnsw (emb vector_cosine_ops);

-- ---------------------------------------------------------------------------
-- Per-user tables
-- ---------------------------------------------------------------------------

create table public.trace_log (
    id          bigint generated always as identity primary key,
    session_id  text not null,
    user_id     uuid references auth.users(id) on delete cascade,
    ts          timestamptz not null default now(),
    kind        text not null,
    payload     jsonb not null default '{}'::jsonb
);
create index trace_log_session_ts on public.trace_log (session_id, ts);
create index trace_log_user_ts on public.trace_log (user_id, ts desc);

create table public.session_artifacts (
    id            bigint generated always as identity primary key,
    session_id    text not null,
    user_id       uuid references auth.users(id) on delete cascade,
    ts            timestamptz not null default now(),
    artifact_kind text not null,
    repo          text not null default '',
    venue         text not null default '',
    artifact_name text not null default '',
    size_bytes    integer not null default 0,
    content_hash  text not null default '',
    content       text not null default '',
    metadata      jsonb not null default '{}'::jsonb
);
create index session_artifacts_user_ts on public.session_artifacts (user_id, ts desc);

create table public.user_profile (
    user_id      uuid primary key references auth.users(id) on delete cascade,
    name         text not null default '',
    title        text not null default '',
    about        text not null default '',
    voice_tone   text not null default '',
    github_url   text not null default '',
    linkedin_url text not null default '',
    scholar_url  text not null default '',
    site_url     text not null default '',
    resume_text  text not null default '',
    updated_at   timestamptz not null default now()
);

create table public.outreach_log (
    id              bigint generated always as identity primary key,
    ts              timestamptz not null default now(),
    user_id         uuid references auth.users(id) on delete cascade,
    purpose         text not null,
    channel         text not null,
    content_type_id text not null default '',
    sample_job_id   text not null default '',
    draft_id        text not null default '',
    posted          boolean not null default false
);
create index outreach_log_user_ts on public.outreach_log (user_id, ts desc);

create table public.o1_evidence (
    id            uuid primary key default gen_random_uuid(),
    user_id       uuid not null references auth.users(id) on delete cascade,
    criterion     text not null,
    title         text not null,
    description   text not null default '',
    evidence_url  text not null default '',
    evidence_date date,
    declared_at   timestamptz not null default now(),
    status        text not null default 'draft',
    metadata      jsonb not null default '{}'::jsonb,
    updated_at    timestamptz not null default now()
);
create index o1_evidence_user_criterion on public.o1_evidence (user_id, criterion);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------

alter table public.cfp               enable row level security;
alter table public.arxiv             enable row level security;
alter table public.trace_log         enable row level security;
alter table public.session_artifacts enable row level security;
alter table public.user_profile      enable row level security;
alter table public.outreach_log      enable row level security;
alter table public.o1_evidence       enable row level security;

-- Shared corpora: any authenticated user may read; no write policy (service role only).
create policy cfp_read   on public.cfp   for select to authenticated using (true);
create policy arxiv_read on public.arxiv for select to authenticated using (true);

-- trace_log: a user may read only their own trace events. Writes go through the
-- service role (the backend), so no insert policy is defined for authenticated.
create policy trace_log_select_own on public.trace_log
    for select to authenticated using ((select auth.uid()) = user_id);

-- session_artifacts: read own (Next.js "past sessions" panel reads directly).
create policy session_artifacts_select_own on public.session_artifacts
    for select to authenticated using ((select auth.uid()) = user_id);

-- user_profile: full self-service CRUD on the caller's own row.
create policy user_profile_select_own on public.user_profile
    for select to authenticated using ((select auth.uid()) = user_id);
create policy user_profile_insert_own on public.user_profile
    for insert to authenticated with check ((select auth.uid()) = user_id);
create policy user_profile_update_own on public.user_profile
    for update to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

-- outreach_log: read own.
create policy outreach_log_select_own on public.outreach_log
    for select to authenticated using ((select auth.uid()) = user_id);

-- o1_evidence: full self-service CRUD on the caller's own evidence items.
create policy o1_evidence_select_own on public.o1_evidence
    for select to authenticated using ((select auth.uid()) = user_id);
create policy o1_evidence_insert_own on public.o1_evidence
    for insert to authenticated with check ((select auth.uid()) = user_id);
create policy o1_evidence_update_own on public.o1_evidence
    for update to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);
create policy o1_evidence_delete_own on public.o1_evidence
    for delete to authenticated using ((select auth.uid()) = user_id);

-- ---------------------------------------------------------------------------
-- Grants: the Data API exposes tables to anon/authenticated only after grants.
-- RLS still restricts which rows are visible. Corpora are select-only.
-- ---------------------------------------------------------------------------

grant select on public.cfp, public.arxiv to authenticated;
grant select on public.trace_log, public.session_artifacts, public.outreach_log to authenticated;
grant select, insert, update on public.user_profile to authenticated;
grant select, insert, update, delete on public.o1_evidence to authenticated;
