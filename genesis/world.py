"""CPU ecology. No language model influences organism actions."""

import copy
import hashlib
import json

import numpy as np

SIZE = 48
INPUTS = 10
HIDDEN = 8
OUTPUTS = 6
GENES = INPUTS * HIDDEN + HIDDEN * OUTPUTS
DELTAS = np.array([[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1], [0, 0]])


class World:
    def __init__(self, seed=42, population=180, mode="evolving", variation=1.0):
        self.seed = seed
        self.mode = mode
        self.variation = variation
        self.rng = np.random.default_rng(seed)
        self.tick = 0
        self.next_id = population
        noise = self.rng.random((SIZE, SIZE))
        # Fixed terrain varies smoothly, independently of interventions.
        self.terrain = (
            0.7
            + sum(
                np.roll(noise, (i, j), (0, 1))
                for i, j in [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]
            )
            / 5
        )
        self.capacity = (1.2 + 1.4 * (self.terrain - 0.7)) * variation
        self.food = self.capacity * self.rng.uniform(0.3, 1, (SIZE, SIZE))
        self.pos = self.rng.integers(0, SIZE, (population, 2))
        self.energy = np.full(population, 8.0)
        self.age = np.zeros(population, dtype=int)
        self.generation = np.zeros(population, dtype=int)
        self.ids = np.arange(population)
        self.lineage = self.ids.copy()
        self.parent = np.full(population, -1)
        self.genes = self.rng.normal(0, 0.7, (population, GENES))
        self.laws = []
        self.reproduction = True
        self.organism_ticks = 0
        self.births = 0
        self.deaths = 0
        self.consumed = 0.0
        self.generated = 0.0
        self.spent = 0.0
        self.death_loss = 0.0
        self.initial_energy = float(self.energy.sum() + self.food.sum())
        self.history = []
        self.cages = []

    def multipliers(self):
        move = np.ones((SIZE, SIZE))
        growth = np.ones((SIZE, SIZE))
        for law in self.laws:
            if self.tick < law.get("start", 0):
                continue
            if law.get("end") is not None and self.tick >= law["end"]:
                continue
            x0, y0, x1, y1 = law["region"]
            target = growth if law["kind"] == "growth" else move
            target[y0:y1, x0:x1] *= law["factor"]
        return move, growth

    def probe_cost(self, x, y):
        move, _ = self.multipliers()
        return float(self.terrain[y, x] * move[y, x])

    def add_law(self, law):
        self.laws.append(copy.deepcopy(law))

    def resource_pulse(self, region, fraction):
        """Recorded external energy, separate from natural renewal and consumption."""
        x0, y0, x1, y1 = region
        current = self.food[y0:y1, x0:x1]
        target = np.clip(
            current + self.capacity[y0:y1, x0:x1] * fraction,
            0,
            self.capacity[y0:y1, x0:x1],
        )
        delta = target - current
        self.operator_added = getattr(self, "operator_added", 0.0) + float(
            delta.clip(min=0).sum()
        )
        self.operator_removed = getattr(self, "operator_removed", 0.0) - float(
            delta.clip(max=0).sum()
        )
        current[:] = target
        return float(delta.sum())

    def step(self, n=1):
        for _ in range(n):
            self._step()

    def _step(self):
        move, growth = self.multipliers()
        added = np.minimum(
            self.capacity - self.food,
            0.025 * growth * self.variation * (1 - self.food / self.capacity),
        )
        added = np.maximum(added, 0)
        self.food += added
        self.generated += float(added.sum())
        count = len(self.energy)
        self.organism_ticks = getattr(self, "organism_ticks", 0) + count
        if count:
            x, y = self.pos.T
            local = (
                np.stack(
                    [
                        self.food[y, x],
                        self.food[y, (x + 1) % SIZE],
                        self.food[y, (x - 1) % SIZE],
                        self.food[(y + 1) % SIZE, x],
                        self.food[(y - 1) % SIZE, x],
                    ],
                    axis=1,
                )
                / 3
            )
            senses = np.concatenate(
                [
                    local,
                    (self.energy / 16)[:, None],
                    (self.age / 500)[:, None],
                    (self.terrain[y, x] / 2)[:, None],
                    self.rng.uniform(-1, 1, (count, 1)),
                    np.ones((count, 1)),
                ],
                axis=1,
            )
            if self.mode == "random":
                actions = self.rng.integers(0, OUTPUTS, count)
            else:
                h = np.tanh(
                    np.einsum(
                        "ni,nih->nh", senses, self.genes[:, :80].reshape(-1, 10, 8)
                    )
                )
                scores = np.einsum(
                    "nh,nho->no", h, self.genes[:, 80:].reshape(-1, 8, 6)
                )
                actions = scores.argmax(axis=1)
            self.controller_trace = {
                "tick": self.tick,
                "entities": {
                    str(int(self.ids[i])): {
                        "inputs": senses[i].tolist(),
                        "hidden": h[i].tolist() if self.mode != "random" else None,
                        "action": int(actions[i]),
                    }
                    for i in range(count)
                },
            }
            moving = (actions > 0) & (actions < 5)
            cost = 0.03 + 0.13 * self.terrain[y, x] * move[y, x] * moving
            self.energy -= cost
            self.spent += float(cost.sum())
            self.pos = (self.pos + DELTAS[actions]) % SIZE
            # Simultaneous sharing of a finite cell's resource. No altruism mechanic.
            x, y = self.pos.T
            eat = actions == 5
            for cx, cy in self.cages:
                eat &= ~((x == cx) & (y == cy))
            flat = y * SIZE + x
            requests = np.bincount(flat[eat], minlength=SIZE * SIZE)
            allowance = np.minimum(0.45, self.food.ravel() / np.maximum(requests, 1))
            gain = allowance[flat] * eat
            np.add.at(self.food, (y, x), -gain)
            self.energy += gain
            self.consumed += float(gain.sum())
            self.age += 1
            alive = (self.energy > 0) & (self.age < 600)
            # Negative energy overshoot has already been accounted as expenditure.
            self.death_loss += float(self.energy[~alive].sum())
            self.deaths += int((~alive).sum())
            for attr in [
                "pos",
                "energy",
                "age",
                "generation",
                "ids",
                "lineage",
                "parent",
                "genes",
            ]:
                setattr(self, attr, getattr(self, attr)[alive])
            parents = (
                np.flatnonzero(
                    (self.energy > 15)
                    & (self.age > 20)
                    & (self.rng.random(len(self.energy)) < 0.06)
                )[: max(0, 600 - len(self.energy))]
                if getattr(self, "reproduction", True)
                else np.array([], dtype=int)
            )
            if len(parents):
                self.energy[parents] *= 0.5
                children = self.genes[parents].copy()
                if self.mode == "evolving":
                    children += self.rng.normal(0, 0.09, children.shape) * (
                        self.rng.random(children.shape) < 0.15
                    )
                values = {
                    "pos": (
                        self.pos[parents] + self.rng.integers(-1, 2, (len(parents), 2))
                    )
                    % SIZE,
                    "energy": self.energy[parents].copy(),
                    "age": np.zeros(len(parents), dtype=int),
                    "generation": self.generation[parents] + 1,
                    "ids": np.arange(self.next_id, self.next_id + len(parents)),
                    "lineage": self.lineage[parents],
                    "parent": self.ids[parents],
                    "genes": children,
                }
                for k, v in values.items():
                    setattr(self, k, np.concatenate([getattr(self, k), v]))
                self.next_id += len(parents)
                self.births += len(parents)
        self.tick += 1
        if self.tick % 20 == 0:
            self.history.append(self.metrics())
            self.history = self.history[-300:]

    def metrics(self):
        total = float(self.energy.sum() + self.food.sum())
        metrics = {
            "tick": self.tick,
            "population": len(self.energy),
            "mean_energy": round(float(self.energy.mean()), 3)
            if len(self.energy)
            else 0,
            "organism_energy": round(float(self.energy.sum()), 3),
            "resource_energy": round(float(self.food.sum()), 3),
            "resource_coverage": round(float((self.food > 0.4).mean()), 4),
            "lineages": len(np.unique(self.lineage)),
            "max_generation": int(self.generation.max()) if len(self.energy) else 0,
            "organism_ticks": getattr(self, "organism_ticks", 0),
            "births": self.births,
            "deaths": self.deaths,
            "food_consumed": round(self.consumed, 3),
            "energy_spent": round(self.spent, 3),
            "resource_generated": round(self.generated, 3),
            "balance_error": total
            - (
                self.initial_energy
                + self.generated
                - self.spent
                - self.death_loss
                + getattr(self, "operator_added", 0.0)
                - getattr(self, "operator_removed", 0.0)
            ),
        }
        if hasattr(self, "operator_added"):
            metrics.update(
                operator_energy_added=self.operator_added,
                operator_energy_removed=self.operator_removed,
            )
        return metrics

    def snapshot(self):
        result = {}
        for k, v in self.__dict__.items():
            if k == "rng":
                result["rng_state"] = copy.deepcopy(v.bit_generator.state)
            elif isinstance(v, np.ndarray):
                result[k] = v.tolist()
            else:
                result[k] = copy.deepcopy(v)
        return result

    @classmethod
    def restore(cls, s):
        w = cls.__new__(cls)
        ints = {"pos", "age", "generation", "ids", "lineage", "parent"}
        arrays = ints | {"terrain", "capacity", "food", "energy", "genes"}
        for k, v in s.items():
            if k == "rng_state":
                w.rng = np.random.default_rng()
                w.rng.bit_generator.state = v
            elif k in arrays:
                setattr(
                    w,
                    k,
                    np.array(v, dtype=int if k in ints else float).reshape(
                        (-1, 2)
                        if k == "pos"
                        else (-1, GENES)
                        if k == "genes"
                        else np.array(v).shape
                    ),
                )
            else:
                setattr(w, k, copy.deepcopy(v))
        return w

    def clone(self):
        return self.restore(self.snapshot())

    def digest(self):
        state = self.snapshot()
        state.pop("controller_trace", None)
        return hashlib.sha256(
            json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def public(self):
        return {
            "size": SIZE,
            "tick": self.tick,
            "terrain": self.terrain.round(3).tolist(),
            "food": self.food.round(3).tolist(),
            "organisms": [
                {
                    "id": int(self.ids[i]),
                    "parent": int(self.parent[i]),
                    "x": int(p[0]),
                    "y": int(p[1]),
                    "energy": round(float(self.energy[i]), 2),
                    "age": int(self.age[i]),
                    "generation": int(self.generation[i]),
                    "lineage": int(self.lineage[i]),
                }
                for i, p in enumerate(self.pos)
            ],
            "metrics": self.metrics(),
            "history": self.history,
            "laws": self.laws,
        }
