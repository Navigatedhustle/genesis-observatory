"""Integration audit of actual local requests and the completed prediction/measurement flow."""

import json
import statistics
from pathlib import Path

import httpx

from genesis.replay import replay

root = Path(__file__).resolve().parent.parent
with httpx.Client(base_url="http://127.0.0.1:8780", timeout=120) as client:
    state = client.get("/api/state").json()
    bundle = client.get("/api/export").json()
    rows = bundle["records"]
    by_id = {r["id"]: r for r in rows}
    for r in rows:
        if r["kind"] == "measurement":
            pred = by_id[r["data"]["prediction_id"]]
            assert pred["kind"] == "prediction" and pred["id"] < r["id"]
            assert pred["scope"] == r["scope"] and pred["actor"] == r["actor"]
    calls = [r for r in rows if r["kind"] == "model_output"]
    routes = {r["data"].get("route") for r in calls}
    assert {"llama", "qwen"} <= routes
    for r in calls:
        context = json.dumps(r["data"]["request"]["messages"])
        for secret in [
            "operator_label",
            "CONTROLLED_HIDDEN_CONTACT_CHANGE",
            "HELD_OUT_REGIONAL_CHANGE",
            '"rng_state"',
            '"seed":',
            "Qwen3.6-35B",
            "llama3.1:8b",
        ]:
            assert secret not in context, (secret, r["id"])
    for run in bundle["encounters"]:
        assert run.get("finished") and len(run["episodes"]) == len(
            run["criteria"]["seeds"]
        ) * len(run["criteria"]["conditions"])
        predeclared = next(
            r
            for r in rows
            if r["scope"] == run["id"] and r["kind"] == "first_contact_criteria"
        )
        for episode in run["episodes"]:
            assert episode["replay"]["match"]
            assert [r["tick"] for r in episode["rounds"]] == [20, 40, 60]
            if not episode["assignment"]["communication"]:
                assert not any(r["messages"] for r in episode["rounds"])
            for rnd in episode["rounds"]:
                assert len(rnd["participants"]) == 2
                for participant in rnd["participants"]:
                    assert participant["prediction_id"] in by_id
                    assert by_id[participant["prediction_id"]]["id"] > predeclared["id"]
                    m = participant["measurement"]
                    assert m["start_tick"] == rnd["tick"]
                    assert participant["tick"] == rnd["tick"]
                    assert participant["prediction_id"] < m["prediction_id"]
                    # Recorded explicit fields are graded, rather than persuasive explanations.
            final = episode["rounds"][-1]["participants"]
            for row, grade in zip(final, episode["grade"]["final"]):
                assert grade["correct"] == (
                    row["output"]["detected"] == episode["grade"]["changed"]
                )
    matches = replay(bundle)
    assert all(r["match"] for r in matches.values())
    # No agent-accessible endpoint contains source state, model routes, or operator labels.
    for world, agents in bundle["agent_registry"].items():
        for actor, a in agents.items():
            if not a["active"]:
                continue
            response = client.get(
                "/api/state",
                params={"view": "inhabitant", "world": world, "actor": actor},
            )
            assert response.status_code == 200
            body = response.text
            for secret in [
                "operator_label",
                "rng_state",
                "controller_weights",
                "Qwen3.6-35B",
                "llama3.1:8b",
                "model_registry",
            ]:
                assert secret not in body, (world, actor, secret)
    latencies = {}
    for route in ["llama", "qwen"]:
        samples = [
            r["data"]["latency_s"] for r in calls if r["data"].get("route") == route
        ]
        latencies[route] = {
            "requests": len(samples),
            "median_s": round(statistics.median(samples), 3),
            "min_s": round(min(samples), 3),
            "max_s": round(max(samples), 3),
        }
    result = {
        "world_replays": matches,
        "raw_model_routes": sorted(x for x in routes if x),
        "latencies": latencies,
        "predictions_before_measurements": True,
        "round_scheduling_verified": True,
        "agent_context_restrictions_verified": True,
        "compute": state["compute"],
        "contact_summary": bundle["encounters"][-1]["summary"],
    }
    (root / "reports/verification.json").write_text(json.dumps(result, indent=2))
    (root / "reports/first-contact-export.json").write_text(json.dumps(bundle))
    print(
        json.dumps(
            {
                "verified": True,
                "replayed_worlds_and_episodes": len(matches),
                "latencies": latencies,
                "compute": state["compute"],
            },
            indent=2,
        )
    )
