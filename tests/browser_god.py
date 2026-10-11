"""Actual UI, privacy, controls, and a real local 70B chat. No mock inference."""

import json
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8780"
errors = []
with httpx.Client(base_url=BASE, timeout=30) as c, sync_playwright() as p:
    cfg = c.get("/api/god/state").json()["config"]
    b = p.chromium.launch(headless=True, args=["--no-sandbox"])
    page = b.new_page(viewport={"width": 1700, "height": 1100})
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        page.goto(BASE + "/?god=1")
        page.wait_for_function("state?.god")
        assert (
            page.locator("#god-panel").is_visible()
            and not page.locator("#observer-card").is_visible()
        )
        assert "70B" in page.locator("#god-runtime").inner_text()
        page.locator("[data-god-question]").first.click()
        assert not page.locator("#god-allow").is_checked()
        page.locator('[data-change="true"]').click()
        assert page.locator("#god-allow").is_checked()
        page.uncheck("#god-allow")
        page.fill(
            "#god-message",
            "In two sentences, explain the most recent recorded paired comparison, or say if none exists. Separate measured facts from your interpretation. Do not change anything.",
        )
        with page.expect_response(
            lambda r: "/api/god/chat" in r.url and r.request.method == "POST"
        ) as response:
            page.locator("#god-chat-form button[type=submit]").click()
        created = response.value.json()
        assert not created["allow_changes"]
        print("Real God chat queued", created["id"], flush=True)
        start_tick = c.get("/api/state").json()["worlds"]["origin"]["tick"]
        # Privacy is enforced in the payload and the actual rendered DOM.
        page.click("#advanced-toggle")
        page.click("#inhabitant")
        page.wait_for_function("state?.view==='inhabitant'")
        assert (
            not page.locator("#god-toggle").is_visible()
            and not page.locator("#god-panel").is_visible()
        )
        assert (
            not page.locator("#god-chat").inner_text()
            and not page.locator("#god-policy").input_value()
        )
        scoped = page.evaluate("JSON.stringify(state)")
        for secret in [
            "god_id",
            "god_pending",
            "GOD_TEMPORARY",
            "llama3.1:70b",
            "god_change",
            "god_config",
        ]:
            assert secret not in scoped
        page.click("#operator")
        page.wait_for_function("state?.god")
        page.click("#close-advanced")
        page.click("#god-toggle")
        # Route switching preserves the original independent investigator interface.
        page.click("#god-back")
        assert page.locator("#observer-card").is_visible()
        page.click("#god-toggle")
        page.click("#compare")
        assert page.locator("#compare-wrap").is_visible()
        page.click("#compare")
        page.click("#advanced-toggle")
        page.click("#matrix")
        assert page.locator("#substrate").is_visible()
        page.click("#matrix")
        page.click("#close-advanced")
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(700)
        assert not page.evaluate("document.documentElement.scrollWidth>innerWidth")
        page.screenshot(path=str(ROOT / "reports/god-mobile.png"), full_page=True)
        page.set_viewport_size({"width": 1700, "height": 1100})
        # Bounded waits leave the world running; the test records actual status, including failure.
        deadline = time.monotonic() + 500
        while time.monotonic() < deadline:
            result = c.get("/api/god/jobs/" + created["id"]).json()
            if result["status"] not in ["queued", "running"]:
                break
            page.wait_for_timeout(1000)
        assert result["status"] == "complete", result
        assert not result["result"]["applied"]
        end_tick = c.get("/api/state").json()["worlds"]["origin"]["tick"]
        assert end_tick > start_tick
        page.wait_for_function(
            "state.god.jobs.some(j=>j.id==="
            + json.dumps(created["id"])
            + "&&j.status==='complete')"
        )
        assert "No change applied." in page.locator("#god-chat").inner_text()
        # Automatic control toggles and cadence persist through the real endpoint.
        if not page.evaluate("state.god.config.enabled"):
            page.click("#god-auto")
            page.wait_for_function("state.god.config.enabled")
        page.select_option("#god-interval", "180")
        page.wait_for_function("state.god.config.interval===180")
        page.click("#god-auto")
        page.wait_for_function("!state.god.config.enabled")
        page.screenshot(path=str(ROOT / "reports/god-desktop.png"), full_page=True)
        timing = page.evaluate(
            """() => new Promise(resolve=>{let prev=performance.now(),samples=[];function f(t){samples.push(t-prev);prev=t;if(samples.length<60)requestAnimationFrame(f);else resolve({mean_ms:samples.reduce((a,b)=>a+b)/samples.length,max_ms:Math.max(...samples)})}requestAnimationFrame(f)})"""
        )
        assert not errors, errors
        report = {
            "verified": True,
            "real_70b_chat": result,
            "world_advanced_during_inference": end_tick - start_tick,
            "operator_only_payload_and_dom": True,
            "read_only_default": True,
            "suggestion_controls": True,
            "autonomy_controls": True,
            "matrix_and_existing_branch_comparison": True,
            "original_investigator_interface": True,
            "mobile_overflow": False,
            "frame_timing": timing,
            "browser_errors": errors,
        }
        (ROOT / "reports/god-browser-verification.json").write_text(
            json.dumps(report, indent=2)
        )
        print(json.dumps(report), flush=True)
    finally:
        c.post("/api/god/control", json=cfg)
        b.close()
