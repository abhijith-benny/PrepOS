create table if not exists public.interview_sessions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    round_type text not null check (round_type in ('technical', 'hr')),
    target_role text not null default 'Software Engineer',
    status text not null check (status in ('in_progress', 'completed', 'abandoned')) default 'in_progress',
    total_questions integer not null default 5,
    current_question_index integer not null default 0,
    overall_score double precision check (overall_score is null or (overall_score >= 0 and overall_score <= 100)),
    summary_feedback text,
    strengths jsonb not null default '[]'::jsonb,
    improvements jsonb not null default '[]'::jsonb,
    started_at timestamptz not null default now(),
    completed_at timestamptz
);

create table if not exists public.interview_turns (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references public.interview_sessions(id) on delete cascade,
    turn_number integer not null,
    topic text,
    question text not null,
    answer_transcript text,
    audio_url text,
    accuracy_score double precision default 0 check (accuracy_score between 0 and 10),
    structure_score double precision default 0 check (structure_score between 0 and 10),
    communication_score double precision default 0 check (communication_score between 0 and 10),
    overall_turn_score double precision default 0 check (overall_turn_score between 0 and 100),
    feedback text,
    model_answer text,
    time_taken_s double precision default 0,
    created_at timestamptz not null default now()
);

alter table public.interview_sessions enable row level security;
alter table public.interview_turns enable row level security;

create policy "Users can view own interview sessions" on public.interview_sessions
    for select using (auth.uid() = user_id);

create policy "Users can insert own interview sessions" on public.interview_sessions
    for insert with check (auth.uid() = user_id);

create policy "Users can update own interview sessions" on public.interview_sessions
    for update using (auth.uid() = user_id);

create policy "Users can view own interview turns" on public.interview_turns
    for select using (
        exists (
            select 1 from public.interview_sessions s
            where s.id = interview_turns.session_id and s.user_id = auth.uid()
        )
    );

create policy "Users can insert own interview turns" on public.interview_turns
    for insert with check (
        exists (
            select 1 from public.interview_sessions s
            where s.id = interview_turns.session_id and s.user_id = auth.uid()
        )
    );
