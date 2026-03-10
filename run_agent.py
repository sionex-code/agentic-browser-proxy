#!/usr/bin/env python
"""
Yaser Agent Launcher — Skill-Based Autonomous Browser Agent
Loads .yaser/<site>.md skill files and runs the agent with profile management,
duplicate tracking, and site-specific instructions.

Usage:
    python run_agent.py --skill quora "answer 5 questions about Python" 0
    python run_agent.py "https://google.com" "search shoes" 50
"""

import asyncio
import sys
import os
import subprocess
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Check and setup virtual environment if needed
venv_path = Path(script_dir) / ".venv"
if not venv_path.exists():
    print("📦 Setting up virtual environment (first time only)...")
    try:
        subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
        if sys.platform == "win32":
            pip_path = venv_path / "Scripts" / "pip.exe"
        else:
            pip_path = venv_path / "bin" / "pip"
        requirements_file = Path(script_dir) / "requirements.txt"
        if requirements_file.exists():
            print("📥 Installing dependencies...")
            subprocess.run([str(pip_path), "install", "-r", str(requirements_file)], check=True)
        print("🌐 Installing browser...")
        subprocess.run([str(pip_path), "install", "patchright"], check=True)
        if sys.platform == "win32":
            python_path = venv_path / "Scripts" / "python.exe"
        else:
            python_path = venv_path / "bin" / "python"
        subprocess.run([str(python_path), "-m", "patchright", "install", "chromium"], check=True)
        print("✅ Setup complete!\n")
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        print("Please run manually: pip install -r requirements.txt && patchright install chromium")
        sys.exit(1)
else:
    print("✅ Virtual environment found, skipping setup\n")

from patchright.async_api import async_playwright
from agentic_browser_v2.agent import BrowserAgent
from agentic_browser_v2.skill_loader import load_skill
from agentic_browser_v2.profile_manager import get_session_dir, get_next_profile
from agentic_browser_v2.duplicate_tracker import DuplicateTracker


async def run_with_skill(skill_name: str, goal: str, max_steps: int = 1000):
    """
    Run the agent with a .yaser/<skill_name>.md skill file.
    Handles profile switching by restarting the browser with a new session directory.
    """
    # Load skill config
    skill_config = load_skill(skill_name)
    if not skill_config:
        print(f"\n❌ Skill file not found: .yaser/{skill_name}.md")
        print(f"   Create it with profiles, rules, and instructions.")
        sys.exit(1)

    start_url = skill_config.start_url
    if not start_url:
        start_url = f"https://www.{skill_config.site}/"

    # Handle unlimited steps
    is_unlimited = max_steps <= 0
    actual_max_steps = 999999 if is_unlimited else max_steps

    # Initialize duplicate tracker
    tracker = None
    if skill_config.tracking.completed_file:
        tracker_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            skill_config.tracking.completed_file
        )
        tracker = DuplicateTracker(tracker_path)

    # Profile switching loop
    current_profile = skill_config.active_profile
    while True:
        session_dir = get_session_dir(skill_config, current_profile)

        print("╔══════════════════════════════════════════════════╗")
        print("║       🤖 YASER AGENT — Skill-Based              ║")
        print("╠══════════════════════════════════════════════════╣")
        print(f"║  Skill: {skill_name:<41}║")
        print(f"║  Profile: {current_profile:<39}║")
        print(f"║  Session: {os.path.basename(session_dir):<39}║")
        print("╚══════════════════════════════════════════════════╝")

        print(f"\n  🌐 URL:     {start_url}")
        print(f"  🎯 Goal:    {goal}")
        print(f"  📊 Steps:   {'unlimited' if is_unlimited else max_steps}")
        print(f"  👤 Profile: {current_profile}")
        if tracker:
            print(f"  📖 Tracked: {tracker.count()} completed items")

        async with async_playwright() as p:
            browser = await p.chromium.launch_persistent_context(
                user_data_dir=session_dir,
                channel="chrome",
                headless=False,
                no_viewport=True,
            )
            page = browser.pages[0]
            page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))

            await page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            # If ask_user_to_login is true, pause for manual login
            if skill_config.rules.ask_user_to_login:
                print("\n  ⏸ AI paused. You can now log into your account if needed.")
                await asyncio.to_thread(
                    input,
                    "  ▶ Press Enter here when you are ready for the AI to take control... "
                )

            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

            agent = BrowserAgent(
                page, browser, goal,
                max_steps=actual_max_steps,
                session_id=session_id,
                skill_config=skill_config,
                duplicate_tracker=tracker,
            )
            agent.current_profile = current_profile

            result = await agent.run()

            print(f"\n{'═'*70}")
            if result == "switch_profile":
                next_profile = agent._switch_to_profile
                if next_profile:
                    print(f"  🔄 Switching from {current_profile} → {next_profile}")
                    current_profile = next_profile
                else:
                    print("  ⚠ No next profile available, stopping.")
                    await browser.close()
                    break
            elif result is True:
                print("  ✅ Task completed successfully!")
                print(f"  📁 Session log: memory_session_{session_id}.txt")
                await browser.close()
                break
            else:
                print("  ⚠ Task did not complete fully")
                print(f"  📁 Session log: memory_session_{session_id}.txt")
                await browser.close()
                break

            print(f"{'═'*70}")
            await browser.close()
            # Small delay before reopening with new profile
            await asyncio.sleep(2)


