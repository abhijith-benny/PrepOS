import os
import sys
from supabase import create_client
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv('services/api/.env')

sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_ROLE_KEY'))

# 1. Fix Sentence Correction questions with bracketed text to have a proper instruction stem
sc_updates = [
    (
        "bed4e709-1110-493f-a9da-04ae95fec80f",
        "In the sentence below, select the option that best replaces the bracketed phrase to make the sentence grammatically correct:\n\n\"After the meeting, the team members, [who were exhausted], went home early.\""
    ),
    (
        "73d2dbd4-05b5-4f3e-bbd3-98d3725f9be8",
        "In the sentence below, select the option that best replaces the bracketed phrase to make the sentence grammatically correct:\n\n\"She answered the question, [despite she was nervous], correctly.\""
    ),
    (
        "1de6d819-5563-4219-9e63-4746a3c52956",
        "In the sentence below, select the option that best replaces the bracketed phrase to make the sentence grammatically correct:\n\n\"The manager, [who she had hired last year], resigned unexpectedly.\""
    ),
    (
        "671952d1-7c69-4d75-97eb-89745f5b5c86",
        "In the sentence below, select the option that best replaces the bracketed phrase to make the sentence grammatically correct:\n\n\"The novel, [which was written by an unknown author], became a bestseller.\""
    ),
    (
        "ef618764-322c-43d9-8a6c-e1343f8f1f6b",
        "In the sentence below, select the option that best replaces the bracketed phrase to make the sentence grammatically correct:\n\n\"The report, [that contains several errors], needs to be revised.\""
    ),
]

for qid, new_body in sc_updates:
    res = sb.table("questions").update({"body": new_body}).eq("id", qid).execute()
    print(f"Updated SC Question {qid}")

# 2. Replace duplicate aptitude question '1b80ba88-64aa-46f4-8ba7-7a31a199f936' with a fresh percentage problem
sb.table("questions").update({
    "body": "A student's score in mathematics increased from 64 to 80. What is the percentage increase in the score?",
    "options": ["20%", "25%", "16%", "24%"],
    "answer": "25%",
    "explanation": "Percentage increase = ((New - Old) / Old) * 100 = ((80 - 64) / 64) * 100 = (16 / 64) * 100 = 25%."
}).eq("id", "1b80ba88-64aa-46f4-8ba7-7a31a199f936").execute()
print("Replaced duplicate aptitude question 1b80ba88...")

