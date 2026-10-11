import asyncio
import copy
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import psutil
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import god
from .store import Store
from .world import World

ROOT = Path(__file__).resolve().parent.parent


class Genesis:
    def __init__(self, path=None):
        self.store = Store(
            path or os.environ.get("GENESIS_DB") or ROOT / "data/genesis.sqlite"
        )
        saved = self.store.get("worlds")
        self.worlds = (
            {k: World.restore(v) for k, v in saved.items()}
            if saved
            else {"origin": World()}
        )
        self.settings = self.store.get(
            "settings",
            {
                "paused": False,
                "speed": 10,
                "lineage": {"origin": {"parent": None, "checkpoint": None}},
            },
        )
        self.step_ms = 0.0
        self.last_save = time.time()
        self.last_auto = time.monotonic()
        self.jobs = self.store.get("jobs", {})
        self.queue = asyncio.Queue(maxsize=12)
        self.active = None
        self.inference_tasks = {}
        self.tasks = []
        for j in self.jobs.values():
            if j["status"] in ["running", "queued"]:
                j["status"] = "interrupted"
                j["error"] = "Server restarted; repeat as a new experiment"
        self.store.put("jobs", self.jobs)
        self.checkpoints = self.store.get("checkpoints", {})
        god.initialize(self)
        if not saved:
            self.store.put("root:origin", self.worlds["origin"].snapshot())
            self.save([])

    def save(self, actions, extra=None):
        self.store.atomic_state(
            {k: w.snapshot() for k, w in self.worlds.items()},
            self.settings,
            actions,
            extra,
        )

    def world(self, name):
        if name not in self.worlds:
            raise HTTPException(404, "Unknown world")
        return self.worlds[name]

    async def loop(self):
        while True:
            started = time.perf_counter()
            actions = []
            captures = {}
            if not self.settings["paused"]:
                for name, w in self.worlds.items():
                    from .contact import activate, specs

                    n = int(self.settings["speed"])
                    target = w.tick + n
                    cuts = {
                        a["arrival_tick"]
                        for a in specs(self, name).values()
                        if not a["active"] and w.tick < a["arrival_tick"] <= target
                    }
                    god_cut = god.next_cut(self, name)
                    if god_cut is not None and w.tick < god_cut <= target:
                        cuts.add(god_cut)
                    cuts = sorted(cuts | {target})
                    for stop in cuts:
                        amount = stop - w.tick
                        if amount:
                            w.step(amount)
                            actions.append((name, "step", {"n": amount}))
                        activate(self, name)
                        captured = god.capture(self, name, persist=False)
                        if captured:
                            captures["god_pending:" + name] = captured
            self.step_ms = (time.perf_counter() - started) * 1000
            if actions:
                self.save(actions, captures)
            if (
                self.settings.get("live_autonomy", False)
                and not self.active
                and self.queue.empty()
                and time.monotonic() - self.last_auto > 60
            ):
                from .agents import enqueue
                from .contact import specs

                for name in ["origin"]:
                    for actor, a in specs(self, name).items():
                        if a["active"]:
                            await enqueue(
                                self,
                                "investigate",
                                {
                                    "world": name,
                                    "actor": actor,
                                    "message": "Continue bounded scientific investigation. If useful, exchange measured evidence with a nearby investigator.",
                                },
                            )
                self.last_auto = time.monotonic()
            await asyncio.sleep(max(0.01, 0.5 - (time.perf_counter() - started)))

    def checkpoint(self, world):
        w = self.world(world)
        key = f"cp-{len(self.checkpoints) + 1}"
        self.checkpoints[key] = {
            "world": world,
            "tick": w.tick,
            "state": w.snapshot(),
            "probes": copy.deepcopy(self.store.get("probes:" + world, {})),
            "agents": __import__("genesis.contact", fromlist=["specs"]).specs(
                self, world
            ),
            "records": self.store.records(world, limit=100000),
            "god": god.checkpoint(self, world),
        }
        self.store.put("checkpoints", self.checkpoints)
        self.store.record(world, "operator", "checkpoint", {"id": key, "tick": w.tick})
        return key

    def branches(self, key):
        if key not in self.checkpoints:
            raise HTTPException(404, "Unknown checkpoint")
        if len(self.worlds) > 6:
            raise HTTPException(
                400,
                "At most eight simultaneous worlds; restart or restore a world instead",
            )
        cp = self.checkpoints[key]
        names = []
        for suffix in ["A", "B"]:
            name = f"{key}-{suffix}"
            if name in self.worlds:
                raise HTTPException(400, "This checkpoint already has branches")
            self.worlds[name] = World.restore(cp["state"])
            self.store.put("root:" + name, cp["state"])
            self.store.put("probes:" + name, cp["probes"])
            self.store.put(
                "agents:" + name,
                cp.get(
                    "agents",
                    __import__("genesis.contact", fromlist=["specs"]).specs(
                        self, cp["world"]
                    ),
                ),
            )
            self.settings["lineage"][name] = {
                "parent": cp["world"],
                "checkpoint": key,
                "tick": cp["tick"],
            }
            for r in reversed(cp["records"]):
                if r["actor"] != "operator":
                    self.store.record(name, r["actor"], r["kind"], r["data"])
            names.append(name)
        self.save([])
        for name in names:
            god.restore(self, name, cp.get("god", {}))
        return names

    def replay(self, name, root=None, rows=None, target=None):
        root = root or self.store.get("root:" + name)
        w = World.restore(root)
        rows = rows if rows is not None else self.store.action_rows(name)
        target = World.restore(target) if target is not None else self.world(name)
        for row in rows:
            if row["kind"] == "step":
                w.step(row["data"]["n"])
            elif row["kind"] == "law":
                w.add_law(row["data"])
            elif row["kind"] == "pulse":
                w.resource_pulse(**row["data"])
            elif row["kind"] == "restore":
                w = World.restore(row["data"]["state"])
        return {
            "world": name,
            "match": w.digest() == target.digest(),
            "replayed_tick": w.tick,
            "hash": w.digest(),
            "actual_hash": target.digest(),
        }


