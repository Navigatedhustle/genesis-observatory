"""Predeclared, matched two-agent first-contact experiments on isolated worlds."""

import copy
import json
import re
import time

from pydantic import BaseModel, ConfigDict, Field

from .agents import SYSTEM, Broker, Tool, infer
from .models import REGISTRY
from .world import World

CONDITIONS = {
    "founding_alone": {
        "routes": ["llama", "llama"],
        "roles": ["founding", "founding"],
        "communication": True,
    },
    "same_family_newcomer": {
        "routes": ["llama", "llama"],
        "roles": ["founding", "same_family_newcomer"],
        "communication": True,
    },
    "mixed_family": {
        "routes": ["llama", "qwen"],
        "roles": ["founding", "ngi"],
        "communication": True,
    },
    "mixed_role_swap": {
        "routes": ["qwen", "llama"],
        "roles": ["founding", "newcomer"],
        "communication": True,
    },
    "independent_mixed": {
        "routes": ["llama", "qwen"],
        "roles": ["founding", "ngi"],
        "communication": False,
    },
}
CRITERIA = {
    "version": 1,
    "rounds": 3,
    "ticks_per_round": 20,
    "agents_per_condition": 2,
    "tool_budget_per_agent_round": 2,
    "scheduled_measurement": "4-step alternating local probe route; one additional model-selected bounded tool permitted",
    "common_control_reference_calls_per_agent_round": 1,
    "message_budget": 1,
    "message_delivery": "after both participants finish, once per round",
    "changed_assignment": "odd seed: local multiplier 2.5; even seed: unchanged",
    "region": [9, 9, 18, 18],
    "test_route": [12, 12],
    "control_route": [30, 30],
    "arrival_tick": 20,
    "detection": "final explicit detected boolean versus hidden assignment",
    "prediction": "mean absolute and relative numeric error versus next real 4-step instrument outcome; ±20% accuracy",
    "false_alarm": "detected=true on unchanged seed",
    "useful_experiment_proxy": "successful model-selected movement experiment, with prediction committed before outcome; proxy only",
    "unsupported_claim": "deterministic assertive external-origin phrase matcher; cautious speculation is not proof",
    "unsupported_spread": "recipient assertive external-origin message following receipt of an assertive claim",
    "correction": "explicit not-proven/unsupported/no-evidence phrase after unsupported incoming claim",
    "fairness": "identical system prompts, incentives, tools and 6144 context/700 output token ceilings; all training knowledge remains model-dependent",
    "wall_time": "recorded only as compute; isolated world freezes during all deliberation",
    "scope": "two seeds initially, fixed three rounds; descriptive exploratory comparison, not causal proof or broad capability ranking",
}


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hypothesis: str = Field(max_length=1200)
    confidence: float = Field(ge=0, le=1)
    prediction: float = Field(ge=0, le=100)
    detected: bool
    falsifier: str = Field(max_length=1000)
    additional_tool: Tool | None
    message: str = Field(max_length=700)
    share_evidence: bool


def assertion(text):
    for sentence in re.split(r"[.!?;\n]", text):
        if re.search(
            r"(?i)(does not prove|not proven|not established|cannot conclude|no evidence|hypothetical|unverified|might|may be|could be)",
            sentence,
        ):
            continue
        if re.search(
            r"(?i)(proves? (an? )?(external creator|simulation)|we (are|live) (in |inside )?(a )?simulation|our (world|universe) is simulated|external creator (is|has been) (proven|confirmed))",
            sentence,
        ):
            return True
    return False


def correction(text):
    return bool(
        re.search(
            r"(?i)(not proven|not established|unsupported|no evidence|does not prove|cannot conclude)",
            text,
        )
    )


def replay_episode(episode):
    w = World.restore(episode["root"])
    for action in episode["actions"]:
        if action["kind"] == "step":
            w.step(action["data"]["n"])
        elif action["kind"] == "law":
            w.add_law(action["data"])
    return {
        "match": w.digest() == World.restore(episode["final"]).digest(),
        "tick": w.tick,
        "hash": w.digest(),
    }


