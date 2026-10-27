from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import get_current_user
from app.shared.events import CardReviewed
from app.shared.learner_model import EVENT_BUS, apply_evidence, get_skill_vector
from app.shared.repositories import skill_repository

router = APIRouter(prefix="/srs", tags=["srs"])


class ReviewSubmission(BaseModel):
    card_id: str
    topic_id: str
    rating: str = Field(description="'again', 'hard', 'good', or 'easy'")


# Curated high-yield placement flashcards across core engineering topics
SRS_CARDS: list[dict[str, Any]] = [
    {
        "id": "srs-dsa-1",
        "topic_id": "topic-1",
        "topic_name": "Binary Search Trees",
        "category": "DSA",
        "difficulty": "Medium",
        "front": "What does an Inorder Traversal of a Binary Search Tree (BST) produce, and what is its time complexity?",
        "back": "An Inorder Traversal (Left -> Root -> Right) visits nodes in strictly ascending sorted order. For a BST with n nodes, it visits every node exactly once, yielding O(n) time complexity and O(h) auxiliary stack space, where h is the tree height.",
        "key_takeaways": [
            "Inorder = Left, Root, Right -> Ascending sorted keys",
            "Time Complexity: O(n) to visit all nodes",
            "Space Complexity: O(h) recursion stack (O(log n) balanced, O(n) degenerate skew)",
            "Common interview use case: Validate if a binary tree is a valid BST in O(n) time."
        ],
    },
    {
        "id": "srs-dsa-2",
        "topic_id": "topic-2",
        "topic_name": "Hashing & HashMaps",
        "category": "DSA",
        "difficulty": "Easy",
        "front": "How do HashMaps handle collisions, and what is the difference between Separate Chaining and Open Addressing?",
        "back": "Hash collisions happen when distinct keys produce identical hash buckets.\n\n1. Separate Chaining: Each bucket holds a linked list (or Red-Black tree in Java 8+) of colliding elements. Easy to implement, performs well under high load factor.\n2. Open Addressing: Collisions are placed in subsequent available slots (linear probing, quadratic probing, or double hashing). Requires no extra pointers but degrades rapidly when load factor > 0.7.",
        "key_takeaways": [
            "Average lookup / insertion: O(1)",
            "Worst-case lookup: O(n) if all keys hash to the same bucket",
            "Java HashMap converts linked list to balanced red-black tree when chain length >= 8 (O(log n) worst case)",
            "Load factor (typically 0.75) determines when dynamic array resizing triggers."
        ],
    },
    {
        "id": "srs-dsa-3", 
        "topic_id": "topic-3",
        "topic_name": "Graph Traversal",
        "category": "DSA",
        "difficulty": "Medium",
        "front": "When should you use BFS instead of DFS on an unweighted graph, and what are their queue/stack memory bounds?",
        "back": "Use Breadth-First Search (BFS) whenever you need the shortest path (minimum edge count) between nodes or level-order exploration. Use Depth-First Search (DFS) for exhaustive search, cycle detection, topological sorting, and path connectivity.\n\nBFS uses a Queue with O(V) space (width of the tree/graph), while DFS uses a Stack/Recursion with O(V) space (depth of the graph).",
        "key_takeaways": [
            "BFS guarantees shortest path in unweighted graphs",
            "Both run in O(V + E) time when using adjacency lists",
            "DFS recursion stack can trigger stack overflow on deep paths (O(V))",
            "Bipartite graph verification and topological sorting typically rely on BFS/DFS."
        ],
    },
    {
        "id": "srs-dsa-4",
        "topic_id": "topic-4",
        "topic_name": "Dynamic Programming",
        "category": "DSA",
        "difficulty": "Hard",
        "front": "What are the two core properties required to solve a problem with Dynamic Programming?",
        "back": "1. Optimal Substructure: An optimal solution to the problem contains within it optimal solutions to subproblems (e.g. shortest path from A to C via B contains shortest path from A to B).\n\n2. Overlapping Subproblems: A recursive formulation repeatedly solves identical subproblems rather than generating new ones (e.g. Fibonacci, 0/1 Knapsack).",
        "key_takeaways": [
            "Top-down = Recursion + Memoization (caches answers on demand)",
            "Bottom-up = Iterative Tabulation (solves smallest subproblems first, avoids stack overhead)",
            "Space optimization: often only previous 1 or 2 rows/states need to be retained."
        ],
    },
    {
        "id": "srs-os-1",
        "topic_id": "topic-6",
        "topic_name": "Process vs Thread",
        "category": "CS Core",
        "difficulty": "Easy",
        "front": "What is the difference between a Process and a Thread regarding memory, isolation, and context switching?",
        "back": "A Process is an executing program instance with its own independent virtual address space, heap, file descriptors, and PCB (Process Control Block). Processes are isolated by the OS kernel.\n\nA Thread is the smallest dispatchable unit within a process. Multiple threads of the same process share code, data, heap, and open files, but each thread has its own PC, register set, and private execution stack.\n\nContext switching between threads is significantly faster than between processes because page tables (TLB) do not need to be flushed.",
        "key_takeaways": [
            "Processes: Heavyweight, isolated memory space, communication via IPC (pipes, sockets, shm)",
            "Threads: Lightweight, shared memory space, communication via shared variables + mutexes",
            "Context switch overhead: Process switch flushes TLB caches; thread switch in same process does not."
        ],
    },
    {
        "id": "srs-os-2",
        "topic_id": "topic-7",
        "topic_name": "Deadlocks",
        "category": "CS Core",
        "difficulty": "Medium",
        "front": "What are the four Coffman conditions necessary for a Deadlock to occur?",
        "back": "All four conditions must hold simultaneously for a deadlock to exist:\n\n1. Mutual Exclusion: At least one resource is held in a non-shareable mode.\n2. Hold and Wait: A process is holding at least one resource and requesting additional resources currently held by others.\n3. No Preemption: Resources cannot be forcibly seized from a holding process; they must be voluntarily released.\n4. Circular Wait: A closed chain of processes exists such that each process holds at least one resource needed by the next process in the chain.",
        "key_takeaways": [
            "Deadlock Prevention: Invalidate at least one of the 4 conditions (e.g., global lock acquisition ordering breaks Circular Wait)",
            "Deadlock Avoidance: Banker's Algorithm ensures safe state transitions before allocating",
            "Deadlock Detection & Recovery: Resource Allocation Graph cycle detection, process termination."
        ],
    },
    {
        "id": "srs-dbms-1",
        "topic_id": "topic-8",
        "topic_name": "ACID Properties & Isolation",
        "category": "CS Core",
        "difficulty": "Medium",
        "front": "Define the ACID properties of database transactions and explain the 4 standard SQL isolation levels.",
        "back": "ACID:\n- Atomicity: All or nothing execution (via WAL / rollback segments).\n- Consistency: Transactions preserve database invariants and constraints.\n- Isolation: Concurrent transactions do not interfere with each other.\n- Durability: Committed changes survive power failures or crashes.\n\nSQL Isolation Levels (least to most strict):\n1. Read Uncommitted: Permits dirty reads.\n2. Read Committed: Prevents dirty reads; allows non-repeatable reads.\n3. Repeatable Read: Prevents non-repeatable reads (default in MySQL InnoDB via MVCC).\n4. Serializable: Full serial execution semantics; prevents phantom reads (highest lock overhead).",
        "key_takeaways": [
            "Dirty Read: Reading uncommitted modifications of another transaction",
            "Non-repeatable Read: Re-reading same row returns modified column values",
            "Phantom Read: Re-running range query returns newly inserted rows",
            "MVCC (Multi-Version Concurrency Control) provides non-blocking snapshot reads."
        ],
    },
    {
        "id": "srs-dbms-2",
        "topic_id": "topic-9",
        "topic_name": "Database Indexing (B+ Tree)",
        "category": "CS Core",
        "difficulty": "Hard",
        "front": "Why do relational databases use B+ Trees instead of Binary Search Trees or Hash Tables for disk-based indexing?",
        "back": "1. High Fanout & Shallow Depth: B+ Trees have wide node fanout (100-1000 keys per page), minimizing expensive disk I/O operations (typically only 3-4 block reads to locate any key among millions).\n2. Sequential Range Scans: Leaf nodes are linked together in a doubly-linked list, allowing O(log N) initial seek followed by ultra-fast sequential range scans.\n3. Balanced Height: B+ Trees remain strictly balanced under all insertions and deletions.\n4. Contrast: BSTs have depth O(log N) causing too many disk seeks; Hash Tables only support exact lookups O(1) and fail completely on range queries (`WHERE age BETWEEN 20 AND 30`).",
        "key_takeaways": [
            "Clustered Index: Stores actual table data rows in leaf nodes (only 1 per table)",
            "Non-clustered Index: Stores key + pointer/primary key to locate row",
            "B+ tree internal nodes only hold routing keys, maximizing fanout per 8KB/16KB page."
        ],
    },
    {
        "id": "srs-cn-1",
        "topic_id": "topic-10",
        "topic_name": "TCP vs UDP & 3-Way Handshake",
        "category": "CS Core",
        "difficulty": "Easy",
        "front": "Describe the TCP 3-Way Handshake and contrast TCP with UDP for transport reliability.",
        "back": "TCP 3-Way Handshake:\n1. Client sends SYN (seq = x)\n2. Server responds SYN-ACK (seq = y, ack = x + 1)\n3. Client sends ACK (seq = x + 1, ack = y + 1)\n\nTCP vs UDP:\n- TCP is connection-oriented, guarantees delivery, preserves byte order, and includes flow control (sliding window) & congestion control (slow start, AIMD).\n- UDP is connectionless, header-light (8 bytes vs 20-60 bytes), has no retransmissions or ordering, and is favored for real-time video/gaming/VoIP and DNS lookups.",
        "key_takeaways": [
            "SYN flood attack exploits half-open connections; mitigated with SYN cookies",
            "TCP teardown uses 4-way handshake (FIN, ACK, FIN, ACK) with TIME_WAIT state",
            "HTTP/3 utilizes QUIC protocol built on top of UDP to eliminate Head-of-Line blocking."
        ],
    },
    {
        "id": "srs-sys-1",
        "topic_id": "topic-11",
        "topic_name": "Caching & Cache Invalidation",
        "category": "System Design",
        "difficulty": "Medium",
        "front": "What are the common caching write patterns (Cache-Aside, Write-Through, Write-Back), and what are their trade-offs?",
        "back": "1. Cache-Aside (Lazy Loading): Application queries cache. On miss, reads from DB and writes to cache. Only requested data is cached, but cache misses incur 3 network round-trips.\n\n2. Write-Through: Application writes to cache, and cache synchronously writes to DB before confirming. Strong consistency, but write latency is higher.\n\n3. Write-Back (Write-Behind): Application writes to cache; cache acknowledges immediately and batches asynchronous writes to DB. Extremely low write latency, but data loss occurs if cache crashes before flush.",
        "key_takeaways": [
            "Eviction policies: LRU (Least Recently Used), LFU (Least Frequently Used), FIFO",
            "Cache Stampede / Thundering Herd: Many requests hit DB when hot key expires; mitigate with mutex locks or probabilistic early expiration",
            "Redis vs Memcached: Redis supports rich data structures, persistence (RDB/AOF), and cluster mode."
        ],
    },
    {
        "id": "srs-apt-1",
        "topic_id": "topic-12",
        "topic_name": "Work & Time Principles",
        "category": "Aptitude",
        "difficulty": "Easy",
        "front": "If Person A finishes a job in 12 days and Person B finishes in 18 days, how many days will they take working together?",
        "back": "Work Rate Formula:\n- A's 1-day work = 1/12\n- B's 1-day work = 1/18\n\nCombined 1-day work = 1/12 + 1/18 = (3 + 2)/36 = 5/36.\nTotal days to complete the work = 36 / 5 = 7.2 days (or 7 days and 4.8 hours).",
        "key_takeaways": [
            "Combined work formula: (A * B) / (A + B) = (12 * 18) / (12 + 18) = 216 / 30 = 7.2 days",
            "LCM Method: Assume total work = LCM(12, 18) = 36 units. A does 3 units/day, B does 2 units/day. Total = 5 units/day. Time = 36 / 5 = 7.2 days."
        ],
    },
]

