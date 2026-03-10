"""Allow running the package directly with: python -m agentic_browser_v2"""
import asyncio
from .main import main

if __name__ == "__main__":
    asyncio.run(main())