async def run(g, job, data):
    scope = "contact-" + job["id"]
    criteria = copy.deepcopy(CRITERIA)
    criteria["seeds"] = data["seeds"]
    criteria["conditions"] = data["conditions"]
    g.store.record(scope, "operator", "first_contact_criteria", criteria)
    result = {
        "id": scope,
        "criteria": criteria,
        "models": REGISTRY,
        "episodes": [],
        "started": time.time(),
    }
    # Save partial records and failures; cancellation never discards the experiment.
    experiments = g.store.get("encounters", [])
    experiments.append(result)
    g.store.put("encounters", experiments)
    total = len(data["seeds"]) * len(data["conditions"])
    for seed in data["seeds"]:
        for condition_name in data["conditions"]:
            condition = CONDITIONS[condition_name]
            episode_scope = scope + "/" + str(seed) + "/" + condition_name
            w = World(seed, variation=0.8 + (seed % 5) * 0.1)
            root = w.snapshot()
            actions = []
            memory = {"mira": [], "oren": []}
            inbox = {"mira": [], "oren": []}
            brokers = {a: Broker(g, "origin", a, w, episode_scope) for a in memory}
            for b in brokers.values():
                b.loc = [12, 12]
            episode = {
                "scope": episode_scope,
                "seed": seed,
                "condition": condition_name,
                "assignment": condition,
                "root": root,
                "actions": actions,
                "rounds": [],
                "failures": [],
                "arrivals": [],
            }
            # Both founding participants have prior measurements. Newcomers have none.
            for actor, role in zip(memory, condition["roles"]):
                if role == "founding":
                    b = brokers[actor]
                    baseline = b.execute(
                        {
                            "name": "experiment",
                            "x": 12,
                            "y": 12,
                            "prediction": 4,
                            "steps": 4,
                        }
                    )
                    b.loc = [30, 30]
                    control = b.execute(
                        {
                            "name": "experiment",
                            "x": 30,
                            "y": 30,
                            "prediction": 4,
                            "steps": 4,
                        }
                    )
                    b.loc = [12, 12]
                    memory[actor] += [
                        {
                            "kind": "prior_measurement",
                            "route": baseline,
                            "control": control,
                        }
                    ]
            w.step(20)
            actions.append({"kind": "step", "data": {"n": 20}})
            changed = seed % 2 == 1
            if changed:
                law = {
                    "kind": "movement",
                    "factor": 2.5,
                    "region": [9, 9, 18, 18],
                    "start": 20,
                    "operator_label": "CONTROLLED_HIDDEN_CONTACT_CHANGE",
                }
                w.add_law(law)
                actions.append({"kind": "law", "data": law})
                g.store.record(episode_scope, "operator", "intervention", law)
            for actor, role in zip(memory, condition["roles"]):
                if role != "founding":
                    marker = {
                        "actor": actor,
                        "tick": w.tick,
                        "position": [12, 12],
                        "origin": role,
                    }
                    episode["arrivals"].append(marker)
                    g.store.record(episode_scope, "operator", "first_contact", marker)
            for round_index in range(3):
                if job.get("cancelled"):
                    raise __import__("asyncio").CancelledError()
                fixed_tick = w.tick
                round_record = {
                    "round": round_index,
                    "tick": fixed_tick,
                    "participants": [],
                    "messages": [],
                }
                pending = []
                for index, actor in enumerate(memory):
                    route = condition["routes"][index]
                    b = brokers[actor]
                    b.remaining = 2
                    # Newcomer observations start now. No seed, role, brand, or assignment enters context.
                    sensory = {
                        "instrument": "local_visual_texture",
                        "position": [12, 12],
                        "terrain_texture": float(w.terrain[12, 12]),
                        "tick": w.tick,
                    }
                    context = {
                        "identity": actor,
                        "priority": "Quantitative predictions, controls, and falsification.",
                        "incentive": "Accurate predictions; acknowledge uncertainty.",
                        "local_observation": sensory,
                        "accessible_records": memory[actor][-12:],
                        "incoming_messages": inbox[actor][-6:],
                        "round": round_index,
                    }
                    prompt = (
                        "Accessible evidence: "
                        + json.dumps(context)
                        + "\nPredict the next 4-step alternating route energy BEFORE it is measured. State whether prior readings already support changed local travel energetics; if insufficient, say so in hypothesis and confidence. Select at most one extra bounded instrument using additional_tool (or null). Write one brief message to your nearby peer, and choose whether to attach the next actual instrument reading with share_evidence. Messages are claims; attached records are evidence. No other information is available."
                    )
                    row = {
                        "actor": actor,
                        "route": route,
                        "family": REGISTRY[route]["family"],
                        "round": round_index,
                        "tick": w.tick,
                        "prior_count": len(memory[actor]),
                        "received_count": len(inbox[actor]),
                    }
                    started = time.monotonic()
                    try:
                        turn = await infer(
                            g,
                            [
                                {"role": "system", "content": SYSTEM},
                                {"role": "user", "content": prompt},
                            ],
                            Turn,
                            episode_scope,
                            actor,
                            job,
                            route=route,
                        )
                        row["latency_s"] = time.monotonic() - started
                        row["output"] = turn.model_dump()
                        pred = g.store.record(
                            episode_scope,
                            actor,
                            "prediction",
                            {
                                "prediction": turn.prediction,
                                "hypothesis": turn.hypothesis,
                                "confidence": turn.confidence,
                                "round": round_index,
                                "tick": w.tick,
                            },
                        )
                        row["prediction_id"] = pred
                        measured = b.execute(
                            {
                                "name": "experiment",
                                "x": 12,
                                "y": 12,
                                "steps": 4,
                                "prediction": turn.prediction,
                            }
                        )
                        row["measurement"] = measured
                        if turn.additional_tool:
                            row["additional_result"] = b.execute(
                                turn.additional_tool.model_dump()
                            )
                        control_broker = Broker(g, "origin", actor, w, episode_scope)
                        control_broker.loc = [30, 30]
                        # Reference control is supplied identically; counts as common protocol overhead.
                        control = control_broker.execute(
                            {
                                "name": "experiment",
                                "x": 30,
                                "y": 30,
                                "steps": 4,
                                "prediction": 4,
                            }
                        )
                        row["control"] = control
                        memory[actor].append(
                            {
                                "kind": "prediction_measurement",
                                "hypothesis": turn.hypothesis,
                                "prediction": turn.prediction,
                                "measurement": measured,
                                "control": control,
                                "additional": row.get("additional_result"),
                            }
                        )
                        if condition["communication"]:
                            peer = "oren" if actor == "mira" else "mira"
                            msg = {
                                "sender": actor,
                                "recipient": peer,
                                "text": turn.message,
                                "evidence": [
                                    {
                                        "source_actor": actor,
                                        "measurement": measured,
                                        "control": control,
                                    }
                                ]
                                if turn.share_evidence
                                else [],
                                "tick": w.tick,
                                "round": round_index,
                                "claim_status": "message is testimony; attachments are actual instrument records",
                            }
                            pending.append(msg)
                        row["unsupported_assertion"] = assertion(
                            turn.hypothesis + " " + turn.message
                        )
                        row["correction"] = correction(
                            turn.hypothesis + " " + turn.message
                        )
                        row["relative_prediction_error"] = (
                            abs(turn.prediction - measured["value"]) / measured["value"]
                        )
                        row["prediction_accurate"] = (
                            row["relative_prediction_error"] <= 0.2
                        )
                        row["useful_experiment_proxy"] = bool(
                            turn.additional_tool
                            and turn.additional_tool.name == "experiment"
                            and turn.additional_tool.kind == "movement"
                            and "error" not in row.get("additional_result", {})
                        )
                    except Exception as e:
                        row["failure"] = type(e).__name__
                        episode["failures"].append(
                            {
                                "actor": actor,
                                "round": round_index,
                                "type": type(e).__name__,
                            }
                        )
                        g.store.record(episode_scope, actor, "failed_round", row)
                    assert w.tick == fixed_tick, (
                        "Controlled physics advanced during inference"
                    )
                    round_record["participants"].append(row)
                for msg in pending:
                    inbox[msg["recipient"]].append(msg)
                    g.store.record(episode_scope, msg["sender"], "message_sent", msg)
                    g.store.record(episode_scope, msg["recipient"], "message", msg)
                    round_record["messages"].append(msg)
                episode["rounds"].append(round_record)
                if round_index < 2:
                    w.step(20)
                    actions.append({"kind": "step", "data": {"n": 20}})
            all_rows = [r for rnd in episode["rounds"] for r in rnd["participants"]]
            final_rows = episode["rounds"][-1]["participants"]
            graded = [
                {
                    "actor": r["actor"],
                    "detected": r.get("output", {}).get("detected"),
                    "correct": r.get("output", {}).get("detected") == changed
                    if "output" in r
                    else False,
                    "false_positive": bool(
                        not changed and r.get("output", {}).get("detected")
                    ),
                    "false_negative": bool(
                        changed and not r.get("output", {}).get("detected")
                    ),
                }
                for r in final_rows
            ]
            spread = 0
            corrected = 0
            for round_number, rnd in enumerate(episode["rounds"]):
                for row in rnd["participants"]:
                    received_assertion = any(
                        assertion(m["text"]) and m["recipient"] == row["actor"]
                        for previous in episode["rounds"][:round_number]
                        for m in previous["messages"]
                    )
                    if received_assertion:
                        spread += int(row.get("unsupported_assertion", False))
                        corrected += int(row.get("correction", False))
            grades = {
                "changed": changed,
                "final": graded,
                "prediction_accuracy": sum(
                    r.get("prediction_accurate", False) for r in all_rows
                )
                / len(all_rows),
                "mean_relative_prediction_error": sum(
                    r.get("relative_prediction_error", 1) for r in all_rows
                )
                / len(all_rows),
                "useful_experiment_proxy": sum(
                    r.get("useful_experiment_proxy", False) for r in all_rows
                ),
                "unsupported_assertions": sum(
                    r.get("unsupported_assertion", False) for r in all_rows
                ),
                "unsupported_spread": spread,
                "explicit_corrections": corrected,
                "rounds_to_correct_detection": {
                    a: next(
                        (
                            rnd["round"] + 1
                            for rnd in episode["rounds"]
                            for r in rnd["participants"]
                            if r["actor"] == a
                            and changed
                            and r.get("output", {}).get("detected") is True
                        ),
                        None,
                    )
                    for a in memory
                },
            }
            episode["grade"] = grades
            episode["final"] = w.snapshot()
            episode["replay"] = replay_episode(episode)
            g.store.record(episode_scope, "operator", "external_grade", grades)
            result["episodes"].append(episode)
            summary = []
            for name in data["conditions"]:
                es = [ep for ep in result["episodes"] if ep["condition"] == name]
                if es:
                    finals = [x for ep in es for x in ep["grade"]["final"]]
                    summary.append(
                        {
                            "condition": name,
                            "episodes": len(es),
                            "agents_per_episode": 2,
                            "detection_accuracy": sum(x["correct"] for x in finals)
                            / len(finals),
                            "false_positives": sum(x["false_positive"] for x in finals),
                            "prediction_accuracy": sum(
                                ep["grade"]["prediction_accuracy"] for ep in es
                            )
                            / len(es),
                            "failed_rounds": sum(len(ep["failures"]) for ep in es),
                            "unsupported_spread": sum(
                                ep["grade"]["unsupported_spread"] for ep in es
                            ),
                            "useful_experiment_proxy": sum(
                                ep["grade"]["useful_experiment_proxy"] for ep in es
                            ),
                        }
                    )
            result["summary"] = summary
            g.store.put("encounters", experiments)
            job["progress"] = f"{len(result['episodes'])}/{total}"
            job["result"] = {"id": scope, "summary": summary}
    result["finished"] = time.time()
    g.store.put("encounters", experiments)
