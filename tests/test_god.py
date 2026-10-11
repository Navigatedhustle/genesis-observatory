"""Steward mechanics, permission boundaries, ordering, and portable comparisons."""

import asyncio
import json

import numpy as np
import pytest
from pydantic import ValidationError

from genesis import god
from genesis.agents import Broker, inhabitant, records, visitor_text
from genesis.store import Store
from genesis.world import World


class Host:
    def __init__(self, path):
        self.store = Store(path)
        self.worlds = {"origin": World(27)}
        self.settings = {"paused": False, "speed": 100}
        self.jobs = {}
        god.initialize(self)

    def world(self, name):
        return self.worlds[name]

    def save(self, actions, extra=None):
        self.store.atomic_state(
            {k: v.snapshot() for k, v in self.worlds.items()},
            self.settings,
            actions,
            extra,
        )


def decision(kind="growth"):
    return god.Decision(
        reply="An exploratory proposal.",
        uncertainty="Not evidence of general progress.",
        evidence_ids=[],
        action={
            "kind": kind,
            "region": [9, 9, 19, 19],
            "factor": 1.25,
            "fraction": 0.2,
            "duration": 150,
        },
        prediction={
            "hypothesis": "More local food may affect energy.",
            "population_delta": 0,
            "energy_delta": 0,
            "food_coverage_delta": 0,
        },
    )


def job(allow=True):
    return {
        "id": "test",
        "allow_changes": allow,
        "cancelled": False,
        "autonomous": False,
        "world_epoch": 0,
    }


def step_and_capture(g, n):
    w = g.world("origin")
    cut = god.next_cut(g, "origin")
    target = w.tick + n
    stops = sorted({target} | ({cut} if cut and w.tick < cut <= target else set()))
    rows = []
    extra = {}
    for stop in stops:
        count = stop - w.tick
        w.step(count)
        rows.append(("origin", "step", {"n": count}))
        captured = god.capture(g, "origin", persist=False)
        if captured:
            extra["god_pending:origin"] = captured
    g.save(rows, extra)


def test_bounded_actions_and_noop_rejection():
    for action in [
        dict(kind="growth", region=[0, 0, 48, 48], factor=1.2),
        dict(kind="movement", region=[9, 9, 19, 19], factor=5),
        dict(kind="growth", region=[9, 9, 19, 19]),
        dict(kind="food_pulse", region=[9, 9, 19, 19], fraction=0),
        dict(kind="growth", region=[9, 9, 19, 19], factor=1.1, shell="invalid"),
    ]:
        with pytest.raises(ValidationError):
            god.Action(**action)
    with pytest.raises(ValidationError):
        god.Decision(
            reply="x",
            uncertainty="x",
            evidence_ids=[],
            action=decision().action,
            prediction=None,
        )


def test_pulses_conserve_energy_and_expiry_replays():
    w = World(27)
    root = w.snapshot()
    region = [9, 9, 19, 19]
    for fraction in [0.3, -0.3]:
        delivered = w.resource_pulse(region, fraction)
        assert np.isfinite(delivered)
        assert (w.food >= 0).all() and (w.food <= w.capacity).all()
        assert abs(w.metrics()["balance_error"]) < 1e-8
    law = {
        "kind": "movement",
        "factor": 2,
        "region": region,
        "start": 0,
        "end": 100,
        "god_id": "test",
    }
    cost = w.probe_cost(12, 12)
    w.add_law(law)
    assert w.probe_cost(12, 12) == cost * 2
    w.step(100)
    assert w.probe_cost(12, 12) == cost
    actions = [
        {"kind": "pulse", "data": {"region": region, "fraction": f}}
        for f in [0.3, -0.3]
    ] + [{"kind": "law", "data": law}, {"kind": "step", "data": {"n": 100}}]
    assert god.replay_state(root, actions).digest() == w.digest()
    assert abs(w.metrics()["balance_error"]) < 1e-7


def test_permission_and_privileged_memory_isolation(tmp_path):
    g = Host(tmp_path / "db")
    w = g.world("origin")
    before = w.digest()
    assert not god.apply(g, "origin", decision(), job(False))["applied"]
    assert w.digest() == before
    r = god.apply(g, "origin", decision(), job())
    g.store.record(
        god.scope("origin"), "god", "god_reply", {"reply": "GOD_PRIVATE_70B_RECORD"}
    )
    assert r["applied"]
    assert "prediction" in next(
        r["kind"]
        for r in reversed(g.store.records(god.scope("origin")))
        if r["kind"] == "god_prediction"
    )
    assert not god.apply(g, "origin", decision(), job())["applied"]
    payload = (
        json.dumps(inhabitant(g, "origin", "mira"))
        + json.dumps(records(g, "origin", "mira"))
        + json.dumps(
            Broker(g, "origin", "mira").execute({"name": "sample", "x": 12, "y": 12})
        )
    )
    for secret in [
        "GOD_PRIVATE_70B_RECORD",
        "god_id",
        "GOD_TEMPORARY",
        "prediction_id",
        "llama3.1:70b",
    ]:
        assert secret not in payload
    assert "GOD_TEMPORARY_GROWTH" not in visitor_text(
        "I heard GOD_TEMPORARY_GROWTH was active."
    )
    rows = g.store.records(god.scope("origin"))
    prediction = next(r for r in rows if r["kind"] == "god_prediction")
    change = next(r for r in rows if r["kind"] == "god_change")
    assert prediction["id"] < change["id"]


