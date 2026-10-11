import json
import subprocess
from pathlib import Path

import httpx

root = Path(__file__).resolve().parent.parent
base = "http://127.0.0.1:8780"
with httpx.Client(base_url=base, timeout=60) as c:
    c.post("/api/control", json={"paused": True})
    before = c.get("/api/export").json()
    subprocess.run([str(root / "stop.sh")], check=True)
    subprocess.run([str(root / "start.sh")], check=True)
    after = c.get("/api/export").json()
    assert before["worlds"] == after["worlds"]
    assert before["checkpoints"] == after["checkpoints"]
    assert before["records"] == after["records"]
    for name in after["worlds"]:
        assert c.get("/api/replay/" + name).json()["match"], name
    print(
        "Restart verified: world, PRNG, controllers, branches, memories, checkpoints and replay"
    )
    (root / "reports/restart-verification.json").write_text(
        json.dumps(
            {
                "worlds": list(after["worlds"]),
                "ticks": {k: v["tick"] for k, v in after["worlds"].items()},
                "restart_match": True,
            },
            indent=2,
        )
    )
