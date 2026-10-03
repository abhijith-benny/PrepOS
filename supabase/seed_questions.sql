-- MANUAL REVIEW REQUIRED before production use: verify every prompt, option, and answer.
-- This deterministic seed creates 6 reviewed-answer placeholders per seeded topic (150 total).
insert into public.questions (id, topic_id, difficulty, type, body, options, answer, explanation)
select
    gen_random_uuid(),
    topics.id,
    ((series.n + length(topics.name)) % 5) + 1,
    'mcq',
    case topics.category
        when 'DSA' then format('Which statement about %s is correct? Variant %s.', topics.name, series.n)
        when 'aptitude' then format('Which method is appropriate for %s? Variant %s.', topics.name, series.n)
        when 'CS core' then format('Which statement best describes %s? Variant %s.', topics.name, series.n)
        when 'system design' then format('Which design choice best supports %s? Variant %s.', topics.name, series.n)
        else format('Which response best demonstrates %s? Variant %s.', topics.name, series.n)
    end,
    jsonb_build_array('The first option', 'The second option', 'The third option', 'The fourth option'),
    'The first option',
    'Manual review required: replace this generated prompt with a domain-verified explanation.'
from public.topics as topics
cross join generate_series(1, 6) as series(n);
