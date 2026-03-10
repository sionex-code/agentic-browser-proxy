#!/usr/bin/env python
"""
Autonomous AI Agent Launcher with Arguments
Launches the agentic browser with specified parameters.
"""

import asyncio
import sys
import os
import subprocess
from datetime import datetime
from pathlib import Path

# Add project directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Check and setup virtual environment if needed
venv_path = Path(script_dir) / ".venv"
if not venv_path.exists():
    print("📦 Setting up virtual environment (first time only)...")
    try:
        # Create venv
        subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
        
        # Determine pip path
        if sys.platform == "win32":
            pip_path = venv_path / "Scripts" / "pip.exe"
        else:
            pip_path = venv_path / "bin" / "pip"
        
        # Install requirements
        requirements_file = Path(script_dir) / "requirements.txt"
        if requirements_file.exists():
            print("📥 Installing dependencies...")
            subprocess.run([str(pip_path), "install", "-r", str(requirements_file)], check=True)
        
        # Install patchright browsers
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


async def run_agent(start_url: str, goal: str, max_steps: int = 1000):
    """
    Run the autonomous AI agent with specified parameters.
    
    Args:
        start_url: Starting URL for the browser
        goal: The goal/task for the agent to accomplish
        max_steps: Maximum number of steps (0 or negative = unlimited)
    """
    print("╔══════════════════════════════════════════════════╗")
    print("║          🐦 TWITTER AGENT — Autonomous          ║")
    print("╠══════════════════════════════════════════════════╣")
    print("║  • Twitter/X automation  • Follow & Post        ║")
    print("║  • Search & Engage  • Fully automated           ║")
    print("╚══════════════════════════════════════════════════╝")

    # Force Twitter/X URL
    if "x.com" not in start_url and "twitter.com" not in start_url:
        print("\n⚠ WARNING: This agent only works with Twitter/X (x.com)")
        print("  Forcing URL to x.com...")
        start_url = "https://x.com"
    elif not start_url.startswith(("http://", "https://")):
        start_url = "https://" + start_url

    # Handle unlimited steps
    is_unlimited = max_steps <= 0
    display_steps = "unlimited" if is_unlimited else str(max_steps)
    actual_max_steps = 999999 if is_unlimited else max_steps

    print(f"\n  🌐 URL:   {start_url}")
    print(f"  🎯 Goal:  {goal}")
    print(f"  📊 Steps: {display_steps}")

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="session",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )
        page = browser.pages[0]

        # Set up dialog auto-handler
        page.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))

        await page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        # Generate session ID
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
    if len(sys.argv) < 3:
        print("Usage: python run_agent.py <url> <goal> [max_steps]")
        print("\nExamples:")
        print('  python run_agent.py "google.com" "search for python tutorials" 50')
        print('  python run_agent.py "amazon.com" "find shoes under $100" 0  # unlimited steps')
        sys.exit(1)
    
    url = sys.argv[1]
    goal = sys.argv[2]
    steps = int(sys.argv[3]) if len(sys.argv) > 3 else 1000
    
    asyncio.run(run_agent(url, goal, steps))
