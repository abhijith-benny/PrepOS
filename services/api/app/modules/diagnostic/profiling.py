from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.mixture import GaussianMixture


TOPIC_GROUPS = {
    "DSA": list(range(0, 5)),
    "aptitude": list(range(5, 10)),
    "CS core": list(range(10, 15)),
    "system design": list(range(15, 20)),
    "behavioral": list(range(20, 25)),
}
MODEL_VERSION = "diagnostic-profile-v1"
MODEL_PATH = Path(__file__).with_name("diagnostic_model.joblib")


def synthetic_population(seed: int = 7, size: int = 1500) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    archetypes = np.array(
        [
            [0.82, 0.45, 0.45, 0.45, 0.45],
            [0.45, 0.82, 0.45, 0.45, 0.45],
            [0.45, 0.45, 0.82, 0.45, 0.45],
            [0.45, 0.45, 0.45, 0.82, 0.45],
            [0.45, 0.45, 0.45, 0.45, 0.82],
        ]
    )
    labels = rng.integers(0, len(archetypes), size=size)
    base = np.repeat(archetypes[labels], 5, axis=1)
    noise = rng.normal(0.0, 0.09, size=base.shape)
    return np.clip(base + noise, 0.02, 0.98), labels


def _label(centroid: np.ndarray) -> str:
    scores = {
        group: float(np.mean(centroid[indexes]))
        for group, indexes in TOPIC_GROUPS.items()
    }
    strongest = max(scores, key=scores.get)
    weakest = min(scores, key=scores.get)
    if scores[strongest] - scores[weakest] < 0.12:
        return "Balanced learner"
    return f"Strong {strongest}, weak {weakest}"


def fit_profile_model(seed: int = 7) -> dict[str, Any]:
    features, true_labels = synthetic_population(seed=seed)
    candidates: list[tuple[float, str, Any]] = []
    for cluster_count in range(4, 7):
        kmeans = KMeans(n_clusters=cluster_count, random_state=seed, n_init=20).fit(features)
        candidates.append((silhouette_score(features, kmeans.labels_), "kmeans", kmeans))
        mixture = GaussianMixture(n_components=cluster_count, random_state=seed, n_init=5).fit(features)
        candidates.append((silhouette_score(features, mixture.predict(features)), "gmm", mixture))
    score, algorithm, model = max(candidates, key=lambda item: (item[0], item[1] == "kmeans"))
    centroids = model.cluster_centers_ if algorithm == "kmeans" else model.means_
    return {
        "version": MODEL_VERSION,
        "algorithm": algorithm,
        "model": model,
        "centroids": centroids,
        "labels": [_label(centroid) for centroid in centroids],
        "silhouette": float(score),
        "synthetic_labels": true_labels,
        "features": features,
    }


def load_profile_model(path: Path = MODEL_PATH) -> dict[str, Any]:
    if path.exists():
        return joblib.load(path)
    profile = fit_profile_model()
    joblib.dump(profile, path)
    return profile


def assign_profile(vector: list[float], profile: dict[str, Any]) -> dict[str, Any]:
    values = np.asarray(vector, dtype=float).reshape(1, -1)
    model = profile["model"]
    if profile["algorithm"] == "kmeans":
        cluster_id = int(model.predict(values)[0])
        distances = model.transform(values)[0]
    else:
        cluster_id = int(model.predict(values)[0])
        distances = np.linalg.norm(profile["centroids"] - values, axis=1)
    return {
        "cluster_id": cluster_id,
        "cluster_label": profile["labels"][cluster_id],
        "model_version": profile["version"],
        "distances": [float(distance) for distance in distances],
    }


def profile_summary(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_version": profile["version"],
        "algorithm": profile["algorithm"],
        "silhouette": profile["silhouette"],
        "cluster_count": len(profile["labels"]),
        "labels": profile["labels"],
    }