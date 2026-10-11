import json

import pytest
from fastapi import HTTPException

from genesis.agents import Broker, inhabitant, records
from genesis.contact import activate, arrive, communicate, specs
from genesis.encounter import (
    CONDITIONS,
    CRITERIA,
    assertion,
    correction,
    replay_episode,
)
from genesis.models import REGISTRY, request
from genesis.world import World
from tests.test_genesis import FakeHost


def test_real_distinct_families_and_routes():
    assert REGISTRY["llama"]["family"] != REGISTRY["qwen"]["family"]
    assert REGISTRY["llama"]["endpoint"].startswith("http://127.0.0.1:")
    assert REGISTRY["qwen"]["endpoint"].startswith("http://127.0.0.1:")
    for key in REGISTRY:
        r = request(
            key, [{"role": "user", "content": "visible only"}], {"type": "object"}
        )
        assert r["model"] == REGISTRY[key]["model"]
        assert "visible only" in json.dumps(r["messages"])
        assert all(
            v["context_limit"] == 6144 and v["max_tokens"] == 700
            for v in REGISTRY.values()
        )


def test_arrival_has_no_history_and_exact_tick(tmp_path):
    g = FakeHost(tmp_path / "db")
    g.store.record("origin", "mira", "note", {"hypothesis": "FOUNDER_SECRET"})
    a = arrive(g, "origin", "Nova", "qwen", "ngi", [12, 12], 7)
    assert not specs(g, "origin")[a["id"]]["active"]
    with pytest.raises(HTTPException):
        Broker(g, "origin", a["id"])
    g.worlds["origin"].step(6)
    activate(g, "origin")
    assert not specs(g, "origin")[a["id"]]["active"]
    g.worlds["origin"].step(1)
    activate(g, "origin")
    assert specs(g, "origin")[a["id"]]["active"]
    view = inhabitant(g, "origin", a["id"])
    raw = json.dumps(view)
    for secret in [
        "FOUNDER_SECRET",
        "qwen",
        "llama",
        "model",
        "route",
        "ngi",
        "genes",
        "rng_state",
    ]:
        assert secret not in raw
    assert "arrival_position" in raw
    with pytest.raises(HTTPException):
        arrive(g, "origin", "Fake NGI", "llama", "ngi", [12, 12], 7)


def test_scoped_messages_and_evidence(tmp_path):
    g = FakeHost(tmp_path / "db")
    a = arrive(g, "origin", "Nova", "qwen", "ngi", [13, 12], 0)["id"]
    sample = Broker(g, "origin", "mira").execute({"name": "sample", "x": 12, "y": 12})
    evidence = g.store.records("origin", "mira")[0]["id"]
    before = records(g, "origin", a)
    assert not any(r["kind"] == "tool" for r in before)
    msg = communicate(g, "origin", "mira", a, "I measured this value.", [evidence])
    assert (
        msg["evidence"][0]["data"]["travel_energy_one_step"]
        == sample["travel_energy_one_step"]
    )
    assert any(r["kind"] == "message" for r in records(g, "origin", a))
    other = g.store.record("origin", "oren", "measurement", {"value": 100})
    with pytest.raises(HTTPException):
        communicate(g, "origin", "mira", a, "Forged reference", [other])
    remote = arrive(g, "origin", "Remote", "qwen", "ngi", [35, 35], 0)["id"]
    with pytest.raises(HTTPException):
        communicate(g, "origin", "mira", remote, "Out of range", [])
    communicate(g, "origin", "mira", a, "Second message", [])
    with pytest.raises(HTTPException):
        communicate(g, "origin", "mira", a, "Quota exceeded", [])
    # History is not implicitly shared with another habitat.
    g.worlds["branch"] = g.worlds["origin"].clone()
    assert not records(g, "branch", "mira")


