create table if not exists public.diagnostic_sessions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    status text not null check (status in ('in_progress', 'completed', 'abandoned')),
    started_at timestamptz not null default now(),
    completed_at timestamptz,
    config jsonb not null default '{}'::jsonb,
    result jsonb
);

alter table public.attempts add column if not exists session_id uuid references public.diagnostic_sessions(id) on delete set null;

create table if not exists public.cluster_assignments (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    session_id uuid not null references public.diagnostic_sessions(id) on delete cascade,
    cluster_id integer not null,
    cluster_label text not null,
    model_version text not null,
    distances jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);

alter table public.diagnostic_sessions enable row level security;
alter table public.cluster_assignments enable row level security;

create policy "Users can view own diagnostic sessions" on public.diagnostic_sessions
    for select using (auth.uid() = user_id);
create policy "Users can create own diagnostic sessions" on public.diagnostic_sessions
    for insert with check (auth.uid() = user_id);
create policy "Users can update own diagnostic sessions" on public.diagnostic_sessions
    for update using (auth.uid() = user_id);

create policy "Users can view own cluster assignments" on public.cluster_assignments
    for select using (auth.uid() = user_id);
create policy "Users can create own cluster assignments" on public.cluster_assignments
    for insert with check (auth.uid() = user_id);
