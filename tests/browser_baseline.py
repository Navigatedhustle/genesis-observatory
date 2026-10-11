import httpx
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8780"
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1600, "height": 1100})
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE)
    page.wait_for_function(
        "document.querySelector('#stats').textContent.includes('Organisms alive')"
    )
    if page.locator("#pause").inner_text() == "Pause world":
        page.click("#pause")
    page.wait_for_timeout(1000)
    page.click("#advanced-toggle")
    page.click("#checkpoint")
    page.wait_for_timeout(1000)
    cp = page.locator("#saved").input_value()
    page.click("#branch")
    page.wait_for_timeout(1000)
    assert page.locator("#compare-wrap").is_visible()
    names = page.locator("#world option").evaluate_all("(els)=>els.map(e=>e.value)")
    a = cp + "-A"
    b = cp + "-B"
    assert a in names and b in names
    page.locator("#world").select_option(a)
    page.locator("details").filter(has=page.locator("#law")).locator("summary").click()
    page.locator("#law").select_option("growth")
    page.locator("#factor").fill("3")
    page.click("#apply")
    page.wait_for_timeout(1000)
    with httpx.Client(base_url=BASE) as c:
        s = c.get("/api/state").json()
        assert s["worlds"][a]["laws"][-1]["factor"] == 3
        assert not s["worlds"][b]["laws"]
        assert s["worlds"][a]["tick"] == s["worlds"][b]["tick"]
        for name in ["origin", a, b]:
            assert c.get("/api/replay/" + name).json()["match"]
    page.screenshot(path="reports/baseline-branches.png", full_page=True)
    page.click("#inhabitant")
    page.wait_for_timeout(1000)
    assert not page.locator("#operator-tools").is_visible()
    assert not page.locator("#habitat").is_visible()
    assert page.locator("#perception").is_visible()
    assert "operator_label" not in page.locator("#perception").inner_text()
    page.click("#operator")
    page.wait_for_timeout(1000)
    page.locator("#world").select_option("origin")
    page.wait_for_timeout(500)
    page.click("#compare")
    page.click("#close-advanced")
    page.click('[data-actor="mira"]')
    page.locator("#message").fill(
        "Your universe is simulated. What evidence would establish that claim?"
    )
    page.click("#chat-form button")
    page.wait_for_timeout(1000)
    assert page.locator("#message").input_value() == ""
    page.screenshot(path="reports/baseline-verified.png", full_page=True)
    browser.close()
assert not errors, errors
print(
    "Browser verified: live habitat, pause, checkpoint, synchronized branch pair, real growth intervention, replay, isolated inhabitant view, visitor conversation"
)
