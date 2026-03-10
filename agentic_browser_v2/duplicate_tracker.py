# ─────────────────────────── Duplicate Tracker ───────────────────────────
# File-backed set for tracking completed work items (URLs, question IDs, etc.)
# Prevents the agent from repeating the same actions.

import os
from typing import Set


class DuplicateTracker:
    """Tracks completed items in a simple text file (one item per line).
    
    Loads all items into memory on init for fast O(1) lookups.
    Appends new items to file immediately for persistence.
    """

    def __init__(self, filepath: str):
        """Initialize tracker with a file path.
        
        Args:
            filepath: Path to the tracking file. Created if it doesn't exist.
        """
        self.filepath = filepath
        self._items: Set[str] = set()
        self._load()

    def _load(self):
        """Load existing items from file into memory."""
        if not os.path.exists(self.filepath):
            # Ensure parent directory exists
            parent = os.path.dirname(self.filepath)
            if parent:
                os.makedirs(parent, exist_ok=True)
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                for line in f:
                    item = line.strip()
                    if item:
                        self._items.add(item)
            print(f"  📖 Loaded {len(self._items)} completed items from {os.path.basename(self.filepath)}")
        except Exception as e:
            print(f"  ⚠ Error loading tracking file: {e}")

    def is_done(self, item: str) -> bool:
        """Check if an item has already been completed.
        
        Args:
            item: The item to check (URL, question ID, etc.)
        
        Returns:
            True if already completed.
        """
        return item.strip() in self._items

    def mark_done(self, item: str):
        """Mark an item as completed — adds to memory and appends to file.
        
        Args:
            item: The item to mark as done.
        """
        item = item.strip()
        if not item:
            return
        if item in self._items:
            return  # Already tracked

        self._items.add(item)

        # Ensure parent directory exists
        parent = os.path.dirname(self.filepath)
        if parent:
            os.makedirs(parent, exist_ok=True)

        try:
            with open(self.filepath, "a", encoding="utf-8") as f:
                f.write(item + "\n")
            print(f"  ✅ Tracked: {item[:80]}")
        except Exception as e:
            print(f"  ⚠ Error writing to tracking file: {e}")

    def count(self) -> int:
        """Return number of completed items."""
        return len(self._items)

    def get_all(self) -> Set[str]:
        """Return a copy of all completed items."""
        return self._items.copy()

    def search(self, query: str) -> list:
        """Search completed items for partial matches.
        
        Args:
            query: Substring to search for.
        
        Returns:
            List of matching items.
        """
        query_lower = query.lower()
        return [item for item in self._items if query_lower in item.lower()]
