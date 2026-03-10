# ─────────────────────────── Main Entry Point ───────────────────────────

import asyncio
from datetime import datetime
from patchright.async_api import async_playwright

from .config import WAIT_FOR_LOGIN
from .agent import BrowserAgent


async def main():
    print("╔══════════════════════════════════════════════════╗")
    print("║       🤖 AGENTIC BROWSER v2 — Enhanced          ║")
    print("╠══════════════════════════════════════════════════╣")
    print("║  • 30 actions  • human-like typing              ║")
    print("║  • indexed elements  • error recovery           ║")
    print("║  • tabs, iframes, dialogs, dropdowns            ║")
    print("╚══════════════════════════════════════════════════╝")

    start_url = input("\nStart URL (Enter for google.com): ").strip()
    if not start_url:
        start_url = "https://www.google.com/"
    elif not start_url.startswith(("http://", "https://")):
        start_url = "https://" + start_url

    goal = input("Enter your goal: ").strip()
    if not goal:
        goal = "find shoes under 2000 pkr"

    max_steps = input("Max steps (Enter for 50): ").strip()
    max_steps = int(max_steps) if max_steps.isdigit() else 50

    print(f"\n  🌐 URL:   {start_url}")
    print(f"  🎯 Goal:  {goal}")
    print(f"  📊 Steps: {max_steps}")

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="test",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )
        page = browser.pages[0]

        # Set up dialog auto-handler (prevent dialogs from blocking)
        page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))

        await page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        
        if WAIT_FOR_LOGIN:
            print("\n  ⏸ AI paused. You can now log into any accounts or solve CAPTCHAs in the browser.")
            await asyncio.to_thread(input, "  ▶ Press Enter here when you are ready for the AI to take control... ")

        # Generate session ID
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        agent = BrowserAgent(page, browser, goal, max_steps=max_steps, session_id=session_id)
        success = await agent.run()

        print(f"\n{'═'*70}")
        if success:
            print("  ✅ Task completed successfully!")
        else:
            print("  ⚠ Task did not complete fully")
        print(f"  📁 Session log: memory_session_{session_id}.txt")
        print(f"{'═'*70}")

        input("\nPress Enter to close browser...")
        await browser.close()
