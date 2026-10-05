from __future__ import annotations

from typing import Any
import random


TECHNICAL_QUESTIONS: dict[str, list[dict[str, str]]] = {
    "DSA": [
        {
            "topic": "Data Structures & Algorithms",
            "question": "How would you detect and remove a cycle in a singly linked list? Explain the time and space complexity.",
            "hint": "Think about Floyd's Cycle-Finding algorithm (tortoise and hare).",
            "model_answer": "Use Floyd's cycle detection with slow and fast pointers moving at 1x and 2x speeds. If they meet, a cycle exists. Reset slow to head, advance both at 1x to find the cycle start, and set the preceding node's next to null. Time complexity is O(N) and space complexity is O(1).",
        },
        {
            "topic": "Data Structures & Algorithms",
            "question": "Explain how you would find the median of two sorted arrays of different sizes in O(log(min(N, M))) time.",
            "hint": "Consider binary search on the partition cut of the smaller array.",
            "model_answer": "Binary search on the smaller array's partition index. Ensure that maxLeftX <= minRightY and maxLeftY <= minRightX. If total length is odd, median is max(maxLeftX, maxLeftY); if even, average of max(lefts) and min(rights).",
        },
        {
            "topic": "Data Structures & Algorithms",
            "question": "What is the difference between BFS and DFS in graph traversal, and when would you prefer Dijkstra's algorithm over standard BFS?",
            "hint": "Think about queue vs stack, shortest path in unweighted vs weighted graphs.",
            "model_answer": "BFS traverses level-by-level using a queue, finding shortest path in unweighted graphs in O(V+E). DFS explores as deep as possible using recursion/stack. When edges have non-negative weights, standard BFS fails to guarantee shortest paths, so Dijkstra's algorithm with a min-priority queue (O((V+E)logV)) is required.",
        },
    ],
    "System Design": [
        {
            "topic": "System Design",
            "question": "Design a URL shortening service like Bitly. How would you handle high write throughput and collisions in ID generation?",
            "hint": "Discuss Base62 encoding, distributed ID generators (like Snowflake or counter ranges), and caching layers.",
            "model_answer": "A distributed URL shortener uses a Key Generation Service or distributed sequence (e.g., Twitter Snowflake) encoded with Base62 (62^7 ~ 3.5 trillion URLs). Read requests are cached via Redis with LRU eviction. Relational or NoSQL store with (short_hash primary key, original_url, user_id, created_at).",
        },
        {
            "topic": "System Design",
            "question": "Explain the CAP theorem and describe how you would choose between CP and AP for an e-commerce checkout vs a social media feed.",
            "hint": "Discuss consistency vs availability during network partitions.",
            "model_answer": "CAP theorem states in the presence of a network partition (P), a distributed system must choose between Consistency (C) or Availability (A). For e-commerce checkout/inventory, CP is chosen to prevent double spending/overselling. For a social media feed, AP is chosen because displaying slightly stale posts is preferable over rejecting user traffic.",
        },
    ],
    "Databases": [
        {
            "topic": "Databases & Storage",
            "question": "Explain what a B+ Tree index is and why databases prefer B+ Trees over Hash tables or Binary Search Trees for disk-based storage.",
            "hint": "Think about range queries, page block size, and fan-out.",
            "model_answer": "B+ Trees have high fan-out, reducing tree height and disk I/O operations per query. All data resides in leaf nodes linked sequentially, enabling efficient range scans (e.g. BETWEEN or inequalities), which Hash indexes cannot do. Binary Search Trees have small fan-out and unbalance easily.",
        },
        {
            "topic": "Databases & Storage",
            "question": "What are ACID properties, and how does Database Isolation Level affect concurrency phenomena like dirty reads and phantom reads?",
            "hint": "Define Atomicity, Consistency, Isolation, Durability, and standard ANSI isolation levels.",
            "model_answer": "ACID ensures reliable transactions. Isolation controls visibility of uncommitted work. Read Uncommitted allows dirty reads. Read Committed prevents dirty reads. Repeatable Read prevents non-repeatable reads using MVCC/snapshot isolation. Serializable prevents phantom reads by strict lock scheduling or optimistic serialization checks.",
        },
    ],
    "Core CS & Operating Systems": [
        {
            "topic": "Operating Systems",
            "question": "What is the difference between a process and a thread, and how does inter-process communication (IPC) differ from inter-thread communication?",
            "hint": "Address virtual address spaces, PCB vs TCB, context switching cost, and shared memory vs pipes/sockets.",
            "model_answer": "A process has its own isolated address space, heap, file descriptors, and Process Control Block. A thread is an execution unit within a process sharing the same address space, heap, and code segment. Context switching threads is cheaper because TLB/page tables are preserved. IPC requires kernel primitives (pipes, sockets, shared memory), while threads communicate via shared memory with mutexes/locks.",
        },
    ],
}

