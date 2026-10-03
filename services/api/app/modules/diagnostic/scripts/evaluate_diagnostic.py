from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import silhouette_score

from ..adaptive import AdaptiveDiagnostic
from ..profiling import assign_profile, fit_profile_model, synthetic_population


def evaluate(seed: int = 7, learners: int = 1500) -> dict[str, object]:
    skills, archetypes = synthetic_population(seed=seed, size=learners)
    model = fit_profile_model(seed=seed)
    rng = np.random.default_rng(seed)
    topics = [str(index) for index in range(25)]
    questions = [
        {"id": str(index), "topic_id": str(index % 25), "difficulty": index % 5 + 1, "answer": "A"}
        for index in range(150)
    ]
    adaptive_errors: list[float] = []
    adaptive_correlations: list[float] = []
    fixed_errors: list[float] = []
    fixed_correlations: list[float] = []
    counts: list[int] = []
    for truth in skills[: min(100, learners)]:
        engine = AdaptiveDiagnostic(questions, topics, max_questions=25, min_topic_coverage=1)
        while not engine.should_stop():
            question = engine.next_question()
            if question is None:
                break
            probability = 1.0 / (1.0 + np.exp(-(truth[int(question["topic_id"])] - question["difficulty"] / 5.0) * 5.0))
            engine.answer(question, "A" if rng.random() < probability else "B")
        estimate = np.array([engine.mastery()[topic] for topic in topics])
        adaptive_errors.append(float(np.mean(np.abs(estimate - truth))))
        adaptive_correlations.append(float(spearmanr(estimate, truth).statistic))
        counts.append(engine.question_count)
        fixed_indices = rng.choice(len(questions), size=engine.question_count, replace=False)
        fixed_estimate = np.full(25, 0.5)
        for question_index in fixed_indices:
            question = questions[int(question_index)]
            probability = 1.0 / (1.0 + np.exp(-(truth[int(question["topic_id"])] - question["difficulty"] / 5.0) * 5.0))
            fixed_estimate[int(question["topic_id"])] = float(rng.random() < probability)
        fixed_errors.append(float(np.mean(np.abs(fixed_estimate - truth))))
        fixed_correlations.append(float(spearmanr(fixed_estimate, truth).statistic))
    assignments = np.array([assign_profile(row.tolist(), model)["cluster_id"] for row in skills])
    stability = []
    for stability_seed in range(5):
        stability_model = fit_profile_model(seed=stability_seed)
        stability_assignments = np.array([assign_profile(row.tolist(), stability_model)["cluster_id"] for row in skills])
        stability.append(float(silhouette_score(skills, stability_assignments)))
    report = {
        "seed": seed,
        "learners_evaluated": min(100, learners),
        "adaptive_mae": float(np.mean(adaptive_errors)),
        "adaptive_spearman": float(np.nanmean(adaptive_correlations)),
        "fixed_random_mae": float(np.mean(fixed_errors)),
        "fixed_random_spearman": float(np.nanmean(fixed_correlations)),
        "questions_to_confidence_mean": float(np.mean(counts)),
        "questions_to_confidence_max": int(np.max(counts)),
        "cluster_silhouette": float(silhouette_score(skills, assignments)),
        "cluster_silhouette_five_seed": stability,
        "cluster_silhouette_five_seed_mean": float(np.mean(stability)),
        "cluster_silhouette_five_seed_min": float(np.min(stability)),
        "cluster_sizes": {str(cluster): int(np.sum(assignments == cluster)) for cluster in sorted(set(assignments))},
        "archetype_cluster_counts": {
            str(archetype): {str(cluster): int(np.sum((archetypes == archetype) & (assignments == cluster))) for cluster in sorted(set(assignments))}
            for archetype in sorted(set(archetypes))
        },
        "model_version": model["version"],
    }
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--learners", type=int, default=1500)
    parser.add_argument("--output", type=Path, default=Path("diagnostic-evaluation.json"))
    args = parser.parse_args()
    report = evaluate(args.seed, args.learners)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