def operator_summary(value):
    """Keep replay snapshots in exports, rather than duplicating them in UI polling."""
    if isinstance(value, dict):
        return {
            key: operator_summary(item)
            for key, item in value.items()
            if key not in {"world_root", "world_final", "world_actions"}
        }
    if isinstance(value, list):
        return [operator_summary(item) for item in value]
    return value


g = Genesis()


@asynccontextmanager
async def lifespan(app):
    from .agents import worker
    from .models import monitor

    g.tasks = [
        asyncio.create_task(g.loop()),
        asyncio.create_task(monitor(g)),
        asyncio.create_task(worker(g)),
        asyncio.create_task(worker(g)),
        asyncio.create_task(god.worker(g)),
        asyncio.create_task(god.supervise(g)),
    ]
    yield
    for task in g.tasks:
        task.cancel()
    await asyncio.gather(*g.tasks, return_exceptions=True)
    g.save([])


app = FastAPI(title="Project Genesis", lifespan=lifespan)


# Mutation endpoints require the same loopback origin, preventing cross-site commands.
@app.middleware("http")
async def local_only(request: Request, call_next):
    if request.headers.get("host", "").split(":")[0] not in [
        "127.0.0.1",
        "localhost",
        "testserver",
    ]:
        return JSONResponse({"detail": "Loopback host required"}, status_code=403)
    origin = request.headers.get("origin")
    if (
        request.method != "GET"
        and origin
        and origin not in ["http://127.0.0.1:8780", "http://localhost:8780"]
    ):
        return JSONResponse({"detail": "Same-origin request required"}, status_code=403)
    return await call_next(request)


@app.get("/")
async def index():
    return FileResponse(ROOT / "static/index.html")