HR_QUESTIONS: list[dict[str, str]] = [
    {
        "topic": "Behavioral & STAR",
        "question": "Tell me about a challenging technical project you worked on. What was your role, what obstacles did you encounter, and what was the outcome?",
        "hint": "Structure your answer using Situation, Task, Action, and Result (STAR).",
        "model_answer": "Use STAR format: Describe the specific context (Situation/Task), quantify your individual contribution (Action - specific technical decisions and tradeoffs), and provide measurable outcomes (Result - performance gains, test coverage, or stakeholder feedback).",
    },
    {
        "topic": "Conflict & Teamwork",
        "question": "Describe a situation where you had a strong disagreement with a teammate or peer regarding a technical design decision. How did you resolve it?",
        "hint": "Focus on data-driven discussion, active listening, and committing to team alignment.",
        "model_answer": "Highlight objective criteria: benchmarked prototypes, evaluated constraints against requirements, listened openly to understand their trade-offs, reached a consensus or agreed to disagree and commit, maintaining positive team rapport.",
    },
    {
        "topic": "Failure & Learning",
        "question": "Tell me about a time you made a mistake or failed to deliver something on time. What happened, how did you handle the situation, and what did you learn?",
        "hint": "Demonstrate accountability, proactive communication with stakeholders, and preventive systems created.",
        "model_answer": "Acknowledge the mistake without deflection, explain immediate mitigation steps (communicating early, rolling back, or prioritizing essentials), and describe systemic improvements implemented to ensure the issue never reoccurred.",
    },
    {
        "topic": "Prioritization & Pressure",
        "question": "How do you manage your time and prioritize when you have multiple competing deadlines or sudden scope changes?",
        "hint": "Mention frameworks like Eisenhower matrix, stakeholder alignment, and trade-off analysis.",
        "model_answer": "Categorize tasks by urgency and impact, communicate proactively with mentors or team leads to align expectations, break work into milestones, and deprioritize non-critical items transparently.",
    },
    {
        "topic": "Career Goals & Motivation",
        "question": "Why are you interested in this role and company, and where do you see your technical growth over the next 2-3 years?",
        "hint": "Connect your foundational skills and genuine curiosity with the team's engineering mission.",
        "model_answer": "Articulate alignment between your current skill set and the company's technical stack, expressing ambition to grow from an autonomous junior engineer into an owner of end-to-end features and architectural components.",
    },
]


class InterviewQuestionGenerator:
    """Generates structured interview questions for technical and behavioral rounds."""

    @classmethod
    def generate_question(
        cls,
        round_type: str,
        target_role: str,
        turn_number: int,
        previous_feedback: str | None = None,
    ) -> dict[str, str]:
        if round_type == "hr":
            index = (turn_number - 1) % len(HR_QUESTIONS)
            return HR_QUESTIONS[index]

        # For technical round, rotate through domains
        domains = list(TECHNICAL_QUESTIONS.keys())
        domain = domains[(turn_number - 1) % len(domains)]
        questions_in_domain = TECHNICAL_QUESTIONS[domain]
        index = ((turn_number - 1) // len(domains)) % len(questions_in_domain)
        selected = questions_in_domain[index]

        # If previous answer was weak, we can provide contextual encouragement
        context_hint = selected.get("hint")
        if previous_feedback and "improve" in previous_feedback.lower():
            context_hint = f"Focus on technical precision: {context_hint}"

        return {
            "topic": selected["topic"],
            "question": selected["question"],
            "hint": context_hint or "",
            "model_answer": selected["model_answer"],
        }
