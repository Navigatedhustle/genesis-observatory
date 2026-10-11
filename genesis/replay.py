import json
import sys

from .world import World


def replay(bundle):
    if "roots" not in bundle and "episodes" in bundle:
        from .god import verify_export

        return verify_export(bundle)
    results = {}
    for name, root in bundle["roots"].items():
        w = World.restore(root)
        for action in bundle["actions"][name]:
            kind = action["kind"]
            data = action["data"]
            if kind == "step":
                w.step(data["n"])
            elif kind == "law":
                w.add_law(data)
            elif kind == "pulse":
                w.resource_pulse(**data)
            elif kind == "restore":
                w = World.restore(data["state"])
        results[name] = {
            "match": w.digest() == World.restore(bundle["worlds"][name]).digest(),
            "tick": w.tick,
            "hash": w.digest(),
        }
    from .encounter import replay_episode

    for run in bundle.get("encounters", []):
        for episode in run["episodes"]:
            results[episode["scope"]] = replay_episode(episode)
    for run in bundle.get("evaluations", []):
        for row in run["rows"]:
            if "world_root" in row:
                results[run["id"] + "/" + str(row["seed"])] = replay_episode(
                    {
                        "root": row["world_root"],
                        "final": row["world_final"],
                        "actions": row["world_actions"],
                    }
                )
    from .god import replay_state

    for world, data in bundle.get("god", {}).items():
        for identity, episode in data.get("episodes", {}).items():
            if episode:
                w = replay_state(episode["root"], episode["actions"])
                results["god:" + world + "/" + identity] = {
                    "match": w.digest() == World.restore(episode["final"]).digest(),
                    "tick": w.tick,
                }
    return results


if __name__ == "__main__":
    results = replay(json.load(open(sys.argv[1])))
    print(json.dumps(results, indent=2))
    sys.exit(0 if all(r["match"] for r in results.values()) else 1)
