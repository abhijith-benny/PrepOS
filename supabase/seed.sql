insert into public.topics (id, name, category, parent_id) values
  (gen_random_uuid(), 'Arrays & Strings', 'DSA', null),
  (gen_random_uuid(), 'Hashing', 'DSA', null),
  (gen_random_uuid(), 'Trees', 'DSA', null),
  (gen_random_uuid(), 'Graphs', 'DSA', null),
  (gen_random_uuid(), 'Dynamic Programming', 'DSA', null),
  (gen_random_uuid(), 'Number System', 'aptitude', null),
  (gen_random_uuid(), 'Percentages', 'aptitude', null),
  (gen_random_uuid(), 'Profit & Loss', 'aptitude', null),
  (gen_random_uuid(), 'Time & Work', 'aptitude', null),
  (gen_random_uuid(), 'Averages', 'aptitude', null),
  (gen_random_uuid(), 'Operating Systems', 'CS core', null),
  (gen_random_uuid(), 'DBMS', 'CS core', null),
  (gen_random_uuid(), 'Computer Networks', 'CS core', null),
  (gen_random_uuid(), 'OOP', 'CS core', null),
  (gen_random_uuid(), 'Compiler Design', 'CS core', null),
  (gen_random_uuid(), 'Scalability', 'system design', null),
  (gen_random_uuid(), 'API Design', 'system design', null),
  (gen_random_uuid(), 'Caching', 'system design', null),
  (gen_random_uuid(), 'Messaging', 'system design', null),
  (gen_random_uuid(), 'Reliability', 'system design', null),
  (gen_random_uuid(), 'Self Introduction', 'HR/behavioral', null),
  (gen_random_uuid(), 'Conflict Resolution', 'HR/behavioral', null),
  (gen_random_uuid(), 'Leadership', 'HR/behavioral', null),
  (gen_random_uuid(), 'Teamwork', 'HR/behavioral', null),
  (gen_random_uuid(), 'Career Goals', 'HR/behavioral', null);

-- Placeholder question entries: enough to satisfy the sample data requirement.
insert into public.questions (id, topic_id, difficulty, type, body, options, answer, explanation)
select gen_random_uuid(), t.id, 2, 'mcq', 'Example question: Which is a valid data structure for O(1) lookups?', jsonb_build_array('HashMap','Array','Queue','Stack'), 'HashMap', 'HashMap provides average O(1) lookup.'
from public.topics t where t.name = 'Hashing';

insert into public.questions (id, topic_id, difficulty, type, body, options, answer, explanation)
select gen_random_uuid(), t.id, 3, 'mcq', 'Example question: What is the time complexity of BFS on a graph?', jsonb_build_array('O(V)', 'O(E)', 'O(V + E)', 'O(V * E)'), 'O(V + E)', 'BFS traverses each vertex and edge once.'
from public.topics t where t.name = 'Graphs';

insert into public.questions (id, topic_id, difficulty, type, body, options, answer, explanation)
select gen_random_uuid(), t.id, 2, 'mcq', 'Example question: What does a cache primarily optimize?', jsonb_build_array('Storage size', 'Latency', 'Security', 'Pricing'), 'Latency', 'A cache reduces repeated access latency for hot data.'
from public.topics t where t.name = 'Caching';

insert into public.questions (id, topic_id, difficulty, type, body, options, answer, explanation)
select gen_random_uuid(), t.id, 2, 'mcq', 'Example question: Which response is best for a self introduction?', jsonb_build_array('I am good', 'I am a software engineer focused on DSA and product thinking.', 'Not sure', 'No answer'), 'I am a software engineer focused on DSA and product thinking.', 'A strong self-introduction ties the candidate to skills and goals.'
from public.topics t where t.name = 'Self Introduction';
