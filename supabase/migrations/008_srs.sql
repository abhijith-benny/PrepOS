create table if not exists public.cards (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    question_id uuid not null references public.questions(id) on delete cascade,
    topic_id uuid not null references public.topics(id) on delete cascade,
    origin text not null check (origin in ('diagnostic', 'mistake', 'manual')),
    state text not null check (state in ('learning', 'review', 'relearning')) default 'learning',
    ease double precision not null default 2.5,
    interval_days integer not null default 0,
    repetitions integer not null default 0,
    lapses integer not null default 0,
    due_at timestamptz not null default now(),
    last_review_at timestamptz,
    fsrs_state jsonb,
    created_at timestamptz not null default now(),
    unique(user_id, question_id)
);

create index if not exists idx_cards_user_due on public.cards(user_id, due_at);

create table if not exists public.reviews (
    id uuid primary key default gen_random_uuid(),
    card_id uuid not null references public.cards(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    rating integer not null check (rating between 0 and 5),
    correct boolean not null,
    time_taken_s integer not null,
    scheduled_days double precision not null,
    elapsed_days double precision not null,
    reviewed_at timestamptz not null default now()
);

create index if not exists idx_reviews_user_date on public.reviews(user_id, reviewed_at);

alter table public.cards enable row level security;
alter table public.reviews enable row level security;

create policy "Users can view own cards" on public.cards
    for select using (auth.uid() = user_id);
create policy "Users can insert own cards" on public.cards
    for insert with check (auth.uid() = user_id);
create policy "Users can update own cards" on public.cards
    for update using (auth.uid() = user_id);
create policy "Users can delete own cards" on public.cards
    for delete using (auth.uid() = user_id);

create policy "Users can view own reviews" on public.reviews
    for select using (auth.uid() = user_id);
create policy "Users can insert own reviews" on public.reviews
    for insert with check (auth.uid() = user_id);