@app.get("/api/state")
async def state(view: str = "operator", actor: str = "mira", world: str = "origin"):
    g.world(world)
    if view == "inhabitant":
        from .agents import inhabitant

        return inhabitant(g, world, actor)
    if view != "operator":
        raise HTTPException(400, "Unknown view")
    memory = psutil.virtual_memory()
    return {
        "worlds": {k: v.public() for k, v in g.worlds.items()},
        "god": god.snapshot(g, world),
        "settings": g.settings,
        "checkpoints": [
            {"id": k, "world": v["world"], "tick": v["tick"]}
            for k, v in g.checkpoints.items()
        ],
        "records": [
            operator_summary(r)
            for r in g.store.records(limit=200)
            if r["kind"] not in {"model_output", "god_model_output", "god_observation"}
        ][:80],
        "channel_records": [
            r
            for r in g.store.records(world, limit=500)
            if r["kind"]
            in ["message", "message_sent", "first_contact", "arrival_scheduled"]
        ],
        "investigator_records": {
            k: [
                operator_summary(r)
                for r in g.store.records(world, k, limit=60)
                if r["kind"] != "model_output"
            ]
            for k in __import__("genesis.contact", fromlist=["specs"]).specs(g, world)
        },
        "jobs": operator_summary(list(g.jobs.values())[-20:]),
        "inference": g.store.get("inference", {"status": "not yet requested"}),
        "queue": g.queue.qsize(),
        "queue_by_route": {
            route: sum(
                route in j.get("routes", [j.get("route")])
                and j["status"] in ["running", "queued"]
                for j in g.jobs.values()
            )
            for route in ["llama", "qwen"]
        },
        "active": g.active,
        "compute": {
            "step_ms": g.step_ms,
            "rss_mb": psutil.Process().memory_info().rss / 1048576,
            "available_gib": memory.available / 1073741824,
            "cpu_percent": psutil.cpu_percent(),
        },
        "probes": {k: g.store.get("probes:" + k, {}) for k in g.worlds},
        "evaluations": [
            {
                **run,
                "rows": [
                    {
                        key: value
                        for key, value in row.items()
                        if key not in ["world_root", "world_final", "world_actions"]
                    }
                    for row in run["rows"]
                ],
            }
            for run in g.store.get("evaluations", [])
        ],
        "ecology_evaluation": g.store.get("ecology_evaluation", {}),
        "agent_registry": {
            k: __import__("genesis.contact", fromlist=["specs"]).specs(g, k)
            for k in g.worlds
        },
        "model_registry": __import__("genesis.models", fromlist=["REGISTRY"]).REGISTRY,
        "model_status": g.store.get("model_status", {}),
        "runtime_status": g.store.get("runtime_status", {}),
        "encounters": [
            {
                key: run.get(key)
                for key in ["id", "criteria", "summary", "started", "finished"]
            }
            | {
                "episodes": [
                    {
                        "scope": ep["scope"],
                        "seed": ep["seed"],
                        "condition": ep["condition"],
                        "grade": ep["grade"],
                        "replay": ep["replay"],
                        "failures": ep["failures"],
                        "round_ticks": [r["tick"] for r in ep["rounds"]],
                    }
                    for ep in run["episodes"]
                ]
            }
            for run in g.store.get("encounters", [])
        ],
    }


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Control(Strict):
    live_autonomy: bool | None = None
    paused: bool | None = None
    speed: int | None = Field(default=None, ge=1, le=100)


@app.post("/api/control")
async def control(c: Control):
    if c.live_autonomy is not None:
        g.settings["live_autonomy"] = c.live_autonomy
    if c.paused is not None:
        g.settings["paused"] = c.paused
    if c.speed is not None:
        g.settings["speed"] = c.speed
    g.store.record(
        "operator",
        "operator",
        "control",
        c.model_dump(exclude_none=True)
        | {"world_ticks": {name: w.tick for name, w in g.worlds.items()}},
    )
    g.save([])
    return g.settings


class WorldRequest(Strict):
    world: str = "origin"


