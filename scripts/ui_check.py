"""Click through the running app in a real browser and save screenshots (desktop and phone).

Usage (any OS with Playwright + Microsoft Edge):  python scripts/ui_check.py [base_url] [out_dir]
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else ROOT / "docs" / "screens")
OUT.mkdir(parents=True, exist_ok=True)
ENV = dict(line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines() if "=" in line and not line.startswith("#"))


def settle(page, ms=2500):
    page.wait_for_selector("[data-testid='stApp']", timeout=30000)
    page.wait_for_timeout(ms)
    try:
        page.wait_for_selector("[data-testid='stStatusWidget']", state="detached", timeout=60000)
    except Exception:
        pass
    page.wait_for_timeout(800)


def login(page, who, password):
    page.goto(BASE)
    settle(page)
    if who == "chhaya.gupta":
        page.get_by_text("Ms Chhaya Gupta · CX reviewer").click()
        settle(page, 1200)
    page.get_by_role("textbox", name="Password").fill(password)
    page.get_by_role("button", name="Sign in as").click()
    settle(page, 4000)


def nav(page, label):
    """Open a screen through the menu (a reload would start a new, signed-out session)."""
    link = page.locator("[data-testid='stSidebarNav'] a", has_text=label)
    if page.viewport_size["width"] < 700:  # phone: the menu is collapsed
        for sel in ["[data-testid='stExpandSidebarButton']", "[data-testid='stSidebarCollapsedControl'] button",
                    "[data-testid='collapsedControl']"]:
            if page.locator(sel).count():
                page.locator(sel).first.click()
                page.wait_for_timeout(800)
                break
    link.click()
    settle(page, 4000)


def shot(page, name):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
    print("saved", name)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    for device, size in [("desktop", {"width": 1366, "height": 900}), ("phone", {"width": 390, "height": 844})]:
        ctx = browser.new_context(viewport=size, device_scale_factor=1, is_mobile=device == "phone")
        page = ctx.new_page()
        page.goto(BASE); settle(page); shot(page, f"{device}-0-login")

        login(page, "neha", ENV["NEHA_PASSWORD"])
        shot(page, f"{device}-1-neha-queue")
        nav(page, "Delay scorecard"); shot(page, f"{device}-2-neha-scorecard")
        menu = page.locator("[data-testid='stSidebarNav'] a").all_inner_texts()
        print(f"{device} Neha menu:", menu)
        ctx.close()

        ctx = browser.new_context(viewport=size, device_scale_factor=1, is_mobile=device == "phone")
        page = ctx.new_page()
        login(page, "chhaya.gupta", ENV["CHHAYA_PASSWORD"])
        shot(page, f"{device}-3-chhaya-guidance")
        print(f"{device} Chhaya menu:", page.locator("[data-testid='stSidebarNav'] a").all_inner_texts())
        ctx.close()
    browser.close()