# 3. Upgrade toy vocabulary & grammar questions to rich placement questions
vocab_grammar_upgrades = [
    (
        "4628021f-e446-49f0-831a-0bc808cf0334",
        "In a technical report, maintaining clarity is paramount. Which word is closest in meaning to 'CONCISE'?",
        ["Succinct and to the point", "Elaborate and comprehensive", "Ambiguous and abstract", "Lengthy and detailed"],
        "Succinct and to the point",
        "Concise means expressing what needs to be said without unnecessary words; succinct is an exact synonym."
    ),
    (
        "26291b30-d50e-4cd5-80b7-e1176e929e35",
        "Select the word that is most nearly OPPOSITE in meaning to 'SCARCE' in an inventory management context:",
        ["Abundant", "Deficient", "Meager", "Sporadic"],
        "Abundant",
        "Scarce means insufficient for the demand or rare; its direct antonym is abundant."
    ),
    (
        "a93c30d0-3019-4bfc-8eac-7b4fd3387699",
        "The project team implemented automated testing to 'MITIGATE' production incidents. What does 'mitigate' mean?",
        ["To make less severe or serious", "To eradicate completely", "To monitor continuously", "To accelerate rapidly"],
        "To make less severe or serious",
        "Mitigate means to make something bad or dangerous less severe, painful, or damaging."
    ),
    (
        "b59e4d55-4550-4d88-a603-3634736c7bbb",
        "When designing microservices, which term best describes a system that performs consistently according to specifications?",
        ["Reliable", "Ephemeral", "Redundant", "Speculative"],
        "Reliable",
        "A reliable system performs consistently according to specifications and maintains fault tolerance."
    ),
    (
        "122b4e7b-308c-4572-bf67-9dfdad7b638f",
        "Choose the sentence that correctly uses the word 'ALLOCATE' in an engineering context:",
        [
            "The cluster manager was configured to allocate CPU cores dynamically based on queue depth.",
            "The developer decided to allocate the bug to avoid fixing it.",
            "The database query allocate when index lookup failed.",
            "We allocate through the documentation to find the API endpoint."
        ],
        "The cluster manager was configured to allocate CPU cores dynamically based on queue depth.",
        "Allocate means to distribute or designate resources for a particular purpose."
    ),
    (
        "9540acbe-8403-4a2a-90b7-ea38a5d06199",
        "Identify the sentence that is grammatically correct and demonstrates the most effective professional phrasing:",
        [
            "Because the automated test suite failed, the engineering team paused the production deployment.",
            "Due to the test failed, deployment was paused because of by the engineering team.",
            "The deployment paused because of it failed the automated test suite by team.",
            "Having failed the test suite, production deployment was paused without no explanation."
        ],
        "Because the automated test suite failed, the engineering team paused the production deployment.",
        "Option A has correct subordinate clause structure, appropriate subject-verb agreement, and unambiguous agency."
    ),
    (
        "8d8b14a3-d975-474c-bdcd-dcb0ddbe4923",
        "In technical documentation, which transitional word or phrase best signals an exception or contrast between two ideas?",
        ["However", "Consequently", "Furthermore", "Namely"],
        "However",
        "'However' signals contrast or introduces a statement that contrasts with the previous clause."
    ),
    (
        "63e62c6c-e7cf-4810-867c-92cf4ae731d6",
        "Select the sentence that is correctly structured in ACTIVE voice with clear subject and action:",
        [
            "The lead architect refactored the legacy authentication service to improve latency.",
            "The legacy authentication service was refactored by the lead architect to improve latency.",
            "Latency was improved through the refactoring of the service being performed.",
            "Refactoring had been done to the authentication service by the team lead."
        ],
        "The lead architect refactored the legacy authentication service to improve latency.",
        "In active voice, the subject ('The lead architect') performs the action of the verb ('refactored') on the object."
    ),
    (
        "5daf83e9-410f-4494-92fc-6cb96ebb218b",
        "Select the option that correctly demonstrates present perfect tense with an ongoing duration:",
        [
            "She has lived in Seattle for five years and continues to work remotely.",
            "She have lived in Seattle since five years and continues to work remotely.",
            "She is living in Seattle for five years and continues to work remotely.",
            "She lived in Seattle since five years and continues to work remotely."
        ],
        "She has lived in Seattle for five years and continues to work remotely.",
        "'Has lived' (singular third person present perfect) correctly combines with 'for [duration]' to express an action started in the past continuing into the present."
    ),
    (
        "a063ab2e-763b-4611-9f6c-a3c5e27ab17b",
        "Choose the sentence that demonstrates correct subject-verb agreement with correlative pronouns:",
        [
            "Neither candidate was prepared for the technical architecture interview.",
            "Neither candidate were prepared for the technical architecture interview.",
            "Neither of candidates were prepared for the technical architecture interview.",
            "Neither candidate have been prepared for the technical architecture interview."
        ],
        "Neither candidate was prepared for the technical architecture interview.",
        "'Neither' used as a singular pronoun takes a singular verb ('was', not 'were')."
    ),
]

for qid, body, opts, ans, exp in vocab_grammar_upgrades:
    sb.table("questions").update({
        "body": body,
        "options": opts,
        "answer": ans,
        "explanation": exp
    }).eq("id", qid).execute()
    print(f"Upgraded question {qid}")

print("\nAll targeted questions have been upgraded!")