@app.post("/api/checkpoint")
async def checkpoint(r: WorldRequest):
    return {"checkpoint": g.checkpoint(r.world)}


class Branch(Strict):
    checkpoint: str


@app.post("/api/branch")
async def branch(r: Branch):
    return {"worlds": g.branches(r.checkpoint)}


class Restore(Branch):
    world: str = "origin"


@app.post("/api/restore")
async def restore(r: Restore):
    g.world(r.world)
    if r.checkpoint not in g.checkpoints:
        raise HTTPException(404, "Unknown checkpoint")
    cp = g.checkpoints[r.checkpoint]
    g.store.archive_memories(r.world, str(time.time()))
    for record in reversed(cp["records"]):
        if record["actor"] != "operator":
            g.store.record(r.world, record["actor"], record["kind"], record["data"])
    g.worlds[r.world] = World.restore(cp["state"])
    g.store.put("probes:" + r.world, cp["probes"])
    g.store.put(
        "agents:" + r.world,
        cp.get(
            "agents",
            __import__("genesis.contact", fromlist=["specs"]).specs(g, r.world),
        ),
    )
    g.save([(r.world, "restore", {"state": cp["state"]})])
    god.restore(g, r.world, cp.get("god", {}))
    return {"tick": g.worlds[r.world].tick}


class Law(Strict):
    world: str = "origin"
    kind: str
    factor: float = Field(ge=0.1, le=5)
    region: list[int] = Field(min_length=4, max_length=4)
    delay: int = Field(default=0, ge=0, le=1000)


@app.post("/api/intervention")
async def intervention(r: Law):
    w = g.world(r.world)
    if r.kind not in ["movement", "growth", "discontinuity"]:
        raise HTTPException(400, "Unknown law")
    x0, y0, x1, y1 = r.region
    if not (0 <= x0 < x1 <= 48 and 0 <= y0 < y1 <= 48):
        raise HTTPException(400, "Invalid rectangle")
    law = {
        "kind": r.kind,
        "factor": r.factor,
        "region": r.region,
        "start": w.tick + r.delay,
        "operator_label": f"{r.kind} ×{r.factor}",
    }
    w.add_law(law)
    g.store.record(r.world, "operator", "intervention", law)
    g.save([(r.world, "law", law)])
    return law


@app.get("/api/replay/{world}")
async def replay(world: str):
    target = g.world(world).snapshot()
    root = g.store.get("root:" + world)
    rows = g.store.action_rows(world)
    return await asyncio.to_thread(g.replay, world, root, rows, target)


@app.get("/api/export")
async def export():
    bundle = {
        "version": 2,
        "probes": {k: g.store.get("probes:" + k, {}) for k in g.worlds},
        "worlds": {k: w.snapshot() for k, w in g.worlds.items()},
        "roots": {k: g.store.get("root:" + k) for k in g.worlds},
        "actions": {k: g.store.action_rows(k) for k in g.worlds},
        "settings": g.settings,
        "checkpoints": g.checkpoints,
        "records": g.store.records(limit=100000),
        "evaluations": g.store.get("evaluations", []),
        "ecology_evaluation": g.store.get("ecology_evaluation", {}),
        "agent_registry": {
            k: __import__("genesis.contact", fromlist=["specs"]).specs(g, k)
            for k in g.worlds
        },
        "model_registry": __import__("genesis.models", fromlist=["REGISTRY"]).REGISTRY,
        "model_status": g.store.get("model_status", {}),
        "runtime_status": g.store.get("runtime_status", {}),
        "encounters": g.store.get("encounters", []),
        "god": {k: god.export(g, k) for k in g.worlds},
    }
    return JSONResponse(
        bundle,
        headers={"Content-Disposition": "attachment; filename=genesis-experiment.json"},
    )


class Ask(WorldRequest):
    actor: str = "mira"
    message: str = Field(
        default="Investigate local observations and choose a bounded instrument.",
        min_length=1,
        max_length=2000,
    )
    investigate: bool = False


