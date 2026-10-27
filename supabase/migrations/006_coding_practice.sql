alter table public.profiles add column if not exists leetcode_username text;

create table if not exists public.coding_problems (
    id uuid primary key default gen_random_uuid(),
    leetcode_slug text not null unique,
    title text not null,
    difficulty text not null,
    topic_id uuid not null references public.topics(id) on delete cascade,
    added_by_admin boolean not null default true
);

create table if not exists public.coding_assignments (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    problem_id uuid not null references public.coding_problems(id) on delete cascade,
    assigned_at timestamptz not null default now(),
    status text not null check (status in ('pending', 'verified', 'failed_to_verify')),
    verified_at timestamptz
);

alter table public.coding_problems enable row level security;
alter table public.coding_assignments enable row level security;
create policy "Read coding problems" on public.coding_problems for select using (true);
create policy "Users view own coding assignments" on public.coding_assignments for select using (auth.uid() = user_id);
create policy "Users create own coding assignments" on public.coding_assignments for insert with check (auth.uid() = user_id);
create policy "Users update own coding assignments" on public.coding_assignments for update using (auth.uid() = user_id);
