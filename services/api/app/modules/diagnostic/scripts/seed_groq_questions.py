"""Script to purge placeholder dummy questions and generate real placement questions
using the Groq API key for all diagnostic topics.
"""
from __future__ import annotations

import sys
import time
from uuid import uuid4

from app.core.config import settings
from app.modules.diagnostic.question_generation import GroqClient
from supabase import create_client

DIAGNOSTIC_CATEGORIES = ["aptitude", "CS core", "English", "DSA"]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print("Connecting to Supabase...")
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    groq = GroqClient()

    # 1. Fetch topics
    topics_res = supabase.table("topics").select("id,name,category").execute()
    topics = topics_res.data or []
    diag_topics = [t for t in topics if t.get("category") in DIAGNOSTIC_CATEGORIES]
    print(f"Found {len(diag_topics)} diagnostic topics across categories: {DIAGNOSTIC_CATEGORIES}")

    # 2. Check existing real questions per topic
    remaining_qs = supabase.table("questions").select("id,topic_id,body").execute().data or []
    topic_q_count = {}
    for q in remaining_qs:
        tid = q.get("topic_id")
        topic_q_count[tid] = topic_q_count.get(tid, 0) + 1

    # 3. Generate real questions with Groq in single batch per topic
    total_generated = 0
    for topic in diag_topics:
        t_id = topic["id"]
        t_name = topic["name"]
        t_cat = topic["category"]
        curr_count = topic_q_count.get(t_id, 0)

        # Target at least 4 real questions per topic
        needed = max(0, 4 - curr_count)
        if needed <= 0:
            print(f"Topic '{t_name}' ({t_cat}) has {curr_count} real questions. Skipping.")
            continue

        print(f"Generating {needed} real questions for '{t_name}' ({t_cat}) in 1 batch using Groq...")
        try:
            batch = groq.generate_raw_batch(category=f"{t_cat} - {t_name}", difficulty="Medium", count=needed)
            for q_data in batch:
                ans_idx = int(q_data["answer_index"])
                options = q_data["options"]
                correct_answer = options[ans_idx] if 0 <= ans_idx < len(options) else options[0]

                new_row = {
                    "id": str(uuid4()),
                    "topic_id": t_id,
                    "difficulty": 2,
                    "type": "mcq",
                    "body": q_data["body"],
                    "options": options,
                    "answer": correct_answer,
                    "explanation": q_data.get("explanation", ""),
                }
                supabase.table("questions").insert(new_row).execute()
                total_generated += 1
                print(f"  [+] Inserted: {q_data['body'][:65]}... -> Ans: {correct_answer}")
            time.sleep(2.0)  # Safe delay between topics
        except Exception as e:
            print(f"  [!] Failed for {t_name}: {e}")
            time.sleep(3.0)

    print(f"\nCompleted! Total new real questions generated: {total_generated}")


if __name__ == "__main__":
    main()