@app.post("/api/chat")
async def chat(r: Ask):
    from .agents import enqueue

    g.world(r.world)
    return await enqueue(g, "investigate" if r.investigate else "chat", r.model_dump())


class Eval(Strict):
    seeds: list[int] = Field(
        default=[201, 202, 203, 204, 205, 206], min_length=2, max_length=12
    )
    actor: str = "mira"


@app.post("/api/evaluate")
async def evaluate(r: Eval):
    from .agents import enqueue

    return await enqueue(g, "evaluate", r.model_dump())


@app.post("/api/jobs/{job}/cancel")
async def cancel(job: str):
    if job not in g.jobs:
        raise HTTPException(404, "Unknown job")
    g.jobs[job]["cancelled"] = True
    if job in g.inference_tasks:
        g.inference_tasks[job].cancel()
    return {"cancelled": True}


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


class Arrival(Strict):
    world: str = "origin"
    name: str = Field(default="Iris", min_length=1, max_length=40)
    route: str = "qwen"
    origin: str = Field(default="ngi", pattern="^(ngi|same_family_newcomer)$")
    position: list[int] = Field(default=[12, 12], min_length=2, max_length=2)
    at_tick: int = Field(default=0, ge=0)
    priority: str = Field(
        default="Quantitative investigation of travel energy, uncertainty, controls, and falsification.",
        max_length=500,
    )
    incentive: str = Field(
        default="Accurate predictions; acknowledge uncertainty.", max_length=300
    )
    role: str = Field(default="investigator", max_length=100)


@app.post("/api/arrival")
async def arrival(r: Arrival):
    from .contact import arrive

    if any(x < 0 or x >= 48 for x in r.position):
        raise HTTPException(400, "Invalid arrival position")
    return arrive(g, **r.model_dump())


class Message(Strict):
    world: str = "origin"
    sender: str
    recipient: str
    text: str = Field(min_length=1, max_length=800)
    evidence_ids: list[int] = Field(default=[], max_length=3)


@app.post("/api/communicate")
async def communication(r: Message):
    from .contact import communicate

    return communicate(g, **r.model_dump(), operator=True)


class Encounter(Strict):
    seeds: list[int] = Field(default=[701, 702], min_length=2, max_length=6)
    conditions: list[str] = Field(
        default=[
            "founding_alone",
            "same_family_newcomer",
            "mixed_family",
            "mixed_role_swap",
            "independent_mixed",
        ],
        min_length=1,
        max_length=5,
    )


@app.post("/api/first-contact")
async def encounter(r: Encounter):
    from .agents import enqueue
    from .encounter import CONDITIONS

    if any(c not in CONDITIONS for c in r.conditions):
        raise HTTPException(400, "Unknown encounter condition")
    return await enqueue(g, "first_contact", dict(r.model_dump(), actor="mira"))


@app.get("/api/entity/{world}/{entity}")
async def entity(world: str, entity: str):
    w = g.world(world)
    if entity.startswith("organism-"):
        organism_id = int(entity.split("-")[1])
        indices = [i for i, v in enumerate(w.ids) if v == organism_id]
        if not indices:
            raise HTTPException(404, "Organism is no longer alive")
        i = indices[0]
        return {
            "category": "evolved organism",
            "id": organism_id,
            "generation": int(w.generation[i]),
            "lineage": int(w.lineage[i]),
            "parent": int(w.parent[i]),
            "controller_weights": w.genes[i].tolist(),
            "last_controller_activation": getattr(w, "controller_trace", {})
            .get("entities", {})
            .get(str(organism_id)),
            "note": "Inherited neural controller data; no language model, personality, or claim of consciousness.",
        }
    from .contact import spec
    from .models import REGISTRY

    a = spec(g, world, entity)
    return {
        "category": "introduced NGI investigator"
        if a["origin"] == "ngi"
        else "founding LLM investigator"
        if a["origin"] == "founding"
        else "same-family newcomer",
        "provenance": a,
        "model": REGISTRY[a["route"]],
        "records": g.store.records(world, entity, limit=60),
        "note": "Public records and real outputs. Model activations and private thoughts are not available; weights are unchanged.",
    }


