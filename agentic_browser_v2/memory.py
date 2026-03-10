# ─────────────────────────── Agent Memory ───────────────────────────

import json
import os
from datetime import datetime
from difflib import SequenceMatcher

from .config import MEMORY_FILE


class AgentMemory:
    """Session-specific persistent memory with progress tracking."""

    def __init__(self, path=MEMORY_FILE, session_id=None):
        # Create session-specific memory file
        self.main_memory_path = path  # Always keep reference to main memory.txt
        
        if session_id:
            base_dir = os.path.dirname(path) or "."
            base_name = os.path.splitext(os.path.basename(path))[0]
            self.path = os.path.join(base_dir, f"{base_name}_session_{session_id}.txt")
            self.session_id = session_id
        else:
            self.path = path
            self.session_id = None

        self.data = self._load()
        self._init_session_data()
        
        # Load main memory for cross-session persistence
        self.main_memory_data = self._load_main_memory()
        
        # Cursor position tracking - load from file if exists
        self.cursor_position = self.data.get("_cursor_position", {"x": 100, "y": 100})

    def _init_session_data(self):
        """Initialize session tracking data."""
        if "_session" not in self.data:
            self.data["_session"] = {
                "session_id": self.session_id,
                "started_at": datetime.now().isoformat(),
                "goal": "",
                "completed_steps": [],
                "remaining_tasks": [],
                "last_action": "",
                "status": "in_progress"
            }

    def _load(self):
        """Load memory from file."""
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _load_main_memory(self):
        """Load the main memory.txt file for cross-session persistence."""
        if os.path.exists(self.main_memory_path):
            try:
                with open(self.main_memory_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_main_memory(self):
        """Save to the main memory.txt file."""
        try:
            with open(self.main_memory_path, "w", encoding="utf-8") as f:
                json.dump(self.main_memory_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"  ⚠ Main memory save error: {e}")

    def save(self):
        """Save memory to file."""
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"  ⚠ Memory save error: {e}")

    def log_progress(self, step_num, action_type, description, status="success"):
        """Log progress after each action."""
        progress_entry = {
            "step": step_num,
            "action": action_type,
            "description": description,
            "status": status,
            "timestamp": datetime.now().isoformat()
        }

        if "_session" in self.data:
            self.data["_session"]["completed_steps"].append(progress_entry)
            self.data["_session"]["last_action"] = description
            self.data["_session"]["updated_at"] = datetime.now().isoformat()

        self.save()

    def update_remaining_tasks(self, tasks):
        """Update the list of remaining tasks."""
        if "_session" in self.data:
            self.data["_session"]["remaining_tasks"] = tasks
            self.save()

    def set_goal(self, goal):
        """Set the session goal."""
        if "_session" in self.data:
            self.data["_session"]["goal"] = goal
            self.save()

    def mark_completed(self):
        """Mark session as completed."""
        if "_session" in self.data:
            self.data["_session"]["status"] = "completed"
            self.data["_session"]["completed_at"] = datetime.now().isoformat()
            self.save()

    def mark_failed(self, reason=""):
        """Mark session as failed."""
        if "_session" in self.data:
            self.data["_session"]["status"] = "failed"
            self.data["_session"]["failure_reason"] = reason
            self.data["_session"]["failed_at"] = datetime.now().isoformat()
            self.save()

    def get_session_summary(self):
        """Get a summary of the current session progress."""
        if "_session" not in self.data:
            return "No session data available."

        session = self.data["_session"]
        completed = len(session.get("completed_steps", []))
        remaining = session.get("remaining_tasks", [])

        summary = f"Session {session.get('session_id', 'unknown')}\n"
        summary += f"Goal: {session.get('goal', 'N/A')}\n"
        summary += f"Status: {session.get('status', 'unknown')}\n"
        summary += f"Completed steps: {completed}\n"

        if completed > 0:
            summary += f"Last action: {session.get('last_action', 'N/A')}\n"

        if remaining:
            summary += f"Remaining tasks: {', '.join(remaining)}\n"

        return summary

    def load_previous_session(self):
        """Load the most recent session file to resume progress."""
        base_dir = os.path.dirname(self.path) or "."
        base_name = os.path.splitext(os.path.basename(MEMORY_FILE))[0]

        # Find all session files
        session_files = []
        try:
            for file in os.listdir(base_dir):
                if file.startswith(f"{base_name}_session_") and file.endswith(".txt"):
                    full_path = os.path.join(base_dir, file)
                    session_files.append((full_path, os.path.getmtime(full_path)))
        except Exception:
            return None

        if not session_files:
            return None

        # Get most recent session file
        latest_session = max(session_files, key=lambda x: x[1])[0]

        try:
            with open(latest_session, "r", encoding="utf-8") as f:
                prev_data = json.load(f)
                if "_session" in prev_data:
                    return prev_data["_session"]
        except Exception:
            pass

        return None

    def read(self, domain):
        """Read notes for a domain + general notes from both session and main memory."""
        notes = []
        
        # Read from main memory first (cross-session learnings)
        if domain in self.main_memory_data:
            for entry in self.main_memory_data[domain]:
                notes.append(f"[{domain}] {entry['note']}")
        if "_general" in self.main_memory_data:
            for entry in self.main_memory_data["_general"]:
                notes.append(f"[general] {entry['note']}")
        
        # Then read from session memory (avoid duplicates)
        if domain in self.data:
            for entry in self.data[domain]:
                note_text = f"[{domain}] {entry['note']}"
                if note_text not in notes:
                    notes.append(note_text)
        if "_general" in self.data:
            for entry in self.data["_general"]:
                note_text = f"[general] {entry['note']}"
                if note_text not in notes:
                    notes.append(note_text)
        
        return notes

    def write(self, domain, note):
        """Write a short note under a domain to both session and main memory."""
        note = note[:150]  # enforce max length
        
        # Save to session memory
        if domain not in self.data:
            self.data[domain] = []
        # Avoid duplicates and near-duplicates (>80% similar)
        existing = [e["note"] for e in self.data[domain]]
        if note not in existing and not self._is_similar(note, existing):
            self.data[domain].append({
                "note": note,
                "time": datetime.now().isoformat()
            })
            # Keep max 20 per domain
            if len(self.data[domain]) > 20:
                self.data[domain] = self.data[domain][-20:]
            self.save()
        
        # ALSO save to main memory.txt for cross-session persistence
        if self.session_id:  # Only if we're in a session
            if domain not in self.main_memory_data:
                self.main_memory_data[domain] = []
            # Avoid duplicates and near-duplicates in main memory too
            main_existing = [e["note"] for e in self.main_memory_data[domain]]
            if note not in main_existing and not self._is_similar(note, main_existing):
                self.main_memory_data[domain].append({
                    "note": note,
                    "time": datetime.now().isoformat()
                })
                # Keep max 20 per domain
                if len(self.main_memory_data[domain]) > 20:
                    self.main_memory_data[domain] = self.main_memory_data[domain][-20:]
                self._save_main_memory()
                print(f"  💾 Saved learning to main memory: [{domain}] {note[:80]}")

    def _is_similar(self, note, existing_notes, threshold=0.80):
        """Check if a note is too similar to any existing note."""
        for existing in existing_notes:
            if SequenceMatcher(None, note.lower(), existing.lower()).ratio() > threshold:
                return True
        return False

    def track_domain_progress(self, domain, step_num, action_desc, status="success"):
        """Track progress per domain (separate from session progress)."""
        domain_key = f"_progress_{domain}"
        if domain_key not in self.data:
            self.data[domain_key] = []
        self.data[domain_key].append({
            "step": step_num,
            "action": action_desc,
            "status": status,
            "time": datetime.now().isoformat()
        })
        # Keep last 50 domain progress entries
        if len(self.data[domain_key]) > 50:
            self.data[domain_key] = self.data[domain_key][-50:]
        self.save()

    def get_domain_progress(self, domain):
        """Get progress summary for a specific domain."""
        domain_key = f"_progress_{domain}"
        entries = self.data.get(domain_key, [])
        if not entries:
            return "No progress tracked for this domain yet."
        
        total = len(entries)
        successes = sum(1 for e in entries if e.get("status") == "success")
        failures = total - successes
        last_action = entries[-1].get("action", "N/A") if entries else "N/A"
        
        return f"Domain progress: {total} actions ({successes} ok, {failures} failed). Last: {last_action}"

    def cleanup_stale_notes(self):
        """Remove very old notes from main memory to keep it lean."""
        cleaned = False
        for domain in list(self.main_memory_data.keys()):
            if domain.startswith("_"):
                continue  # Skip system keys
            notes = self.main_memory_data[domain]
            if len(notes) > 30:
                self.main_memory_data[domain] = notes[-20:]
                cleaned = True
        if cleaned:
            self._save_main_memory()
            print("  🧹 Cleaned up stale memory notes")

    def save_cursor_position(self, x, y):
        """Save cursor position for restoration after page load."""
        self.cursor_position = {"x": x, "y": y}
        # Persist to file immediately
        self.data["_cursor_position"] = self.cursor_position
        self.save()

    def get_cursor_position(self):
        """Get saved cursor position."""
        # Always load from file to get latest position
        self.data = self._load()
        return self.data.get("_cursor_position", {"x": 100, "y": 100})