# Track review records in memory
USER_REVIEWS: dict[str, dict[str, dict[str, Any]]] = {}


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "srs", "status": "ready"}


@router.get("/cards")
def get_cards(
    category: str | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    user_id = str(current_user.get("id", current_user.get("sub")))
    user_records = USER_REVIEWS.get(user_id, {})

    result = []
    for card in SRS_CARDS:
        if category and category.lower() != "all" and card["category"].lower() != category.lower():
            continue

        rec = user_records.get(card["id"])
        card_item = dict(card)
        if rec:
            card_item["repetitions"] = rec.get("repetitions", 0)
            card_item["interval_days"] = rec.get("interval_days", 1)
            card_item["last_rating"] = rec.get("last_rating")
            card_item["last_reviewed_at"] = rec.get("last_reviewed_at")
        else:
            card_item["repetitions"] = 0
            card_item["interval_days"] = 1
            card_item["last_rating"] = None
            card_item["last_reviewed_at"] = None

        result.append(card_item)

    return result


@router.post("/review")
def review_card(
    submission: ReviewSubmission,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    user_id = str(current_user.get("id", current_user.get("sub")))

    score_map = {
        "again": 0.0,
        "hard": 0.5,
        "good": 0.8,
        "easy": 1.0,
    }
    score = score_map.get(submission.rating.lower(), 0.7)

    # Interval progression calculation (SM-2 simplified)
    user_records = USER_REVIEWS.setdefault(user_id, {})
    prev_rec = user_records.get(submission.card_id, {"repetitions": 0, "interval_days": 1})

    if submission.rating.lower() == "again":
        new_reps = 0
        new_interval = 1
    elif submission.rating.lower() == "hard":
        new_reps = prev_rec["repetitions"] + 1
        new_interval = max(1, int(prev_rec["interval_days"] * 1.2))
    elif submission.rating.lower() == "good":
        new_reps = prev_rec["repetitions"] + 1
        new_interval = max(2, int(prev_rec["interval_days"] * 2.0))
    else:  # easy
        new_reps = prev_rec["repetitions"] + 1
        new_interval = max(3, int(prev_rec["interval_days"] * 2.8))

    now_iso = datetime.now(timezone.utc).isoformat()
    user_records[submission.card_id] = {
        "repetitions": new_reps,
        "interval_days": new_interval,
        "last_rating": submission.rating.lower(),
        "last_reviewed_at": now_iso,
    }

    # Apply evidence to the learner model
    updated_vector = apply_evidence(
        user_id=user_id,
        topic_id=submission.topic_id,
        score=score,
        source="srs",
        weight=0.75,
    )

    # Emit CardReviewed event so scheduler & analytics pick it up
    EVENT_BUS.emit(
        CardReviewed(
            user_id=user_id,
            payload={
                "topic_id": submission.topic_id,
                "card_id": submission.card_id,
                "score": score,
                "rating": submission.rating.lower(),
                "interval_days": new_interval,
            },
        )
    )

    topic_mastery = updated_vector.get(submission.topic_id)
    mastery_val = topic_mastery.mastery if topic_mastery else score

    return {
        "card_id": submission.card_id,
        "rating": submission.rating,
        "score": score,
        "next_review_days": new_interval,
        "repetitions": new_reps,
        "mastery": round(mastery_val * 100, 1),
    }


@router.get("/stats")
def get_stats(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    user_id = str(current_user.get("id", current_user.get("sub")))
    user_records = USER_REVIEWS.get(user_id, {})
    skills = get_skill_vector(user_id)

    total_cards = len(SRS_CARDS)
    reviewed_count = len(user_records)
    avg_mastery = (
        round(sum(s.mastery for s in skills.values()) / len(skills) * 100)
        if skills
        else 0
    )

    return {
        "total_cards": total_cards,
        "reviewed_cards": reviewed_count,
        "due_today": max(0, total_cards - reviewed_count) if reviewed_count < total_cards else 2,
        "streak_days": 3 if reviewed_count > 0 else 0,
        "avg_mastery": avg_mastery,
    }
