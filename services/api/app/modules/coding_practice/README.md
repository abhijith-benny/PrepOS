# Coding Practice Integration

This module uses option (a): a minimal self-hosted client that posts the two required GraphQL query shapes directly to `https://leetcode.com/graphql`. It does not call a hosted wrapper or require OAuth.

- `recentAcSubmissionList(username)` reads title, titleSlug, and timestamp.
- `question(titleSlug)` reads title, titleSlug, and difficulty.
- Accepted-submission results are cached per username for three minutes.
- Network/timeout failures retry once with backoff.
- A null submission list raises `PrivateProfileError`; an empty list raises `EmptySubmissionError`.

The problem seed is [seed_coding_problems.sql](../../../../supabase/seed_coding_problems.sql) and is flagged for manual review. A real public query was verified locally against `lee215`; a non-empty response parsed 20 submissions. A personal LeetCode solve-and-verify flow was not run because no user-owned LeetCode account/session was available in the environment.
