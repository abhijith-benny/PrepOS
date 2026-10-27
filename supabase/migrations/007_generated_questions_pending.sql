create table if not exists public.generated_questions_pending (
    id uuid primary key default gen_random_uuid(),
    category text not null,
    difficulty text not null,
    body text not null,
    options jsonb not null,
    answer_index integer not null,
    explanation text not null,
    model_check_passed boolean not null default false,
    created_at timestamptz not null default now(),
    reviewed boolean not null default false
);

alter table public.generated_questions_pending enable row level security;
create policy "Allow read on generated_questions_pending" on public.generated_questions_pending for select using (true);
create policy "Allow insert on generated_questions_pending" on public.generated_questions_pending for insert with check (true);
create policy "Allow update on generated_questions_pending" on public.generated_questions_pending for update using (true);
create policy "Allow delete on generated_questions_pending" on public.generated_questions_pending for delete using (true);
