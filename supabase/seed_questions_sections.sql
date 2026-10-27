-- MANUAL REVIEW REQUIRED before production use.
-- This additive seed supplements seed_questions.sql with the new English section
-- and 15 rewritten coding/code-reading questions.

insert into public.questions (id, topic_id, difficulty, type, body, options, answer, explanation)
select gen_random_uuid(), topics.id, questions.difficulty, 'mcq', questions.body,
       jsonb_build_array(questions.option_a, questions.option_b, questions.option_c, questions.option_d),
       questions.answer, questions.explanation
from (values
  ('Grammar', 1, 'Choose the correct sentence.', 'She has lived here for five years.', 'She have lived here for five years.', 'She living here for five years.', 'She live here since five years.', 'She has lived here for five years.', 'The present perfect describes an action continuing to the present.'),
  ('Grammar', 2, 'Choose the correct sentence.', 'Neither answer is correct.', 'Neither answers are correct.', 'Neither answer are correct.', 'Neither of answer is correct.', 'Neither answer is correct.', 'Neither is singular in formal usage.'),
  ('Grammar', 2, 'Complete: If I ___ earlier, I would have called.', 'had known', 'know', 'have known', 'will know', 'had known', 'This is a third conditional sentence.'),
  ('Grammar', 1, 'Choose the correct article: She is ___ honest engineer.', 'a', 'an', 'the', 'no article', 'an', 'Honest begins with a vowel sound.'),
  ('Grammar', 3, 'Choose the correctly punctuated sentence.', 'After the meeting, we reviewed the notes.', 'After the meeting we, reviewed the notes.', 'After, the meeting we reviewed the notes.', 'After the meeting we reviewed, the notes.', 'After the meeting, we reviewed the notes.', 'A comma follows the introductory phrase.'),
  ('Grammar', 2, 'Choose the correct form: The data ___ consistent.', 'is', 'are', 'be', 'being', 'are', 'Data is treated as a plural noun in this usage.'),
  ('Vocabulary', 1, 'What does concise mean?', 'Brief and clear', 'Loud and forceful', 'Difficult to understand', 'Very old', 'Brief and clear', 'Concise writing uses few words without losing meaning.'),
  ('Vocabulary', 2, 'What is an antonym of scarce?', 'Rare', 'Abundant', 'Small', 'Hidden', 'Abundant', 'Scarce means limited or hard to find.'),
  ('Vocabulary', 2, 'What does mitigate mean?', 'To make less severe', 'To measure exactly', 'To repeat loudly', 'To remove entirely', 'To make less severe', 'Mitigate means reduce the impact or severity.'),
  ('Vocabulary', 1, 'What does reliable mean?', 'Consistently dependable', 'Recently purchased', 'Very expensive', 'Hard to access', 'Consistently dependable', 'Reliable things can be trusted to perform consistently.'),
  ('Vocabulary', 3, 'What is the closest meaning of ambiguous?', 'Open to more than one interpretation', 'Extremely fast', 'Completely false', 'Easy to verify', 'Open to more than one interpretation', 'Ambiguous wording permits multiple readings.'),
  ('Vocabulary', 2, 'What does allocate mean?', 'Distribute for a purpose', 'Delay without reason', 'Copy exactly', 'Argue against', 'Distribute for a purpose', 'Allocate means assign resources or time.'),
  ('Reading Comprehension', 2, 'Passage: A team reduced build time by caching unchanged dependencies. What was the direct benefit?', 'Lower build latency', 'More source files', 'Higher memory errors', 'Fewer tests', 'Lower build latency', 'Caching avoided repeated dependency work.'),
  ('Reading Comprehension', 3, 'Passage: Maya compared two approaches on accuracy and cost before choosing one. Which quality did she demonstrate?', 'Trade-off analysis', 'Guessing', 'Avoidance', 'Memorization', 'Trade-off analysis', 'She evaluated competing benefits and costs.'),
  ('Reading Comprehension', 2, 'Passage: The API returns a clear error and a retry hint when a service is temporarily unavailable. What improves?', 'Recoverability', 'Syntax highlighting', 'Disk capacity', 'Compilation speed', 'Recoverability', 'Actionable errors help callers recover.'),
  ('Reading Comprehension', 3, 'Passage: A report says usage rose after onboarding was simplified, but it does not compare against a control group. What is missing?', 'A stronger causal comparison', 'A title', 'A verb', 'A file extension', 'A stronger causal comparison', 'Without a control, causation remains uncertain.'),
  ('Reading Comprehension', 1, 'Passage: The library opens at nine and closes at five. When can a visitor enter?', 'At eight', 'At nine', 'At six', 'At midnight', 'At nine', 'The stated opening time is nine.'),
  ('Reading Comprehension', 2, 'Passage: The release was delayed because testing found a data-loss defect. Why was it delayed?', 'To fix a serious defect', 'To add a logo', 'To reduce documentation', 'To remove testing', 'To fix a serious defect', 'The defect posed a release risk.'),
  ('Sentence Correction', 2, 'Choose the best revision: The results was useful.', 'The results were useful.', 'The results is useful.', 'The result were useful.', 'The results be useful.', 'The results were useful.', 'Results is plural and takes were.'),
  ('Sentence Correction', 2, 'Choose the best revision: She is good in solving problems.', 'She is good at solving problems.', 'She is good on solving problems.', 'She good at solve problems.', 'She is good to solving problems.', 'She is good at solving problems.', 'Good at is the standard collocation.'),
  ('Sentence Correction', 3, 'Choose the clearest sentence.', 'Because the test failed, we paused deployment.', 'The deployment paused because it failed the test we.', 'Failed test deployment paused because.', 'We because paused deployment test failed.', 'Because the test failed, we paused deployment.', 'The first sentence has a clear cause and action.'),
  ('Usage and Style', 1, 'Which phrase is most appropriate in a professional email?', 'Please find the report attached.', 'Yo, see the thing.', 'Send report now!!!', 'Report attached lol.', 'Please find the report attached.', 'It is concise and professional.'),
  ('Usage and Style', 2, 'Which word best signals contrast?', 'However', 'Therefore', 'Similarly', 'Because', 'However', 'However introduces a contrast.'),
  ('Usage and Style', 1, 'Which sentence uses active voice?', 'The engineer fixed the bug.', 'The bug was fixed by the engineer.', 'The bug had been fixed.', 'The fix was completed.', 'The engineer fixed the bug.', 'The subject performs the action.'),
  ('Usage and Style', 2, 'Which opening is clearest for a recommendation?', 'I recommend option B because it reduces latency.', 'Option B maybe sort of.', 'There are things to say.', 'You know the option.', 'I recommend option B because it reduces latency.', 'It states the recommendation and rationale directly.')
) as questions(topic_name, difficulty, body, option_a, option_b, option_c, option_d, answer, explanation)
join public.topics on public.topics.name = questions.topic_name and public.topics.category = 'English';

