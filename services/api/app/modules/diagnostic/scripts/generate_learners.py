from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from ..profiling import synthetic_population


def generate(seed: int = 7, size: int = 1500, output: Path | None = None) -> dict[str, list]:
    skills, archetypes = synthetic_population(seed=seed, size=size)
    rng = np.random.default_rng(seed)
    difficulties = rng.integers(1, 6, size=(size, 150))
    topic_skill = np.repeat(skills, 6, axis=1)
    probabilities = 1.0 / (1.0 + np.exp(-(topic_skill - difficulties / 5.0) * 5.0))
    answers = rng.random(probabilities.shape) < probabilities
    result = {
        "seed": seed,
        "skills": skills.tolist(),
        "archetypes": archetypes.tolist(),
        "difficulties": difficulties.tolist(),
        "answers": answers.astype(int).tolist(),
    }
    if output:
        output.write_text(__import__("json").dumps(result), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--size", type=int, default=1500)
    parser.add_argument("--output", type=Path, default=Path("diagnostic-learners.json"))
    args = parser.parse_args()
    generate(args.seed, args.size, args.output)
    print(f"wrote {args.size} learners to {args.output}")
