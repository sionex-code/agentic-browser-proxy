# ─────────────────────────── Configuration ───────────────────────────

# Toggle for reading AI thoughts aloud using edge-playback
READ_THOUGHTS = True
THOUGHT_SPEECH_RATE = "+30%"  # +100% is 2x faster. Change to "+50%" for 1.5x, etc.
WAIT_FOR_LOGIN = False  # If True, waits for user to press Enter before AI takes control
MEMORY_FILE = "memory.txt"  # Persistent memory file for domain-specific lessons
LONG_RUN_MODE = True  # If True, runs with virtually unlimited steps for overnight tasks
VISION_FAILURE_THRESHOLD = 4  # After this many consecutive failures, capture a screenshot for OCR
OCR_API_KEY = "cdfa35baed114b39ae381240bb53df94.2VzyxJbKaY1RnwJ3"  # ZhipuAI glm-ocr API key
