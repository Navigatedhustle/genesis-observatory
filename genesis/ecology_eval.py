"""Matched ecology comparison. Evaluation disables reproduction for equal 180x600 slots."""

import json
import time
from pathlib import Path

import numpy as np

from .store import Store
from .world import World


def run(seeds=range(11, 17)):
    started = time.perf_counter()
    rows = []
    for seed in seeds:
        trained = {}
        for mode in ["evolving", "frozen", "random"]:
            w = World(seed, mode=mode)
            w.step(2000)
            trained[mode] = w
        for variant in [0.7, 1.25]:
            for mode, train in trained.items():
                w = World(
                    seed + 1000,
                    mode="random" if mode == "random" else "frozen",
                    variation=variant,
                )
                w.reproduction = False
                if len(train.genes):
                    rng = np.random.default_rng(seed + 7000)
                    w.genes = train.genes[rng.integers(0, len(train.genes), 180)].copy()
                # If training went extinct, use original random actions; record extinction.
                w.step(600)
                rows.append(
                    {
                        "train_seed": seed,
                        "test_seed": seed + 1000,
                        "environment": variant,
                        "mode": mode,
                        "training_extinct": len(train.genes) == 0,
                        "train_metrics": train.metrics(),
                        "evaluation_slots": 108000,
                        "survival_fraction": w.organism_ticks / 108000,
                        "consumed_per_slot": w.consumed / 108000,
                        "test_metrics": w.metrics(),
                    }
                )
    means = {
        mode: float(
            np.mean([r["survival_fraction"] for r in rows if r["mode"] == mode])
        )
        for mode in ["evolving", "frozen", "random"]
    }
    diff = means["evolving"] - means["frozen"]
    summary = f"Held-out survival: evolved {means['evolving']:.1%}, frozen {means['frozen']:.1%}, random {means['random']:.1%}. Mutation advantage {diff:+.1%}; limited six-seed evaluation, no general intelligence claim. Cooperation was not tested (no transfer action)."
    result = {
        "protocol": {
            "train_ticks": 2000,
            "test_ticks": 600,
            "initial_population": 180,
            "seeds": list(seeds),
            "held_out_environments": [0.7, 1.25],
            "evaluation_budget": "180 organisms × 600 tick slots; no reproduction during evaluation; dead slots score zero",
            "metric": "fraction of allocated organism ticks spent alive",
            "selection_note": "Both evolving and frozen populations undergo survival selection during training; only evolving controllers mutate",
            "random_note": "Random action baseline has no inherited controller",
        },
        "rows": rows,
        "means": means,
        "summary": summary,
        "elapsed_s": time.perf_counter() - started,
    }
    return result


if __name__ == "__main__":
    result = run()
    root = Path(__file__).resolve().parent.parent
    (root / "reports/ecology-evaluation.json").write_text(json.dumps(result, indent=2))
    Store(root / "data/genesis.sqlite").put("ecology_evaluation", result)
    print(result["summary"])
    print("elapsed_s", result["elapsed_s"])
