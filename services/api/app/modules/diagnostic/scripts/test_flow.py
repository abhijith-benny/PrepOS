import os
import sys
from uuid import uuid4
from supabase import create_client
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv('services/api/.env')
sys.path.insert(0, os.path.abspath('services/api'))

from app.modules.diagnostic.router import STORE, start_session, next_question, answer_question, complete_session, session_report
from app.modules.diagnostic.router import AnswerCreate

user_id = "65915f5c-bf6d-4103-ad2b-d2f2053809a4"
mock_user = {"id": user_id, "email": "josephbennycoc883@gmail.com"}

print(f"--- Step 1: Starting Session 1 for user {user_id[:8]} ---")
s1 = start_session(current_user=mock_user)
s1_id = s1["id"]
print(f"Session 1 ID: {s1_id}")

s1_q_ids = []
s1_coding_problem = None

# Answer 10 questions in section 1 (aptitude)
for i in range(10):
    nq = next_question(s1_id, current_user=mock_user)
    if nq.get("done") or nq.get("section_complete"):
        break
    q = nq["question"]
    s1_q_ids.append(q["id"])
    print(f"  Q{i+1} [{q['id'][:8]}]: {q.get('body', '')[:60]}...")
    opts = q.get("options") or ["A"]
    ans = answer_question(s1_id, AnswerCreate(question_id=q["id"], answer=opts[0], time_taken_s=15), current_user=mock_user)

print(f"\n--- Checking Supabase 'attempts' table for session 1 ---")
from app.shared.repositories.retry import retry_supabase
sb = STORE.supabase
if sb:
    att_rows = retry_supabase(lambda: sb.table("attempts").select("*").eq("user_id", user_id).execute()).data or []
    print(f"Attempts recorded in Supabase: {len(att_rows)}")
    for a in att_rows[:3]:
        print(f"  Attempt: QID {a['question_id'][:8]} | Correct: {a['correct']}")

print(f"\n--- Step 2: Coding section for Session 1 ---")
# Jump to coding
s1_obj = STORE.get(s1_id, user_id)
s1_obj["sections"]["aptitude"]["status"] = "completed"
s1_obj["sections"]["computer_aptitude"]["status"] = "completed"
s1_obj["sections"]["english"]["status"] = "completed"
s1_obj["sections"]["coding"]["status"] = "in_progress"
STORE.save(s1_obj)

coding_nq = next_question(s1_id, current_user=mock_user)
coding_q = coding_nq["question"]
s1_coding_slug = coding_q.get("leetcode_slug")
print(f"Session 1 Coding Problem: {coding_q.get('title')} ({s1_coding_slug})")

ans_coding = answer_question(s1_id, AnswerCreate(question_id=coding_q["id"], answer="verified", time_taken_s=120), current_user=mock_user)
print("Coding answer response:", ans_coding["correct"])

# Complete Session 1
res = complete_session(s1_id, current_user=mock_user)
topic_names = res.get("topic_names") or {}
print(f"Topic names mapped in report: {len(topic_names)} topics")
print(f"Sample mapped topic: {list(topic_names.items())[0] if topic_names else None}")

# Check that weak_topics in session_report are human names, not raw UUIDs!
rep = session_report(s1_id, current_user=mock_user)
weak = rep.get("weak_topics", [])
print(f"Weak topics sample: {weak[:3]}")

print(f"\n--- Step 3: Starting Session 2 for the same user ---")
s2 = start_session(current_user=mock_user)
s2_id = s2["id"]
print(f"Session 2 ID: {s2_id}")

s2_q_ids = []
for i in range(10):
    nq = next_question(s2_id, current_user=mock_user)
    if nq.get("done") or nq.get("section_complete"):
        break
    q = nq["question"]
    s2_q_ids.append(q["id"])
    print(f"  Session 2 Q{i+1} [{q['id'][:8]}]: {q.get('body', '')[:60]}...")
    opts = q.get("options") or ["A"]
    ans = answer_question(s2_id, AnswerCreate(question_id=q["id"], answer=opts[0], time_taken_s=12), current_user=mock_user)

# Check question overlap between Session 1 and Session 2
overlap = set(s1_q_ids).intersection(set(s2_q_ids))
print(f"\n=== Question Overlap Check ===")
print(f"Session 1 questions: {len(s1_q_ids)}")
print(f"Session 2 questions: {len(s2_q_ids)}")
print(f"Overlapping questions: {len(overlap)} (Must be 0!)")
assert len(overlap) == 0, f"ERROR: Questions overlapped: {overlap}"
print("✓ ZERO question overlap verified!")

# Check Coding problem for Session 2
s2_obj = STORE.get(s2_id, user_id)
s2_obj["sections"]["aptitude"]["status"] = "completed"
s2_obj["sections"]["computer_aptitude"]["status"] = "completed"
s2_obj["sections"]["english"]["status"] = "completed"
s2_obj["sections"]["coding"]["status"] = "in_progress"
STORE.save(s2_obj)

coding_nq2 = next_question(s2_id, current_user=mock_user)
coding_q2 = coding_nq2["question"]
s2_coding_slug = coding_q2.get("leetcode_slug")
print(f"Session 2 Coding Problem: {coding_q2.get('title')} ({s2_coding_slug})")
assert s1_coding_slug != s2_coding_slug, f"ERROR: Same coding problem served: {s1_coding_slug}"
print("✓ ZERO coding problem overlap verified!")
print("\nALL VERIFICATIONS PASSED!")
