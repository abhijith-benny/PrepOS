import os
import sys
from supabase import create_client
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv('services/api/.env')

sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_ROLE_KEY'))
rows = sb.table('questions').select('id,body,options,answer,topic_id,topics(name,category)').execute().data or []

print(f"Total questions in DB: {len(rows)}")

issues = []
for r in rows:
    t = r.get('topics') or {}
    cat = t.get('category', '')
    body = r.get('body', '')
    opts = r.get('options') or []
    ans = r.get('answer', '')
    topic_name = t.get('name', '')
    
    reasons = []
    
    # 1. Very short body that is uninformative
    if len(body.strip()) < 35:
        reasons.append(f"Very short body ({len(body)} chars)")
        
    # 2. Passage reference without a proper passage
    if 'passage' in body.lower() and len(body) < 180:
        reasons.append("Passage mention but passage is too short or missing")
        
    # 3. Bracketed phrase without instructions
    if '[' in body and ']' in body and not any(w in body.lower() for w in ['replace', 'correct', 'substitute', 'bracket', 'underlined', 'improve', 'phrase']):
        reasons.append("Contains brackets [...] without instructions on what to do")
        
    # 4. "Sentence" mentioned but no sentence is given
    if any(phrase in body.lower() for phrase in ['in the following sentence', 'in this sentence', 'the following sentence has']) and not any(mark in body for mark in ['"', "'", ":", "["]):
        reasons.append("Refers to a sentence without quoting or embedding the sentence")
        
    # 5. Options empty or missing correct answer
    if len(opts) < 4:
        reasons.append(f"Fewer than 4 options ({len(opts)})")
    if ans not in opts and ans not in ['A', 'B', 'C', 'D']:
        reasons.append(f"Answer '{ans}' not in options")
        
    # 6. Any placeholder or example text
    if 'example' in body.lower() or 'variant' in body.lower():
        reasons.append("Contains 'example' or 'variant'")
        
    if reasons:
        issues.append((r, reasons))

print(f"\nFound {len(issues)} questions with quality issues:")
for r, reasons in issues:
    t = r.get('topics') or {}
    print(f"\nID: {r['id']} | Category: {t.get('category')} | Topic: {t.get('name')}")
    print(f"Issues: {reasons}")
    print(f"Body: {r.get('body')}")
    print(f"Options: {r.get('options')}")
    print(f"Answer: {r.get('answer')}")