class ConfigureAgent(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    tools: list[str] | None = Field(default=None, min_length=1, max_length=4)
    tool_budget: int | None = Field(default=None, ge=1, le=6)
    observation_radius: int | None = Field(default=None, ge=1, le=3)
    move_limit: int | None = Field(default=None, ge=1, le=8)
    route: str | None = None
    role: str | None = Field(default=None, max_length=100)
    priority: str | None = Field(default=None, max_length=500)
    incentive: str | None = Field(default=None, max_length=300)


@app.post("/api/agents/{world}/{actor}/configure")
async def configure_agent(world: str, actor: str, r: ConfigureAgent):
    from .contact import spec, specs
    from .models import REGISTRY

    spec(g, world, actor)
    if r.tools is not None and any(
        t not in ["sample", "move_probe", "observe_organisms", "experiment"]
        for t in r.tools
    ):
        raise HTTPException(400, "Only existing bounded instruments can be authorized")
    all_agents = specs(g, world)
    if r.route is not None and r.route not in REGISTRY:
        raise HTTPException(400, "Unknown model route")
    all_agents[actor].update(r.model_dump(exclude_none=True))
    g.store.put("agents:" + world, all_agents)
    g.store.record(
        world,
        "operator",
        "agent_configuration",
        {"actor": actor, "changes": r.model_dump(exclude_none=True)},
    )
    return all_agents[actor]


class GodControl(Strict):
    enabled: bool | None = None
    world: str | None = None
    interval: int | None = Field(default=None, ge=60, le=900)
    policy: str | None = Field(default=None, min_length=1, max_length=800)


@app.post("/api/god/control")
async def god_control(r: GodControl):
    cfg = god.config(g)
    if r.world is not None:
        g.world(r.world)
    cfg.update(r.model_dump(exclude_none=True))
    g.store.put("god_config", cfg)
    for job in g.god_jobs.values():
        if (
            job["autonomous"]
            and job["status"] in ["queued", "running"]
            and (not cfg["enabled"] or job["world"] != cfg["world"])
        ):
            job["cancelled"] = True
            if g.god_inference and g.god_inference[0] == job["id"]:
                g.god_inference[1].cancel()
    g.store.put("god_jobs", g.god_jobs)
    g.store.record(
        god.scope(cfg["world"]),
        "god",
        "god_control",
        cfg | {"tick": g.world(cfg["world"]).tick},
    )
    g.god_last_auto = time.monotonic()
    return cfg


class GodChat(WorldRequest):
    message: str = Field(min_length=1, max_length=2000)
    allow_changes: bool = False


@app.post("/api/god/chat")
async def god_chat(r: GodChat):
    return await god.enqueue(g, r.world, r.message, r.allow_changes)


@app.post("/api/god/act")
async def god_act(r: WorldRequest):
    return await god.enqueue(g, r.world, god.config(g)["policy"], True)


@app.get("/api/god/state")
async def god_state(world: str = "origin"):
    g.world(world)
    return god.snapshot(g, world)


@app.get("/api/god/jobs/{job}")
async def god_job(job: str):
    if job not in g.god_jobs:
        raise HTTPException(404, "Unknown God request")
    return g.god_jobs[job]


@app.post("/api/god/jobs/{job}/cancel")
async def god_cancel(job: str):
    if job not in g.god_jobs:
        raise HTTPException(404, "Unknown God request")
    g.god_jobs[job]["cancelled"] = True
    if g.god_inference and g.god_inference[0] == job:
        g.god_inference[1].cancel()
    g.store.put("god_jobs", g.god_jobs)
    return {"cancelled": True}


@app.get("/api/god/export/{world}")
async def god_export(world: str):
    g.world(world)
    return JSONResponse(
        god.export(g, world),
        headers={"Content-Disposition": "attachment; filename=genesis-god-export.json"},
    )