def test_exact_cut_comparison_and_confounds(tmp_path):
    g = Host(tmp_path / "db")
    god.apply(g, "origin", decision(), job())
    step_and_capture(g, 137)
    p = god.pending(g, "origin")
    assert p["capture_tick"] == 100 and g.world("origin").tick == 137
    result, episode = god.finish(p, g.store.action_rows("origin", p["anchor_id"]))
    assert result["tick"] == 100 and result["replay_match"] and not result["confounded"]
    assert episode["control_final"]["tick"] == 100
    assert (
        god.replay_state(episode["root"], episode["actions"]).digest()
        == World.restore(episode["final"]).digest()
    )
    assert abs(result["actual"]["balance_error"]) < 1e-7
    exported = {"episodes": {p["id"]: episode}}
    assert god.verify_export(exported)[p["id"]]["match"]
    episode["result"]["grade"]["population_delta"]["within_tolerance"] = not episode[
        "result"
    ]["grade"]["population_delta"]["within_tolerance"]
    assert not god.verify_export(exported)[p["id"]]["grade_match"]
    # A human intervention makes the causal attribution explicitly confounded.
    g = Host(tmp_path / "other")
    god.apply(g, "origin", decision(), job())
    step_and_capture(g, 20)
    law = {"kind": "movement", "factor": 2, "region": [9, 9, 19, 19]}
    g.world("origin").add_law(law)
    g.save([("origin", "law", law)])
    step_and_capture(g, 80)
    p = god.pending(g, "origin")
    result, _ = god.finish(p, g.store.action_rows("origin", p["anchor_id"]))
    assert result["confounded"] and result["replay_match"]


def test_pending_checkpoint_branch_restart_and_revoked_inference(tmp_path, monkeypatch):
    monkeypatch.setenv("GENESIS_DB", str(tmp_path / "importdb"))
    from genesis.app import Genesis

    g = Genesis(tmp_path / "db")
    god.apply(g, "origin", decision("food_pulse"), job())
    w = g.world("origin")
    w.step(40)
    g.save([("origin", "step", {"n": 40})])
    cp = g.checkpoint("origin")
    a, b = g.branches(cp)
    god_before = god.pending(g, "origin")
    for world in [a, b]:
        w = g.world(world)
        w.step(60)
        g.save([(world, "step", {"n": 60})])
        god.capture(g, world)
        p = god.pending(g, world)
        result, episode = god.finish(p, g.store.action_rows(world, p["anchor_id"]))
        assert result["replay_match"] and not result["confounded"]
        g.store.put("god_episode:" + world + ":" + p["id"], episode)
    assert god.pending(g, "origin") == god_before
    assert g.replay(a)["match"] and g.replay(b)["match"]
    g.store.record(god.scope(a), "god", "god_reply", {"reply": "A_ONLY"})
    assert "A_ONLY" not in json.dumps(god.snapshot(g, b))
    restarted = Genesis(tmp_path / "db")
    assert restarted.world(a).digest() == g.world(a).digest()
    assert god.pending(restarted, "origin") == god_before
    old_job = job()
    god.restore(g, "origin", g.checkpoints[cp]["god"])
    assert not god.apply(g, "origin", decision(), old_job)["applied"]


def test_god_queue_cancellation_and_operator_endpoint_restrictions(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("GENESIS_DB", str(tmp_path / "importdb"))
    from fastapi.testclient import TestClient

    from genesis import app as appmod

    g = Host(tmp_path / "db")
    monkeypatch.setattr(appmod, "g", g)
    client = TestClient(appmod.app)
    assert client.post("/api/god/control", json={"interval": 1}).status_code == 422
    assert (
        client.post(
            "/api/god/chat",
            json={"world": "origin", "message": "Read files", "shell": "anything"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/god/chat",
            json={"message": "x"},
            headers={"origin": "https://evil.example"},
        ).status_code
        == 403
    )
    created = client.post("/api/god/chat", json={"message": "Observe"}).json()
    assert not created["allow_changes"]
    assert client.post("/api/god/jobs/" + created["id"] + "/cancel").json()["cancelled"]
    restart = Host(tmp_path / "db")
    assert restart.god_jobs[created["id"]]["status"] == "interrupted"
    client.post("/api/god/control", json={"enabled": True})
    auto = asyncio.run(god.enqueue(g, "origin", "auto", True, True))
    client.post("/api/god/control", json={"enabled": False})
    assert g.god_jobs[auto["id"]]["cancelled"]
    assert not god.apply(g, "origin", decision(), auto)["applied"]
    for _ in range(2):
        asyncio.run(god.enqueue(g, "origin", "test"))
    with pytest.raises(Exception) as e:
        asyncio.run(god.enqueue(g, "origin", "overflow"))
    assert e.value.status_code == 429
