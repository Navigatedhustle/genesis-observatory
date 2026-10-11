"""Real-browser verification of the watch-first interface; no inference substitutes."""

import json
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8780"
root = Path(__file__).resolve().parent.parent
errors = []
requests = []
with httpx.Client(base_url=BASE, timeout=30) as c:
    initial = c.get("/api/state").json()
    original_settings = initial["settings"].copy()
    ngi = next(
        a
        for a in initial["agent_registry"]["origin"].values()
        if a["origin"] == "ngi" and a["active"]
    )
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1600, "height": 1050})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(BASE)
            page.wait_for_function(
                "state?.worlds && document.querySelector('.journal-entry')"
            )
            assert not page.locator("#advanced-panel").is_visible()
            assert (
                "Little dots = organisms" in page.locator("#world-guide").inner_text()
            )
            assert "food" in page.locator("#observer-role").inner_text()
            # The journal and map are next to each other, with the journal visible without scrolling.
            assert page.locator("#activity-panel").bounding_box()["y"] < 650
            assert (
                page.locator("#activity-panel").bounding_box()["x"]
                > page.locator("#habitat").bounding_box()["x"]
            )
            assert not page.locator(".journal-entry").first.evaluate(
                "e=>getComputedStyle(e).display==='grid'"
            )
            # Match translated counters to the exact world history that produced them.
            ecology = page.evaluate("Understanding.ecologyRows(selectedWorld()).at(-1)")
            a, b = ecology["source"]["from"], ecology["source"]["to"]
            assert str(b["births"] - a["births"]) + " born" in ecology["body"]
            assert str(b["deaths"] - a["deaths"]) + " died" in ecology["body"]
            assert b["tick"] > a["tick"]
            page.click("#hold-log")
            before = page.locator("#feed").inner_text()
            page.wait_for_timeout(1800)
            assert page.locator("#feed").inner_text() == before
            assert "world continues" in page.locator("#log-status").inner_text()
            page.click("#hold-log")
            page.select_option("#log-filter", "selected")
            page.wait_for_function(
                "document.querySelector('#feed').innerText.includes('Mira')"
            )
            assert not page.locator("#feed .group-ecology").count()
            assert not page.locator("#feed").evaluate(
                "el=>[...el.querySelectorAll('h3')].some(e=>/Oren|Vale|Iris|Nova|Lyra/.test(e.innerText))"
            )
            page.uncheck("#show-beliefs")
            assert not page.locator("#feed .event-tag.claim").count()
            page.check("#show-beliefs")
            source = page.locator("#feed details.log-source").first
            source.locator("summary").click()
            assert source.locator("pre").is_visible()
            page.wait_for_timeout(1200)
            assert source.get_attribute("open") is not None
            page.select_option("#log-filter", "all")
            # Probe badges select real identities instead of pretending they are organisms.
            hit = page.evaluate(
                "Understanding.probeHits.find(x=>x.id==="
                + json.dumps(ngi["id"])
                + " && x.w>20)"
            )
            rect = page.locator("#habitat").bounding_box()
            page.mouse.click(
                rect["x"] + hit["x"] + hit["w"] / 2, rect["y"] + hit["y"] + hit["h"] / 2
            )
            page.wait_for_function("actor===" + json.dumps(ngi["id"]))
            page.wait_for_function(
                'document.querySelector("#observer-name").innerText==='
                + json.dumps(ngi["name"])
            )
            page.click("#inspect-observer")
            page.wait_for_selector("#inspector[open]")
            assert (
                "different" in page.locator("#inspector-summary").inner_text().lower()
                or "Qwen" in page.locator("#inspector-summary").inner_text()
            )
            assert not page.locator("#inspector-data").is_visible()
            page.locator(".raw-details summary").click()
            assert "Qwen3.6" in page.locator("#inspector-data").inner_text()
            page.click("#close-inspector")
            # Existing branch comparison remains accessible; no new branch is made by this test.
            page.click("#compare")
            assert page.locator("#compare-wrap").is_visible()
            page.click("#compare")
            if not original_settings["paused"]:
                page.click("#pause")
                page.wait_for_function("state.settings.paused")
            # Choose a current organism away from probe labels and inspect its actual controller.
            point = page.evaluate(
                """() => {const w=selectedWorld(),c=document.querySelector('#habitat').getBoundingClientRect(),s=Math.min(c.width,c.height)/48*zoom,ox=(c.width-48*s)/2+pan[0],oy=(c.height-48*s)/2+pan[1];for(const o of w.organisms){const x=ox+(o.x+.5)*s,y=oy+(o.y+.5)*s;if(!Understanding.probeHits.some(b=>x>=b.x&&x<=b.x+b.w&&y>=b.y&&y<=b.y+b.h))return {id:o.id,x,y};}}"""
            )
            rect = page.locator("#habitat").bounding_box()
            page.mouse.click(rect["x"] + point["x"], rect["y"] + point["y"])
            page.wait_for_selector("#inspector[open]")
            assert "Organism #" in page.locator("#inspector-title").inner_text()
            assert "Energy remaining" in page.locator("#inspector-summary").inner_text()
            assert (
                "Last recorded controller choice"
                in page.locator("#inspector-summary").inner_text()
            )
            page.screenshot(
                path=str(root / "reports/watch-first-organism.png"), full_page=True
            )
            page.click("#close-inspector")
            if not original_settings["paused"]:
                page.click("#pause")
                page.wait_for_function("!state.settings.paused")
            # Matrix and restricted perception also remain isolated when Focus view is on.
            page.click("#advanced-toggle")
            page.click("#matrix")
            page.click("#close-advanced")
            assert page.locator("#substrate").is_visible()
            page.click("#presentation")
            page.click("#advanced-toggle")
            page.click("#inhabitant")
            page.wait_for_function("view==='inhabitant' && state?.identity")
            assert not page.locator("#activity-panel").is_visible()
            assert not page.locator("#habitat").is_visible()
            assert not page.locator("#substrate").is_visible()
            assert not page.locator("#operator-tools").is_visible()
            assert not page.locator("#inspect-observer").is_visible()
            assert not page.locator("#inspector-summary").inner_text()
            assert "Qwen3.6" not in page.locator("body").inner_text()
            page.click("#operator")
            page.wait_for_function("view==='operator' && state?.worlds")
            page.click("#close-advanced")
            page.click("#presentation")
            # Actual conversations travel through the UI to each local model.
            for identity in ["mira", ngi["id"]]:
                page.locator("[data-actor=" + json.dumps(identity) + "]").click()
                page.wait_for_function(
                    "actor==="
                    + json.dumps(identity)
                    + ' && !!document.querySelector("#observer-last").innerText'
                )
                page.locator("[data-question]").first.click()
                with page.expect_response(
                    lambda r: r.url.endswith("/api/chat") and r.request.method == "POST"
                ) as response:
                    page.locator("#chat-form button[type=submit]").click()
                submitted = response.value.json()
                assert response.value.ok
                jobid = submitted["id"]
                deadline = time.monotonic() + 240
                while time.monotonic() < deadline:
                    job = next(j for j in c.get("/api/state").json()["jobs"] if j["id"] == jobid)
                    if job["status"] in ["complete", "failed", "cancelled"]:
                        break
                    time.sleep(0.5)
                assert job["status"] == "complete", job
                assert job["route"] == ("llama" if identity == "mira" else "qwen")
                requests.append(
                    {
                        "actor": identity,
                        "job": jobid,
                        "route": job["route"],
                        "status": job["status"],
                    }
                )
                print("Real UI conversation completed", requests[-1], flush=True)
            page.wait_for_timeout(1000)
            page.screenshot(
                path=str(root / "reports/watch-first-desktop.png"), full_page=True
            )
            timing = page.evaluate(
                """() => new Promise(resolve=>{let prev=performance.now();const samples=[];function f(t){samples.push(t-prev);prev=t;if(samples.length<60)requestAnimationFrame(f);else resolve({mean_ms:samples.reduce((a,b)=>a+b)/samples.length,max_ms:Math.max(...samples)})}requestAnimationFrame(f)})"""
            )
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(1000)
            assert not page.evaluate(
                "document.documentElement.scrollWidth>window.innerWidth"
            )
            page.screenshot(
                path=str(root / "reports/watch-first-mobile.png"), full_page=True
            )
            browser.close()
            assert not errors, errors
            result = {
                "verified": True,
                "plain_language_journal": True,
                "world_counter_sources_checked": True,
                "held_log": True,
                "belief_filter": True,
                "source_expansion_retained": True,
                "named_probe_selection": True,
                "organism_inspection": True,
                "restricted_view_in_focus_mode": True,
                "existing_branch_comparison": True,
                "local_model_ui_requests": requests,
                "mobile_overflow": False,
                "browser_errors": errors,
                "frame_timing": timing,
                "baseline_checkpoint": "cp-7",
            }
            (root / "reports/understanding-verification.json").write_text(
                json.dumps(result, indent=2)
            )
            print(json.dumps(result, indent=2))
    finally:
        # Preserve the user's chosen world speed, pause state, and investigator automation.
        c.post(
            "/api/control",
            json={
                k: original_settings[k] for k in ["paused", "speed", "live_autonomy"]
            },
        )
