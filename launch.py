#!/usr/bin/env python
"""
Simple launcher for the agentic browser.
Can be run from anywhere in the project.
"""

import asyncio
import sys
import os

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Add it to the Python path
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Now import and run
from agentic_browser_v2.main import main

if __name__ == "__main__":
    print("🚀 Starting Agentic Browser v2...")
    print(f"📁 Working directory: {os.getcwd()}")
    print(f"📂 Script directory: {script_dir}")
    print()
    
    asyncio.run(main())