async def run_generic(start_url: str, goal: str, max_steps: int = 1000):
    """
    Run the agent without a skill file (generic mode — same as before).
    """
    if not start_url.startswith(("http://", "https://")):
        start_url = "https://" + start_url

    is_unlimited = max_steps <= 0
    actual_max_steps = 999999 if is_unlimited else max_steps

    print("╔══════════════════════════════════════════════════╗")
    print("║       🤖 AGENTIC BROWSER v2 — Enhanced          ║")
    print("╠══════════════════════════════════════════════════╣")
    print("║  • 30+ actions  • human-like typing             ║")
    print("║  • indexed elements  • error recovery           ║")
    print("╚══════════════════════════════════════════════════╝")

    print(f"\n  🌐 URL:   {start_url}")
    print(f"  🎯 Goal:  {goal}")
    print(f"  📊 Steps: {'unlimited' if is_unlimited else max_steps}")

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="session",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )
        page = browser.pages[0]
        page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))

        await page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        agent = BrowserAgent(page, browser, goal, max_steps=actual_max_steps, session_id=session_id)
        success = await agent.run()

        print(f"\n{'═'*70}")
        if success:
            print("  ✅ Task completed successfully!")
        else:
            print("  ⚠ Task did not complete fully")
        print(f"  📁 Session log: memory_session_{session_id}.txt")
        print(f"{'═'*70}")

        await browser.close()


if __name__ == "__main__":
    # Parse command line arguments
    args = sys.argv[1:]

    if not args:
        print("Usage:")
        print('  python run_agent.py --skill <site> "<goal>" [max_steps]')
        print('  python run_agent.py "<url>" "<goal>" [max_steps]')
        print()
        print("Examples (skill mode):")
        print('  python run_agent.py --skill quora "answer 5 questions about Python" 0')
        print('  python run_agent.py --skill twitter "post a tweet about AI" 0')
        print()
        print("Examples (generic mode):")
        print('  python run_agent.py "google.com" "search for python tutorials" 50')
        sys.exit(1)

    if args[0] == "--skill":
        if len(args) < 3:
            print('Usage: python run_agent.py --skill <site> "<goal>" [max_steps]')
            sys.exit(1)
        skill_name = args[1]
        goal = args[2]
        steps = int(args[3]) if len(args) > 3 else 0
        asyncio.run(run_with_skill(skill_name, goal, steps))
    else:
        if len(args) < 2:
            print('Usage: python run_agent.py "<url>" "<goal>" [max_steps]')
            sys.exit(1)
        url = args[0]
        goal = args[1]
        steps = int(args[2]) if len(args) > 2 else 1000
        asyncio.run(run_generic(url, goal, steps))
