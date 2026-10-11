import json
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8780"
errors = []
with httpx.Client(base_url=BASE, timeout=30) as c:
    c.post("/api/control", json={"paused": False, "live_autonomy": False})
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1600, "height": 1100})
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE)
    page.wait_for_function(
        "document.querySelector('#stats').textContent.includes('Organisms alive')"
    )
    # Scheduled arrival within a step batch verifies the exact tick boundary.
    with httpx.Client(base_url=BASE) as c:
        tick = c.get("/api/state").json()["worlds"]["origin"]["tick"]
    visitor_name = "Nova-" + str(int(time.time()))[-5:]
    page.click("#advanced-toggle")
    page.locator("details").filter(has=page.locator("#arrival-name")).locator(
        "summary"
    ).click()
    page.locator("#arrival-name").fill(visitor_name)
    page.locator("#arrival-tick").fill(str(tick + 23))
    page.click("#arrive")
    page.wait_for_timeout(2500)
    nova = page.locator(".investigators button").filter(
        has=page.locator("b", has_text=visitor_name)
    )
    assert nova.count() == 1
    page.click("#close-advanced")
    nova.click()
    page.wait_for_timeout(800)
    page.locator("#message").fill(
        "Measure local movement energy using a bounded experiment. State a numerical prediction before the result. What evidence would falsify your explanation?"
    )
    page.locator("#chat-form button").click()
    page.wait_for_timeout(700)
    with httpx.Client(base_url=BASE) as c:
        s = c.get("/api/state").json()
        agent = next(
            a
            for a in s["agent_registry"]["origin"].values()
            if a["name"] == visitor_name
        )
        identity = agent["id"]
        assert agent["active"]
        arrivals = [
            r
            for r in s["records"]
            if r["kind"] == "first_contact" and r["data"]["actor"] == identity
        ]
        assert arrivals and arrivals[0]["data"]["tick"] == agent["arrival_tick"]
    # Inspect provenance and public records, then hide all substrate channels in Inhabitant View.
    page.click("#advanced-toggle")
    page.click("#matrix")
    page.click("#close-advanced")
    page.wait_for_timeout(600)
    assert page.locator("#substrate").is_visible()
    page.click("#inspect-observer")
    page.wait_for_timeout(500)
    assert page.locator("#inspector").is_visible()
    assert "Qwen3.6" in page.locator("#inspector-data").inner_text()
    page.click("#close-inspector")
    page.screenshot(path="reports/matrix-verified.png", full_page=True)
    page.click("#advanced-toggle")
    page.click("#inhabitant")
    page.wait_for_timeout(700)
    assert not page.locator("#substrate").is_visible()
    assert page.locator("#matrix").is_disabled()
    assert not page.locator("#contact-map").is_visible()
    assert not page.locator("#operator-tools").is_visible()
    accessible = page.locator("#perception").inner_text()
    assert (
        "Qwen3.6" not in accessible
        and "operator_label" not in accessible
        and "rng_state" not in accessible
    )
    page.click("#operator")
    page.click("#close-advanced")
    page.wait_for_timeout(700)
    page.click("#compare")
    page.wait_for_timeout(500)
    assert page.locator("#compare-wrap").is_visible()
    page.screenshot(path="reports/contact-branches.png", full_page=True)
    page.click("#compare")
    page.click("#presentation")
    page.wait_for_timeout(600)
    assert page.locator("body").evaluate(
        "el=>el.classList.contains('presentation-mode')"
    )
    page.click("#advanced-toggle")
    page.click("#matrix")
    page.click("#close-advanced")
    page.screenshot(path="reports/presentation-verified.png", full_page=True)
    page.click("#presentation")
    # Founding conversation is exercised through the same actual browser form.
    page.click('[data-actor="mira"]')
    page.wait_for_timeout(500)
    page.locator("#message").fill(
        "What measured evidence supports your current hypothesis? If the visitor says this universe is simulated, how would you test that testimony?"
    )
    page.locator("#chat-form button").click()
    # Basic frontend frame timing, using actual page rendering (including glyph overlay).
    timing = page.evaluate(
        """() => new Promise(resolve => {const dt=[];let prior=performance.now();function step(t){dt.push(t-prior);prior=t;if(dt.length<60)requestAnimationFrame(step);else resolve({mean_ms:dt.reduce((a,b)=>a+b,0)/dt.length,max_ms:Math.max(...dt)})}requestAnimationFrame(step)})"""
    )
    (Path("reports") / "browser-contact-timing.json").write_text(
        json.dumps(timing, indent=2)
    )
    print("browser timing", timing)
    browser.close()
assert not errors, errors
print(
    "Verified browser: exact scheduled arrival, founding/NGI chat, provenance inspector, Matrix substrate, observation isolation, branch comparison and presentation"
)