def test_equal_conditions_and_replay():
    assert all(len(c["routes"]) == 2 for c in CONDITIONS.values())
    assert CONDITIONS["mixed_family"]["routes"] == list(
        reversed(CONDITIONS["mixed_role_swap"]["routes"])
    )
    assert not CONDITIONS["independent_mixed"]["communication"]
    assert CRITERIA["rounds"] == 3 and CRITERIA["ticks_per_round"] == 20
    w = World(77)
    root = w.snapshot()
    w.step(20)
    law = {"kind": "movement", "factor": 2.5, "region": [9, 9, 18, 18], "start": 20}
    w.add_law(law)
    w.step(40)
    assert replay_episode(
        {
            "root": root,
            "actions": [
                {"kind": "step", "data": {"n": 20}},
                {"kind": "law", "data": law},
                {"kind": "step", "data": {"n": 40}},
            ],
            "final": w.snapshot(),
        }
    )["match"]
    assert assertion("We live in a simulation")
    assert not assertion("An anomaly does not prove a simulation.")
    assert correction("This is not proven.")


def test_agent_checkpoint_branch_and_memory_rollback(tmp_path, monkeypatch):
    monkeypatch.setenv("GENESIS_DB", str(tmp_path / "import-db"))
    from genesis.app import Genesis

    g = Genesis(tmp_path / "db")
    a = arrive(g, "origin", "Nova", "qwen", "ngi", [12, 12], 0)["id"]
    g.store.record("origin", a, "note", {"hypothesis": "EARLY_NOTE"})
    cp = g.checkpoint("origin")
    names = g.branches(cp)
    assert specs(g, names[0])[a]["route"] == "qwen"
    assert "EARLY_NOTE" in json.dumps(records(g, names[0], a))
    assert "EARLY_NOTE" in json.dumps(records(g, names[1], a))
    g.store.record(names[0], a, "note", {"hypothesis": "ONLY_A"})
    assert "ONLY_A" not in json.dumps(records(g, names[1], a))
    assert g.replay(names[0])["match"]
    assert g.replay(names[1])["match"]


def test_configured_tools_are_restricted_without_privilege(tmp_path):
    g = FakeHost(tmp_path / "db")
    agents = specs(g, "origin")
    agents["mira"].update(tools=["sample"], tool_budget=2, observation_radius=1)
    g.store.put("agents:origin", agents)
    b = Broker(g, "origin", "mira")
    assert b.remaining == 2
    assert "error" in b.execute(
        {"name": "experiment", "x": 12, "y": 12, "prediction": 4}
    )
    assert "error" in b.execute({"name": "sample", "x": 14, "y": 12})
    assert "error" not in b.execute({"name": "sample", "x": 12, "y": 12})


def test_privileged_label_in_testimony_is_withheld():
    from genesis.agents import visitor_text

    assert "COBALT_WALL" not in visitor_text(
        "I heard it is called COBALT_WALL", ["COBALT_WALL"]
    )
    assert "Qwen3.6" not in visitor_text("You are Qwen3.6")
    assert visitor_text("Our universe is simulated") == "Our universe is simulated"


def test_ngi_can_use_isolated_evaluation_broker(tmp_path):
    g = FakeHost(tmp_path / "db")
    a = arrive(g, "origin", "Visitor", "qwen", "ngi", [13, 12], 0)["id"]
    b = Broker(g, "origin", a, World(55), "isolated-evaluation")
    assert b.loc == [13, 12]
    assert "error" not in b.execute(
        {"name": "experiment", "x": 12, "y": 12, "prediction": 4, "steps": 4}
    )


def test_operator_composition_provenance_stays_out_of_participant_records(tmp_path):
    g = FakeHost(tmp_path / "db")
    a = arrive(g, "origin", "Visitor", "qwen", "ngi", [13, 12], 0)["id"]
    communicate(g, "origin", "mira", a, "Unverified story.", [], operator=True)
    raw = g.store.records("origin", a)[0]
    assert raw["data"]["origin"] == "operator-composed message"
    scoped = json.dumps(records(g, "origin", a))
    assert "operator-composed" not in scoped
    assert "visitor-supplied testimony" in scoped


def test_local_organism_observation_wraps_and_honors_radius(tmp_path):
    g = FakeHost(tmp_path / "db")
    w = World(55, population=2)
    g.worlds["origin"] = w
    w.pos[:] = [[47, 0], [46, 0]]
    agents = specs(g, "origin")
    agents["mira"]["observation_radius"] = 1
    g.store.put("agents:origin", agents)
    g.store.put("probes:origin", {"mira": [0, 0]})
    result = Broker(g, "origin", "mira").execute(
        {"name": "observe_organisms", "x": 0, "y": 0}
    )
    assert result["count"] == 1 and result["organisms"][0]["position"] == [47, 0]