-- CODING REVIEW REQUIRED: these 15 questions were rewritten as code-reading items.
insert into public.questions (id, topic_id, difficulty, type, body, options, answer, explanation)
select gen_random_uuid(), topics.id, questions.difficulty, 'mcq', questions.body,
       jsonb_build_array(questions.option_a, questions.option_b, questions.option_c, questions.option_d),
       questions.answer, questions.explanation
from (values
  ('Arrays & Strings', 1, 'What does this print? a = [1, 2, 3]; print(a[-1])', '1', '2', '3', 'Error', '3', 'Negative index -1 selects the last item.'),
  ('Arrays & Strings', 2, 'What is the complexity? for x in items: print(x)', 'O(1)', 'O(log n)', 'O(n)', 'O(n^2)', 'O(n)', 'The loop visits each item once.'),
  ('Hashing', 2, 'What does this print? counts = {}; counts["a"] = 1; print(counts.get("b", 0))', '1', '0', 'None', 'Error', '0', 'get returns the supplied default for a missing key.'),
  ('Hashing', 3, 'What is wrong with this lookup? for key in keys: if key == target: return value', 'It may return the wrong value because value is not indexed by key.', 'It sorts the keys.', 'It always runs in O(1).', 'It creates a graph.', 'It may return the wrong value because value is not indexed by key.', 'The code does not retrieve a value associated with the matching key.'),
  ('Trees', 2, 'A balanced binary search tree has n nodes. What is search complexity?', 'O(1)', 'O(log n)', 'O(n)', 'O(n log n)', 'O(log n)', 'Each comparison removes roughly half the remaining tree.'),
  ('Trees', 3, 'What does preorder traversal visit first?', 'The root', 'The smallest leaf', 'The rightmost leaf', 'The parent after children', 'The root', 'Preorder is root, left, right.'),
  ('Graphs', 2, 'What does BFS use to manage the frontier?', 'A queue', 'A stack only', 'A sorted array', 'A hash set only', 'A queue', 'BFS processes vertices level by level with a queue.'),
  ('Graphs', 3, 'What is the complexity of BFS with adjacency lists?', 'O(V + E)', 'O(V^2E)', 'O(log V)', 'O(1)', 'O(V + E)', 'Each vertex and edge is visited at most once.'),
  ('Dynamic Programming', 2, 'What does memo = {} change in a recursive Fibonacci function?', 'It avoids repeated subproblems.', 'It makes every call random.', 'It removes the base case.', 'It sorts results.', 'It avoids repeated subproblems.', 'Memoization stores solved subproblems.'),
  ('Dynamic Programming', 3, 'If dp[i] = dp[i - 1] + 1, what does dp usually represent?', 'A value built from a previous state', 'A database connection', 'A random sample', 'A syntax tree only', 'A value built from a previous state', 'The recurrence derives the current state from an earlier one.'),
  ('Arrays & Strings', 2, 'What does this print? s = "prep"; print(s[0:2])', 'pr', 'pre', 'ep', 'prep', 'pr', 'The slice stops before index 2.'),
  ('Hashing', 2, 'What bug occurs if a counter is read before initialization?', 'A missing-key error', 'A guaranteed sort', 'A memory compression', 'A graph cycle', 'A missing-key error', 'The counter must be initialized before incrementing.'),
  ('Graphs', 2, 'A DFS function calls itself on each unvisited neighbor. What risk must be considered?', 'Recursion depth', 'Floating-point rounding', 'CSS specificity', 'File encoding only', 'Recursion depth', 'A deep graph can exceed the call stack.'),
  ('Trees', 2, 'What does an inorder traversal of a binary search tree produce?', 'Sorted order', 'Reverse insertion order always', 'Random order', 'Only the root', 'Sorted order', 'Inorder traversal yields ascending keys in a BST.'),
  ('Dynamic Programming', 1, 'What must a recursive DP solution include to stop?', 'A base case', 'A second language', 'A network call', 'A random seed', 'A base case', 'The base case terminates recursion.')
) as questions(topic_name, difficulty, body, option_a, option_b, option_c, option_d, answer, explanation)
join public.topics on public.topics.name = questions.topic_name and public.topics.category = 'DSA';
