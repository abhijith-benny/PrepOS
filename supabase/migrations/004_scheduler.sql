create table if not exists public.study_plans (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    week_start_date date not null,
    status text not null check (status in ('active', 'archived')),
    generated_at timestamptz not null default now(),
    horizon_weeks integer not null default 1,
    config jsonb not null default '{}'::jsonb
);

create table if not exists public.plan_sessions (
    id uuid primary key default gen_random_uuid(),
    plan_id uuid not null references public.study_plans(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    topic_id uuid not null references public.topics(id) on delete cascade,
    day_of_week smallint not null check (day_of_week between 0 and 6),
    start_time time not null,
    duration_minutes integer not null check (duration_minutes > 0),
    status text not null check (status in ('scheduled', 'completed', 'skipped')),
    completed_at timestamptz
);

alter table public.profiles add column if not exists preferred_days jsonb;
alter table public.profiles add column if not exists preferred_times jsonb;

alter table public.study_plans enable row level security;
alter table public.plan_sessions enable row level security;

create policy "Users can view own study plans" on public.study_plans
    for select using (auth.uid() = user_id);
create policy "Users can create own study plans" on public.study_plans
    for insert with check (auth.uid() = user_id);
create policy "Users can update own study plans" on public.study_plans
    for update using (auth.uid() = user_id);

create policy "Users can view own plan sessions" on public.plan_sessions
    for select using (auth.uid() = user_id);
create policy "Users can create own plan sessions" on public.plan_sessions
    for insert with check (auth.uid() = user_id);
create policy "Users can update own plan sessions" on public.plan_sessions
    for update using (auth.uid() = user_id);
