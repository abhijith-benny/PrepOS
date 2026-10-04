alter table public.profiles add column if not exists department text;
alter table public.profiles add column if not exists year_or_semester text;
alter table public.profiles add column if not exists known_languages jsonb;

alter table public.diagnostic_sessions add column if not exists sections jsonb not null default '{}'::jsonb;

insert into public.topics (id, name, category, parent_id)
select gen_random_uuid(), topic.name, 'English', null
from (values
    ('Grammar'),
    ('Vocabulary'),
    ('Reading Comprehension'),
    ('Sentence Correction'),
    ('Usage and Style')
) as topic(name)
where not exists (
    select 1 from public.topics existing
    where existing.name = topic.name and existing.category = 'English'
);

alter table public.diagnostic_sessions enable row level security;
