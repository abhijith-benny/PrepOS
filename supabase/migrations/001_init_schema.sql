create extension if not exists "pgcrypto";

create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    full_name text,
    target_role text,
    target_date date,
    weekly_hours integer default 0,
    created_at timestamptz not null default now()
);

create table if not exists public.topics (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    category text not null,
    parent_id uuid references public.topics(id)
);

create table if not exists public.questions (
    id uuid primary key default gen_random_uuid(),
    topic_id uuid not null references public.topics(id) on delete cascade,
    difficulty smallint not null check (difficulty between 1 and 5),
    type text not null,
    body text not null,
    options jsonb,
    answer text,
    explanation text
);

create table if not exists public.attempts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    question_id uuid not null references public.questions(id) on delete cascade,
    correct boolean not null,
    time_taken_s integer,
    created_at timestamptz not null default now()
);

create table if not exists public.skill_states (
    user_id uuid not null,
    topic_id uuid not null references public.topics(id) on delete cascade,
    mastery double precision not null default 0 check (mastery between 0 and 1),
    confidence double precision not null default 0 check (confidence between 0 and 1),
    updated_at timestamptz not null default now(),
    primary key (user_id, topic_id)
);

create table if not exists public.events (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    type text not null,
    payload jsonb default '{}'::jsonb,
    created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;
alter table public.topics enable row level security;
alter table public.questions enable row level security;
alter table public.attempts enable row level security;
alter table public.skill_states enable row level security;
alter table public.events enable row level security;

create policy "Users can view own profile" on public.profiles
    for select using (auth.uid() = id);
create policy "Users can update own profile" on public.profiles
    for update using (auth.uid() = id);
create policy "Users can insert own profile" on public.profiles
    for insert with check (auth.uid() = id);

create policy "Users can view own attempts" on public.attempts
    for select using (auth.uid() = user_id);
create policy "Users can insert own attempts" on public.attempts
    for insert with check (auth.uid() = user_id);

create policy "Users can view own skill states" on public.skill_states
    for select using (auth.uid() = user_id);
create policy "Users can upsert own skill states" on public.skill_states
    for insert with check (auth.uid() = user_id);
create policy "Users can update own skill states" on public.skill_states
    for update using (auth.uid() = user_id);

create policy "Users can view own events" on public.events
    for select using (auth.uid() = user_id);
create policy "Users can insert own events" on public.events
    for insert with check (auth.uid() = user_id);

create policy "Read topics is public" on public.topics
    for select using (true);
create policy "Read questions is public" on public.questions
    for select using (true);
