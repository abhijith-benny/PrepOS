"""Purge example questions and old toy English questions, and generate real,
rigorous English and Aptitude placement questions via Groq API into Supabase.
"""
from __future__ import annotations

import sys
import time
from uuid import uuid4

from app.core.config import settings
from app.modules.diagnostic.question_generation import GroqClient
from supabase import create_client


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print("Connecting to Supabase...")
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    groq = GroqClient()

    # 1. Purge all questions with "Example question:"
    print("1. Purging questions containing 'Example question:'...")
    ex_qs = supabase.table("questions").select("id,body").ilike("body", "%example question%").execute().data or []
    for q in ex_qs:
        print(f"  Deleting example question: {q['id']} - {q['body']}")
        supabase.table("questions").delete().eq("id", q["id"]).execute()

    # 2. Purge old toy English questions (short toy passages, 'The results was useful', 'Yo, see the thing', etc.)
    print("\n2. Purging old toy English questions...")
    eng_topics = supabase.table("topics").select("id,name,category").eq("category", "English").execute().data or []
    eng_topic_ids = [t["id"] for t in eng_topics]
    all_eng_qs = supabase.table("questions").select("id,body,options,topic_id").in_("topic_id", eng_topic_ids).execute().data or []
    
    toy_ids = []
    for q in all_eng_qs:
        b = q.get("body", "").lower()
        opts_str = str(q.get("options", [])).lower()
        if "passage:" in b or "useful." in b or "problems." in b or "lol" in opts_str or "yo," in opts_str:
            toy_ids.append(q["id"])
            print(f"  Flagged toy question for deletion: {q['id']} - {q.get('body')[:60]}")
    
    if toy_ids:
        for i in range(0, len(toy_ids), 10):
            chunk = toy_ids[i:i+10]
            supabase.table("questions").delete().in_("id", chunk).execute()
        print(f"Deleted {len(toy_ids)} toy English questions.")

    # 3. Generate high-quality English questions with Groq
    print("\n3. Generating high-quality, comprehensive English placement questions with Groq...")
    english_prompts = {
        "Grammar": {
            "prompt": "English Grammar - Subject-verb agreement, advanced tenses, prepositions, or conditional clauses for corporate/campus placement tests. Every question body must contain a full, self-contained sentence with a blank (e.g. '___') to fill, or ask to identify the grammatically correct sentence among 4 options.",
            "count": 5,
        },
        "Vocabulary": {
            "prompt": "English Vocabulary - Advanced synonyms, antonyms, or contextual definitions (e.g., words like PRAGMATIC, EPHEMERAL, METICULOUS, PERSPICACIOUS). Format questions clearly as 'Choose the word closest in meaning to...' or 'Choose the word opposite in meaning to...'.",
            "count": 5,
        },
        "Sentence Correction": {
            "prompt": "English Sentence Correction - A full, complete sentence must be provided in the question body with a bracketed phrase [like this], asking which of the 4 options provides the grammatically correct and concise replacement.",
            "count": 5,
        },
        "Reading Comprehension": {
            "prompt": "English Reading Comprehension - Each question body MUST include a complete, coherent 3-4 sentence paragraph followed by an inference or factual question based strictly on the text. Format: 'Read the passage below and answer the question:\n\"[3-4 sentence passage]\"\n\nQuestion: [Question]?'",
            "count": 5,
        },
        "Usage and Style": {
            "prompt": "English Usage and Style - Business communication, professional idioms (e.g., 'to burn the midnight oil', 'a blessing in disguise', 'bite the bullet'), active vs passive voice transformations, or clarity in professional writing. The full sentence must be provided in the question body.",
            "count": 5,
        },
    }

    for topic in eng_topics:
        t_id = topic["id"]
        t_name = topic["name"]
        spec = english_prompts.get(t_name)
        if not spec:
            continue

        print(f"\nGenerating {spec['count']} questions for '{t_name}'...")
        try:
            batch = groq.generate_raw_batch(category=spec["prompt"], difficulty="Medium", count=spec["count"])
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
                print(f"  [+] Inserted: {q_data['body'][:70]}... -> {correct_answer}")
            time.sleep(2.0)
        except Exception as e:
            print(f"  [!] Failed for {t_name}: {e}")
            time.sleep(3.0)

    print("\nCompleted English overhaul!")


if __name__ == "__main__":
    main()
