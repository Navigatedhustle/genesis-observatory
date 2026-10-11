"""Additive arrival registry and scoped local communication."""

import copy
import uuid

from fastapi import HTTPException

from .agents import ACTORS, visitor_text
from .models import REGISTRY

COMMON_PRIORITY = "Quantitative investigation of travel energy, uncertainty, controls, and falsification."


def specs(g, world):
    stored = g.store.get("agents:" + world)
    if stored is None:
        stored = {
            k: {
                "id": k,
                "name": v["name"],
                "origin": "founding",
                "role": "investigator",
                "route": "llama",
                "priority": v["priority"],
                "incentive": "Accurate predictions; acknowledge uncertainty.",
                "arrival_tick": 0,
                "active": True,
                "position": v["start"],
                "color": {"mira": "#70ded7", "oren": "#e8b76b", "vale": "#b499f0"}[k],
            }
            for k, v in ACTORS.items()
        }
        g.store.put("agents:" + world, stored)
    return stored


def spec(g, world, actor):
    all_agents = specs(g, world)
    if actor not in all_agents or not all_agents[actor]["active"]:
        raise HTTPException(400, "Investigator is not present in this habitat")
    return all_agents[actor]


def arrive(
    g,
    world,
    name,
    route,
    origin,
    position,
    at_tick,
    priority=COMMON_PRIORITY,
    incentive="Accurate predictions; acknowledge uncertainty.",
    role="investigator",
):
    w = g.world(world)
    all_agents = specs(g, world)
    if len(all_agents) >= 9:
        raise HTTPException(400, "Maximum nine language investigators per habitat")
    if route not in REGISTRY:
        raise HTTPException(400, "Unknown local model route")
    if origin == "ngi" and REGISTRY[route]["family"] == "Llama":
        raise HTTPException(
            400,
            "NGI requires a different family from the founding Llama investigators; use same-family newcomer for this route",
        )
    identity = "arrival-" + uuid.uuid4().hex[:6]
    a = {
        "id": identity,
        "name": name,
        "route": route,
        "origin": origin,
        "role": role,
        "priority": priority,
        "incentive": incentive,
        "position": position,
        "arrival_tick": max(w.tick, at_tick),
        "active": False,
        "color": "#9dfc91" if origin == "ngi" else "#b499f0",
    }
    all_agents[identity] = a
    g.store.put("agents:" + world, all_agents)
    g.store.record(world, "operator", "arrival_scheduled", copy.deepcopy(a))
    activate(g, world)
    return specs(g, world)[identity]


def activate(g, world):
    agents = specs(g, world)
    w = g.world(world)
    p = g.store.get(
        "probes:" + world, {k: v["position"] for k, v in agents.items() if v["active"]}
    )
    changed = False
    for actor, a in agents.items():
        if not a["active"] and w.tick >= a["arrival_tick"]:
            a["active"] = True
            changed = True
            p[actor] = a["position"][:]
            g.store.record(
                world,
                "operator",
                "first_contact",
                {
                    "actor": actor,
                    "tick": w.tick,
                    "planned_tick": a["arrival_tick"],
                    "position": a["position"],
                    "origin": a["origin"],
                    "family": REGISTRY[a["route"]]["family"],
                },
            )
            # Newcomers get their own present arrival observation, no historical memories.
            g.store.record(
                world,
                actor,
                "observation",
                {
                    "instrument": "arrival_position",
                    "tick": w.tick,
                    "position": a["position"],
                },
            )
    if changed:
        g.store.put("agents:" + world, agents)
        g.store.put("probes:" + world, p)


def communicate(g, world, sender, recipient, text, evidence_ids, operator=False):
    # Instruments are referenced from the sender's actual records, never pasted and trusted.
    s = spec(g, world, sender)
    r = spec(g, world, recipient)
    p = g.store.get("probes:" + world, {})
    a = p.get(sender, s["position"])
    b = p.get(recipient, r["position"])
    distance = max(
        min(abs(a[0] - b[0]), 48 - abs(a[0] - b[0])),
        min(abs(a[1] - b[1]), 48 - abs(a[1] - b[1])),
    )
    if distance > 12:
        raise HTTPException(
            400, "Recipient is outside the 12-cell communication channel"
        )
    own = g.store.records(world, sender, limit=500)
    # Per-round channel quotas prevent recursive or unbounded chatter.
    current_round = g.world(world).tick // 20
    sent = [
        x
        for x in own
        if x["kind"] == "message_sent" and x["data"].get("round") == current_round
    ]
    if len(sent) >= 2:
        raise HTTPException(429, "Two messages per 20-tick round are permitted")
    permitted = {x["id"]: x for x in own if x["kind"] in ["measurement", "tool"]}
    if any(eid not in permitted for eid in evidence_ids):
        raise HTTPException(
            400, "Evidence references must belong to the sender and this habitat"
        )
    evidence = [
        {
            "source_actor": sender,
            "source_record": eid,
            "data": permitted[eid]["data"].get("result", permitted[eid]["data"]),
        }
        for eid in evidence_ids
    ]
    message = {
        "sender": sender,
        "recipient": recipient,
        "text": visitor_text(
            text, [law.get("operator_label", "") for law in g.world(world).laws]
        )[:800],
        "evidence": evidence,
        "round": current_round,
        "tick": g.world(world).tick,
        "claim_status": "message is testimony; attached evidence is instrument-backed",
        "origin": "operator-composed message"
        if operator
        else "model-generated message",
    }
    g.store.record(world, sender, "message_sent", message)
    g.store.record(world, recipient, "message", message)
    return message
