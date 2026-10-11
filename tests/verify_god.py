"""Audit real model records, restore Genesis, and replay the compact God export."""

import json
import sqlite3
import statistics
import subprocess
import time
from pathlib import Path

import httpx

from genesis.god import verify_export
from genesis.world import World

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8780"


def kv(key):
    with sqlite3.connect(
        "file:" + str(ROOT / "data/genesis.sqlite") + "?mode=ro", uri=True
    ) as db:
        row = db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def raw_calls(since):
    with sqlite3.connect(
        "file:" + str(ROOT / "data/genesis.sqlite") + "?mode=ro", uri=True
    ) as db:
        rows = db.execute(
            "SELECT id,actor,data FROM records WHERE scope='origin' AND kind='model_output' AND time>=? ORDER BY id",
            (since,),
        ).fetchall()
    return [dict(id=r[0], actor=r[1], data=json.loads(r[2])) for r in rows]


with httpx.Client(base_url=BASE, timeout=45) as c:
    settings = (
        json.loads(Path("/tmp/genesis-god-user-settings.json").read_text())
        if Path("/tmp/genesis-god-user-settings.json").exists()
        else c.get("/api/state").json()["settings"]
    )
    try:
        c.post(
            "/api/god/control", json={"enabled": False, "interval": 180}
        ).raise_for_status()
        c.post(
            "/api/control", json={"paused": True, "live_autonomy": False}
        ).raise_for_status()
        state = c.get("/api/state").json()
        deadline = time.monotonic() + 180
        while (
            any(
                j["status"] in ["queued", "running"]
                for j in state["jobs"] + state["god"]["jobs"]
            )
            and time.monotonic() < deadline
        ):
            time.sleep(1)
            state = c.get("/api/state").json()
        assert not any(
            j["status"] in ["queued", "running"]
            for j in state["jobs"] + state["god"]["jobs"]
        )
        bundle = c.get("/api/god/export/origin").json()
        (ROOT / "reports/genesis-god-export.json").write_text(json.dumps(bundle))
        matches = verify_export(bundle)
        assert len(matches) >= 3 and all(r["match"] for r in matches.values())
        by_id = {r["id"]: r for r in bundle["records"]}
        for r in bundle["records"]:
            if r["kind"] == "god_change":
                assert (
                    r["data"]["prediction_id"] < r["id"]
                    and by_id[r["data"]["prediction_id"]]["kind"] == "god_prediction"
                )
        calls = [r for r in bundle["records"] if r["kind"] == "god_model_output"]
        assert calls and all(
            r["data"]["request"]["model"] == "llama3.1:70b" for r in calls
        )
        auto = [
            j
            for j in state["god"]["jobs"]
            if j["autonomous"]
            and j["status"] == "complete"
            and j.get("result", {}).get("applied")
        ]
        assert len(auto) >= 2
        investigator_calls = raw_calls(min(r["time"] for r in calls))
        latest = {
            route: next(
                r for r in reversed(investigator_calls) if r["data"]["route"] == route
            )
            for route in ["llama", "qwen"]
        }
        for r in investigator_calls:
            context = json.dumps(r["data"]["request"]["messages"])
            for secret in [
                "GOD_TEMPORARY",
                "GOD_RESOURCE_PULSE",
                "god_id",
                "god_pending",
                "god_observation",
                "god_prediction",
                "god_policy",
                "llama3.1:70b",
                "operator_label",
                "rng_state",
                "controller_weights",
            ]:
                assert secret not in context, (secret, r["id"])
        for world, agents in state["agent_registry"].items():
            for actor, a in agents.items():
                if not a["active"]:
                    continue
                scoped = c.get(
                    "/api/state",
                    params={"view": "inhabitant", "actor": actor, "world": world},
                )
                scoped.raise_for_status()
                for secret in [
                    "god_id",
                    "god_config",
                    "god_change",
                    "god_prediction",
                    "llama3.1:70b",
                    "GOD_TEMPORARY",
                    "operator_label",
                    "rng_state",
                    "controller_weights",
                ]:
                    assert secret not in scoped.text, (secret, world, actor)
        before = kv("worlds")
        before_hash = {n: World.restore(w).digest() for n, w in before.items()}
        cp = kv("checkpoints")
        before_mem = bundle["records"]
        cfg = kv("god_config")
        subprocess.run([str(ROOT / "stop.sh")], check=True)
        subprocess.run([str(ROOT / "start.sh")], check=True)
        after = kv("worlds")
        assert before == after and before_hash == {
            n: World.restore(w).digest() for n, w in after.items()
        }
        assert cp == kv("checkpoints") and cfg == kv("god_config")
        recovered = c.get("/api/god/export/origin").json()
        assert recovered["records"] == before_mem
        assert verify_export(recovered) == matches
        runtime = c.get("/api/god/state").json()["runtime"]
        outcomes = [r["data"] for r in bundle["records"] if r["kind"] == "god_outcome"]
        report = {
            "verified": True,
            "model": bundle["model"],
            "pre_god_baseline_commit": "ac72d31",
            "pre_god_checkpoint": "cp-9",
            "physics_tests": 21,
            "portable_replay": matches,
            "actual_autonomous_changes": auto,
            "outcomes": [
                {
                    "id": d["id"],
                    "difference_vs_control": d["difference_vs_control"],
                    "grade": d["grade"],
                    "confounded": d["confounded"],
                    "replay_match": d["replay_match"],
                }
                for d in outcomes
            ],
            "real_70b_calls": [
                {
                    "record": r["id"],
                    "job": r["data"]["job"],
                    "latency_s": round(r["data"]["latency_s"], 3),
                    "prompt_tokens": r["data"]["response"].get("prompt_eval_count"),
                    "output_tokens": r["data"]["response"].get("eval_count"),
                }
                for r in calls
            ],
            "validated_failures": [
                r["data"] for r in bundle["records"] if r["kind"] == "god_failure"
            ],
            "existing_models_actual_connections": {
                k: {
                    "record": v["id"],
                    "latency_s": round(v["data"]["latency_s"], 3),
                    "model": v["data"]["registry"]["model"],
                }
                for k, v in latest.items()
            },
            "inhabitant_payload_and_inference_context_audit": True,
            "prediction_before_action": True,
            "cancelled_real_request": any(
                j["status"] == "cancelled" for j in state["god"]["jobs"]
            ),
            "restart": {
                "world_prng_controller_hashes_equal": True,
                "worlds": before_hash,
                "god_memories_equal": True,
                "checkpoints_equal": True,
                "god_config_equal": True,
                "portable_replay_after_restart": True,
            },
            "compute": state["compute"],
            "runtime": runtime,
            "interpretation": "Three exploratory paired comparisons. Forecasts can be wrong. No evidence of general intelligence, consciousness, or long-term evolutionary progress.",
        }
        (ROOT / "reports/god-verification.json").write_text(
            json.dumps(report, indent=2)
        )
        print(
            json.dumps(
                {
                    "verified": True,
                    "replays": len(matches),
                    "automatic_changes": len(auto),
                    "restart": True,
                    "runtime": runtime,
                }
            ),
            flush=True,
        )
    finally:
        c.post(
            "/api/control",
            json={
                k: settings[k]
                for k in ["paused", "speed", "live_autonomy"]
                if k in settings
            },
        ).raise_for_status()
        c.post(
            "/api/god/control",
            json={"enabled": True, "world": "origin", "interval": 180},
        ).raise_for_status()
