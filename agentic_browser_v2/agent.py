# ─────────────────────────── Browser Agent ───────────────────────────

import asyncio
import base64
import io
import json
import re
import subprocess
import time
import requests
from datetime import datetime
from urllib.parse import urlparse
from PIL import Image

from .config import (
    READ_THOUGHTS, THOUGHT_SPEECH_RATE, LONG_RUN_MODE,
    VISION_FAILURE_THRESHOLD, OCR_API_KEY
)
from .ai_client import send_prompt
from .prompts import SYSTEM_PROMPT
from .page_scripts import (
    EXTRACT_ELEMENTS_JS, PAGE_STATE_JS, EXTRACT_PAGE_TEXT_JS,
    INIT_CURSOR_JS, RESTORE_CURSOR_POSITION_JS, GET_CURSOR_POSITION_JS
)
from .memory import AgentMemory
from .actions import do_action


class BrowserAgent:
    def __init__(self, page, context, goal, max_steps=50, session_id=None,
                 skill_config=None, duplicate_tracker=None):
        self.page = page
        self.context = context  # browser context for tab management
        self.goal = goal
        self.action_history = []
        self.error_history = []
        self.max_steps = max_steps
        self.step_count = 0
        self.consecutive_failures = 0
        self.max_consecutive_failures = 5
        self.in_iframe = False
        self.pending_dialog = None
        self.pending_popup = None  # Store info about new popup windows
        self.start_time = None
        
        # Skill system integration
        self.skill_config = skill_config
        self.duplicate_tracker = duplicate_tracker
        self.answers_count = 0
        self.current_profile = skill_config.active_profile if skill_config else None
        self._switch_to_profile = None  # Set by switch_profile action
        
        # Create session-specific memory
        if not session_id:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_id = session_id
        self.memory = AgentMemory(session_id=session_id)
        self.memory.set_goal(goal)
        
        # Load previous session if exists
        prev_session = self.memory.load_previous_session()
        if prev_session and prev_session.get("status") != "completed":
            print(f"  📂 Found previous session: {prev_session.get('session_id')}")
            print(f"  📊 Previous progress: {len(prev_session.get('completed_steps', []))} steps completed")
            if prev_session.get('last_action'):
                print(f"  📝 Last action: {prev_session.get('last_action')}")
        
        self.vision_context = None  # OCR text from screenshot, set on repeated failures

        # Clean up stale memory notes on init
        self.memory.cleanup_stale_notes()

        # Set up dialog handler
        self.page.on("dialog", self._handle_dialog)
        
        # Set up popup handler - automatically detect new windows/tabs
        self.page.on("popup", self._handle_popup)
        
        # Set up page load handler to reinitialize cursor
        self.page.on("load", self._on_page_load)

    async def _on_page_load(self):
        """Reinitialize cursor on page load and restore position."""
        try:
            # Small delay to ensure page is ready
            await asyncio.sleep(0.5)
            
            # Initialize cursor script
            await self.page.evaluate(INIT_CURSOR_JS)
            
            # Restore cursor position from memory
            cursor_pos = self.memory.get_cursor_position()
            x, y = cursor_pos["x"], cursor_pos["y"]
            
            # Use the function call syntax to restore position
            await self.page.evaluate(f"window.__move_cursor && window.__move_cursor({x}, {y})")
            
            print(f"  🖱 Cursor restored to position ({x}, {y})")
        except Exception as e:
            print(f"  ⚠ Cursor initialization error: {e}")

    def _handle_dialog(self, dialog):
        """Store dialog info for AI to handle."""
        self.pending_dialog = {
            "type": dialog.type,
            "message": dialog.message,
            "default": dialog.default_value
        }
        print(f"  📋 Dialog detected: [{dialog.type}] {dialog.message}")

    def _handle_popup(self, popup):
        """Handle popup windows (e.g., 'Sign in with Google' popups)."""
        try:
            popup_url = popup.url
            popup_title = ""
            # Try to get title, but don't block if it's not ready yet
            try:
                popup_title = popup.title if hasattr(popup, 'title') else ""
            except:
                pass
            
            self.pending_popup = {
                "url": popup_url,
                "title": popup_title,
                "page": popup
            }
            print(f"  🪟 Popup window detected: {popup_url}")
            
            # Add popup to context pages list (it's automatically added by Playwright)
            # The AI can now switch to it using switch_tab or use switch_to_popup action
        except Exception as e:
            print(f"  ⚠ Error handling popup: {e}")

    def _resolve_selector(self, action):
        """Resolve element index to a reliable selector, or return raw selector."""
        if "index" in action:
            idx = action["index"]
            return f"[data-agent-idx='{idx}']", idx
        return action.get("selector", ""), None

    async def _inject_indices(self):
        """Inject data-agent-idx attributes so we can target elements by index."""
        await self.page.evaluate("""
        (() => {
          // Remove old indices
          document.querySelectorAll('[data-agent-idx]').forEach(el =>
            el.removeAttribute('data-agent-idx')
          );

          const INTERACTIVE_TAGS = new Set([
            'A', 'BUTTON', 'INPUT', 'TEXTAREA', 'SELECT', 'DETAILS', 'SUMMARY'
          ]);
          const INTERACTIVE_ROLES = new Set([
            'button', 'link', 'tab', 'menuitem', 'checkbox', 'radio', 'switch',
            'textbox', 'combobox', 'searchbox', 'option', 'menuitemcheckbox',
            'menuitemradio', 'slider', 'spinbutton', 'treeitem', 'listbox'
          ]);

          const isVisible = el => {
            const rect = el.getBoundingClientRect();
            const style = getComputedStyle(el);
            return (
              rect.width > 0 && rect.height > 0 &&
              rect.bottom >= 0 && rect.right >= 0 &&
              rect.top <= (window.innerHeight || document.documentElement.clientHeight) &&
              rect.left <= (window.innerWidth || document.documentElement.clientWidth) &&
              style.visibility !== 'hidden' && style.display !== 'none' &&
              parseFloat(style.opacity) > 0
            );
          };

          const isInteractive = el => {
            if (INTERACTIVE_TAGS.has(el.tagName)) return true;
            const role = el.getAttribute('role');
            if (role && INTERACTIVE_ROLES.has(role)) return true;
            if (el.hasAttribute('onclick') || el.hasAttribute('tabindex')) return true;
            if (el.hasAttribute('contenteditable') && el.getAttribute('contenteditable') !== 'false') return true;
            const cursor = getComputedStyle(el).cursor;
            if (cursor === 'pointer' && el.tagName !== 'HTML' && el.tagName !== 'BODY') return true;
            return false;
          };

          const allElements = [...document.querySelectorAll('*')].filter(isVisible);
          const interactive = allElements.filter(isInteractive);
          const nonInteractive = allElements.filter(el => {
            if (isInteractive(el)) return false;
            const text = el.innerText?.trim();
            const tag = el.tagName;
            return (
              (tag === 'H1' || tag === 'H2' || tag === 'H3' || tag === 'H4' ||
               tag === 'P' || tag === 'SPAN' || tag === 'LI' || tag === 'TD' ||
               tag === 'TH' || tag === 'LABEL' || tag === 'LEGEND' ||
               tag === 'IMG' || tag === 'IFRAME') &&
              (text || tag === 'IMG' || tag === 'IFRAME')
            );
          });

          let idx = 0;
          for (const el of interactive) el.setAttribute('data-agent-idx', idx++);
          for (const el of nonInteractive) el.setAttribute('data-agent-idx', idx++);
        })();
        """)
        
        # Also sync cursor position from page to memory
        try:
            cursor_pos = await self.page.evaluate(GET_CURSOR_POSITION_JS)
            if cursor_pos and isinstance(cursor_pos, dict):
                self.memory.save_cursor_position(cursor_pos.get("x", 0), cursor_pos.get("y", 0))
        except Exception:
            pass  # Silently fail if cursor script not loaded

    async def get_page_state(self):
        """Get current page state summary."""
        try:
            state_json = await self.page.evaluate(PAGE_STATE_JS)
            state = json.loads(state_json)

            # Add tab info
            pages = self.context.pages
            state["tabs"] = [{"index": i, "url": p.url, "title": await p.title() if p != self.page else state["title"]}
                             for i, p in enumerate(pages)]
            state["currentTabIndex"] = pages.index(self.page) if self.page in pages else 0
            state["tabCount"] = len(pages)

            # Add dialog info
            if self.pending_dialog:
                state["pendingDialog"] = self.pending_dialog

            # Add popup info
            if self.pending_popup:
                state["pendingPopup"] = {
                    "url": self.pending_popup["url"],
                    "title": self.pending_popup["title"]
                }

            # Add iframe flag
            state["inIframe"] = self.in_iframe

            return state
        except Exception as e:
            return {"title": "Unknown", "url": self.page.url, "error": str(e)}

    async def get_visible_elements(self):
        """Extract visible elements with indices."""
        try:
            await self._inject_indices()
            result = await self.page.evaluate(EXTRACT_ELEMENTS_JS)
            return json.loads(result)
        except Exception as e:
            print(f"  ⚠ Element extraction error: {e}")
            return []

    async def get_page_text_snippets(self):
        """Extract partial text snippets from visible text elements on the page."""
        try:
            result = await self.page.evaluate(EXTRACT_PAGE_TEXT_JS)
            return json.loads(result)
        except Exception as e:
            print(f"  ⚠ Page text extraction error: {e}")
            return []

    async def _capture_vision_snapshot(self):
        """Take a screenshot, compress it, and send to ZhipuAI OCR API for vision fallback."""
        try:
            from zai import ZhipuAiClient
            # Take screenshot using Playwright
            screenshot_bytes = await self.page.screenshot(type="jpeg", quality=70)
            
            # Further compress if needed to keep payload small
            img = Image.open(io.BytesIO(screenshot_bytes))
            # Resize if too large
            if img.width > 1280 or img.height > 1280:
                img.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
            
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=60)
            compressed_bytes = buffer.getvalue()
            
            base64_data = base64.b64encode(compressed_bytes).decode('utf-8')
            data_uri = f"data:image/jpeg;base64,{base64_data}"
            
            print(f"  👁 Sending {len(compressed_bytes) // 1024}KB screenshot to OCR API...")
            
            # Run blocking API call in thread
            def _call_ocr():
                client = ZhipuAiClient(api_key=OCR_API_KEY)
                return client.layout_parsing.create(
                    model="glm-ocr",
                    file=data_uri
                )
            
            response = await asyncio.to_thread(_call_ocr)
            
            if response and hasattr(response, 'md_results'):
                self.vision_context = response.md_results
                print(f"  👁 Vision snapshot captured successfully ({len(self.vision_context)} chars of text)")
            else:
                self.vision_context = "OCR returned no result"
                print("  👁 Vision snapshot returned no result")
                
        except Exception as e:
            print(f"  ⚠ Vision snapshot failed: {e}")
            self.vision_context = f"Failed to capture vision snapshot: {e}"

    def extract_json_from_response(self, response_text):
        """Extract JSON from response, handling markdown code blocks."""
        text = response_text.strip()
        # Try direct parse
        try:
            return json.loads(text)
        except:
            pass
        # Try markdown code block
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except:
                pass
        # Try finding any JSON object (safely)
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            try:
                return json.loads(text[start_idx:end_idx+1])
            except:
                pass
        raise ValueError(f"No valid JSON found in response")

    def _format_elements_compact(self, elements):
        """Format elements into a compact but readable list for the AI."""
        lines = []
        for el in elements:
            idx = el.get("index", "?")
            tag = el.get("tag", "?")
            parts = [f"[{idx}] <{tag}>"]

            if el.get("role"):
                parts.append(f'role="{el["role"]}"')
            if el.get("type"):
                parts.append(f'type="{el["type"]}"')
            if el.get("id"):
                parts.append(f'id="{el["id"]}"')
            if el.get("name"):
                parts.append(f'name="{el["name"]}"')
            if el.get("label"):
                parts.append(f'label="{el["label"]}"')
            if el.get("placeholder"):
                parts.append(f'placeholder="{el["placeholder"]}"')
            if el.get("text"):
                text = el["text"][:60]
                parts.append(f'"{text}"')
            if el.get("href"):
                # Increase limit to 400 chars to avoid truncating long URLs like Quora questions
                href = el["href"][:400]
                parts.append(f'href="{href}"')
                # Inject duplicate check directly into element text to save tokens
                if self.duplicate_tracker and hasattr(self.duplicate_tracker, 'is_done'):
                    if self.duplicate_tracker.is_done(el["href"]):
                        parts.append("🛑DUPLICATE🛑")
            if el.get("value"):
                parts.append(f'value="{el["value"][:40]}"')
            if el.get("disabled"):
                parts.append("DISABLED")
            if el.get("options"):
                opts = ", ".join(o["text"] for o in el["options"][:5])
                parts.append(f'options=[{opts}]')
            if el.get("interactive"):
                parts.append("★")

            lines.append(" ".join(parts))
        return "\n".join(lines)

    async def decide_next_action(self):
        """Query AI for the next action."""
        elements = await self.get_visible_elements()
        page_state = await self.get_page_state()
        text_snippets = await self.get_page_text_snippets()

        elements_text = self._format_elements_compact(elements)
        interactive_count = sum(1 for e in elements if e.get("interactive"))

        # Build page text context from snippets
        text_context_lines = []
        for snippet in text_snippets:
            idx = snippet.get("index")
            tag = snippet.get("tag", "?")
            text = snippet.get("snippet", "")
            full_len = snippet.get("fullLength", 0)
            idx_str = f"[{idx}]" if idx is not None else "[-]"
            truncated = " [TRUNCATED — use extract_text to read full]" if full_len > len(text) + 10 else ""
            text_context_lines.append(f"{idx_str} <{tag}> {text}{truncated}")
        text_context = "\n".join(text_context_lines) if text_context_lines else "No readable text found on page"

        # Build state summary
        state_lines = [
            f"URL: {page_state.get('url', 'unknown')}",
            f"Title: {page_state.get('title', 'untitled')}",
            f"Scroll: {page_state.get('scrollPercent', 0)}%",
            f"Tabs: {page_state.get('tabCount', 1)} (current: #{page_state.get('currentTabIndex', 0)})",
            f"Elements: {len(elements)} total, {interactive_count} interactive",
        ]
        
        # Always show tab details with titles
        state_lines.append("Open Tabs:")
        for tab in page_state.get('tabs', []):
            idx = tab['index']
            title = tab['title'][:60] if tab.get('title') else 'Untitled'
            url = tab['url'][:80] if tab.get('url') else ''
            is_current = (idx == page_state.get('currentTabIndex', 0))
            marker = "→" if is_current else " "
            state_lines.append(f"  [{idx}] {marker} {title} | {url}")
        
        if page_state.get("inIframe"):
            state_lines.append("⚠ Currently inside an IFRAME")
        if page_state.get("pendingDialog"):
            d = page_state["pendingDialog"]
            state_lines.append(f"⚠ DIALOG OPEN: [{d['type']}] \"{d['message']}\"")
        if page_state.get("pendingPopup"):
            p = page_state["pendingPopup"]
            state_lines.append(f"🪟 POPUP WINDOW DETECTED: \"{p.get('title', 'Untitled')}\" at {p['url']} — Use 'switch_to_popup' to control it")
        if page_state.get("focusedElement"):
            f = page_state["focusedElement"]
            state_lines.append(f"Focused: <{f['tag']}> id={f.get('id', '-')} value={f.get('value', '-')}")

        state_summary = "\n".join(state_lines)

        # Build memory context for current domain
        current_url = page_state.get("url", "")
        current_domain = ""
        try:
            parsed = urlparse(current_url)
            # Extract base domain for memory matching (e.g. "www.trustpilot.com/categories" -> "trustpilot.com")
            host = parsed.netloc.replace("www.", "")
            if not host and current_url:
                # Fallback if no schema was present
                host = current_url.split('/')[0].replace("www.", "")
            current_domain = host
        except Exception:
            pass
            
        memory_notes = self.memory.read(current_domain) if current_domain else self.memory.read("_general")
        
        # Also always append _general lessons alongside domain lessons
        if current_domain and current_domain != "_general":
            general_notes = self.memory.read("_general")
            # Filter out generic notes that might already be included by read(domain)
            missing = [n for n in general_notes if n not in memory_notes]
            memory_notes.extend(missing)
            
        memory_text = "\n".join(f"• {n}" for n in memory_notes) if memory_notes else "No saved memories for this domain"

        # Build domain progress context
        domain_progress = self.memory.get_domain_progress(current_domain) if current_domain else ""

        # Build action history (last 15 in long-run, last 8 normally)
        history_window = 15 if LONG_RUN_MODE else 8
        history_text = "\n".join(self.action_history[-history_window:]) if self.action_history else "None yet"

        # Build error context (last 3)
        error_text = ""
        if self.error_history:
            error_text = "\n\n⚠ Recent errors:\n" + "\n".join(self.error_history[-3:])

        # Build vision context (if OCR snapshot was captured after repeated failures)
        vision_text = ""
        if self.vision_context:
            vision_text = f"\n\n## 👁 Vision Snapshot (OCR of screenshot — taken because of {VISION_FAILURE_THRESHOLD}+ consecutive failures)\nThe following is the OCR-recognized text from a screenshot of the ACTUAL page. Use this to understand what is VISUALLY shown on screen and figure out what went wrong:\n{self.vision_context}"
            # Clear after one use so it doesn't persist forever
            self.vision_context = None

        # Build consecutive failures context
        failure_text = ""
        if self.consecutive_failures >= 2:
            failure_text = f"\n\n⚠ CONSECUTIVE FAILURES: {self.consecutive_failures} (OCR available at {VISION_FAILURE_THRESHOLD}+ via `capture_screenshot_ocr` or auto-triggered)"

        # Elapsed time
        elapsed = round(time.time() - self.start_time, 1) if self.start_time else 0
        elapsed_display = f"{elapsed:.0f}s" if elapsed < 120 else f"{elapsed/60:.1f}min"

        today_date = datetime.now().strftime("%m-%d-%Y")

        # Build skill context if a skill file is loaded
        skill_text = ""
        if self.skill_config:
            skill_lines = []
            skill_lines.append(f"Site: {self.skill_config.site}")
            skill_lines.append(f"Profile: {self.current_profile}")
            skill_lines.append(f"Answers posted this session: {self.answers_count}")
            skill_lines.append(f"Max answers per session: {self.skill_config.rules.answers_per_session}")
            skill_lines.append(f"Wait between posts: {self.skill_config.rules.wait_between_posts_seconds}s")
            if self.skill_config.rules.switch_profile_after > 0:
                remaining = self.skill_config.rules.switch_profile_after - self.answers_count
                skill_lines.append(f"Switch profile after: {self.skill_config.rules.switch_profile_after} answers ({remaining} remaining)")
            if self.duplicate_tracker:
                skill_lines.append(f"Completed items tracked: {self.duplicate_tracker.count()}")
            if self.skill_config.selectors:
                skill_lines.append("Selector hints:")
                for name, sel in self.skill_config.selectors.items():
                    skill_lines.append(f"  {name}: {sel}")
            skill_text = "\n".join(skill_lines)

        # Build skill instructions section
        skill_instructions = ""
        if self.skill_config and self.skill_config.instructions:
            skill_instructions = f"\n\n## Skill Instructions (from .yaser/{self.skill_config.site.replace('.com','')}.md)\n{self.skill_config.instructions}"

        user_prompt = f"""## Current Date
{today_date}

## Goal
{self.goal}

## Page State
{state_summary}
{f"""
## Skill Context
{skill_text}""" if skill_text else ""}

## Memory (lessons from past runs on this domain)
{memory_text}
{f"Domain tracking: {domain_progress}" if domain_progress else ""}

## Visible Elements
{elements_text}

## Page Text Context (partial snippets — use extract_text for full content)
{text_context}

## Action History (step {self.step_count}/{self.max_steps}, {elapsed_display} elapsed)
{history_text}{error_text}{vision_text}{failure_text}{skill_instructions}

What is the next action? Respond with ONLY JSON."""

        print(f"\n{'━'*70}")
        print(f"  Step {self.step_count + 1}/{self.max_steps} │ {page_state.get('title', '')} │ {page_state.get('url', '')}")
        print(f"  {interactive_count} interactive elements │ scroll {page_state.get('scrollPercent', 0)}%")
        print(f"{'━'*70}")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

        response = await asyncio.to_thread(send_prompt, messages)

        if not response:
            print("  ⚠ Empty AI response - starting new chat session and retrying...")
            # Start new session immediately
            try:
                new_chat_url = "http://localhost:8000/v1/chat/new"
                await asyncio.to_thread(requests.post, new_chat_url, timeout=30)
                await asyncio.sleep(2)
                print("  🔄 New session started, retrying prompt...")
                # Retry with new session
                response = await asyncio.to_thread(send_prompt, messages)
                if not response:
                    print("  ⚠ Empty AI response after retry")
                    return None
            except Exception as e:
                print(f"  ⚠ Failed to start new session: {e}")
                return None

        try:
            action_data = self.extract_json_from_response(response)
            thinking = action_data.get("thinking", "")
            voice_summary = action_data.get("voice_summary", "")
            
            if thinking:
                # Truncate thinking for display
                display_thinking = thinking[:200] + "..." if len(thinking) > 200 else thinking
                print(f"  💭 {display_thinking}")
                
                # To read thoughts aloud, prioritize the short voice_summary, fallback to thinking if missing
                text_to_speak = voice_summary if voice_summary else thinking
                
                if READ_THOUGHTS and text_to_speak:
                    try:
                        # Run asynchronously so it doesn't block the browser agent
                        subprocess.Popen(
                            ["edge-playback", "--rate", THOUGHT_SPEECH_RATE, "--text", text_to_speak], 
                            stdout=subprocess.DEVNULL, 
                            stderr=subprocess.DEVNULL
                        )
                    except FileNotFoundError:
                        print(f"  ⚠ Failed to read thought: 'edge-playback' command not found. Please install edge-tts or disable READ_THOUGHTS in config.")
                    except Exception as e:
                        print(f"  ⚠ Failed to read thought: {e}")
            actions = action_data.get("actions", [])
            if not actions and "action" in action_data:
                actions = [action_data.get("action", {})]
            
            action_desc = ", ".join(a.get("type", "?") for a in actions)
            print(f"  🎯 Actions: {action_desc} {json.dumps(actions, ensure_ascii=False)}")
            return action_data
        except Exception as e:
            print(f"  ⚠ JSON parse error: {e} - starting new chat session and retrying...")
            print(f"  Response: {response[:300]}")
            # Start new session immediately on JSON parse error
            try:
                new_chat_url = "http://localhost:8000/v1/chat/new"
                await asyncio.to_thread(requests.post, new_chat_url, timeout=30)
                await asyncio.sleep(2)
                print("  🔄 New session started, retrying prompt...")
                # Retry with new session
                response = await asyncio.to_thread(send_prompt, messages)
                if not response:
                    print("  ⚠ Empty AI response after retry")
                    return None
                # Try parsing again
                try:
                    action_data = self.extract_json_from_response(response)
                    thinking = action_data.get("thinking", "")
                    voice_summary = action_data.get("voice_summary", "")
                    
                    if thinking:
                        display_thinking = thinking[:200] + "..." if len(thinking) > 200 else thinking
                        print(f"  💭 {display_thinking}")
                        text_to_speak = voice_summary if voice_summary else thinking
                        if READ_THOUGHTS and text_to_speak:
                            try:
                                subprocess.Popen(
                                    ["edge-playback", "--rate", THOUGHT_SPEECH_RATE, "--text", text_to_speak], 
                                    stdout=subprocess.DEVNULL, 
                                    stderr=subprocess.DEVNULL
                                )
                            except FileNotFoundError:
                                print(f"  ⚠ Failed to read thought: 'edge-playback' command not found. Please install edge-tts or disable READ_THOUGHTS in config.")
                            except Exception as e:
                                print(f"  ⚠ Failed to read thought: {e}")
                    actions = action_data.get("actions", [])
                    if not actions and "action" in action_data:
                        actions = [action_data.get("action", {})]
                    
                    action_desc = ", ".join(a.get("type", "?") for a in actions)
                    print(f"  🎯 Actions: {action_desc} {json.dumps(actions, ensure_ascii=False)}")
                    return action_data
                except Exception as retry_err:
                    print(f"  ⚠ JSON parse error after retry: {retry_err}")
                    print(f"  Response: {response[:300]}")
                    return None
            except Exception as session_err:
                print(f"  ⚠ Failed to start new session: {session_err}")
                return None

    async def execute_action(self, action_data):
        """Execute the decided action(s) with retry logic."""
        if not action_data:
            print("  ⚠ Invalid action data")
            return "continue"

        actions = action_data.get("actions", [])
        if not actions and "action" in action_data:
            actions = [action_data["action"]]

        if not actions:
            print("  ⚠ No actions found")
            return "continue"

        step_had_failure = False  # Track if any action in this step failed
        
        for action in actions:
            action_type = action.get("type", "")
            
            # Action-level retry loop
            action_success = False
            action_failures = 0
            max_action_retries = 3
            
            while action_failures < max_action_retries:
                try:
                    result = await self._do_action(action_type, action)
                    action_success = True
                    
                    # Log successful action to session memory
                    action_desc = self._get_action_description(action_type, action)
                    self.memory.log_progress(
                        self.step_count,
                        action_type,
                        action_desc,
                        status="success"
                    )
                    
                    # Track per-domain progress
                    try:
                        current_url = self.page.url
                        domain = urlparse(current_url).netloc.replace("www.", "") if current_url else ""
                        if domain:
                            self.memory.track_domain_progress(domain, self.step_count, action_desc, status="success")
                    except Exception:
                        pass
                    
                    if result in ["wait", "abort", "completed", "failed", "switch_profile"]:
                        return result
                    break  # Success, move to next action
                except Exception as e:
                    action_failures += 1
                    error_msg = f"Action '{action_type}' failed (attempt {action_failures}/{max_action_retries}): {str(e)[:150]}"
                    print(f"  ❌ {error_msg}")
                    
                    if action_failures == max_action_retries:
                        self.error_history.append(error_msg)
                        self.action_history.append(f"FAILED (after {max_action_retries} tries): {action_type} — {str(e)[:80]}")
                        step_had_failure = True
                        
                        # Log failed action to session memory
                        action_desc = self._get_action_description(action_type, action)
                        self.memory.log_progress(
                            self.step_count,
                            action_type,
                            f"FAILED: {action_desc} - {str(e)[:100]}",
                            status="failed"
                        )
                    else:
                        await asyncio.sleep(1.5)  # Wait before retry
            
            # If the action ultimately failed after retries
            if not action_success:
                step_had_failure = True
                break  # Stop processing further actions in this list, return to AI for new plan
        
        # Only update consecutive_failures counter at the step level, not action level
        if step_had_failure:
            self.consecutive_failures += 1
            
            # Trigger OCR if we've had too many consecutive failures
            if self.consecutive_failures >= VISION_FAILURE_THRESHOLD:
                if not self.vision_context:
                    print(f"  👁 {self.consecutive_failures} consecutive step failures — capturing vision snapshot...")
                    await self._capture_vision_snapshot()
            
            # Abort if too many failures
            if self.consecutive_failures >= self.max_consecutive_failures:
                print(f"\n  🛑 {self.consecutive_failures} consecutive step failures — aborting")
                return "abort"
        else:
            # Only reset counter if the entire step succeeded (all actions completed successfully)
            self.consecutive_failures = 0

        return "continue"

    def _get_action_description(self, action_type, action):
        """Generate a human-readable description of an action."""
        if action_type in ["click", "double_click", "right_click"]:
            idx = action.get("index")
            selector = action.get("selector", "")
            return f"{action_type} [{idx}]" if idx is not None else f"{action_type} {selector}"
        elif action_type == "type":
            idx = action.get("index")
            text = action.get("text", "")[:50]
            return f"type '{text}' into [{idx}]" if idx is not None else f"type '{text}'"
        elif action_type == "navigate":
            return f"navigate to {action.get('url', '')}"
        elif action_type == "scroll":
            direction = action.get("direction", "down")
            return f"scroll {direction}"
        elif action_type == "wait":
            return f"wait {action.get('seconds', 1)}s"
        elif action_type == "goal_completed":
            return f"COMPLETED: {action.get('reason', '')}"
        elif action_type == "goal_failed":
            return f"FAILED: {action.get('reason', '')}"
        else:
            return f"{action_type}"

    async def _do_action(self, action_type, action):
        """Execute a single action. Delegates to actions module."""
        return await do_action(self, action_type, action)

    def _elapsed_str(self):
        """Human-readable elapsed time."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        if elapsed < 120:
            return f"{elapsed:.1f}s"
        elif elapsed < 7200:
            return f"{elapsed/60:.1f}min"
        else:
            return f"{elapsed/3600:.1f}hr"

    async def run(self):
        """Run the autonomous agent loop."""
        self.start_time = time.time()

        # Long-run mode overrides max_steps
        effective_max = 999999 if LONG_RUN_MODE else self.max_steps

        print(f"\n{'━'*70}")
        print(f"  🚀 BROWSER AGENT v2 STARTED")
        print(f"  Goal: {self.goal}")
        print(f"  Max steps: {'∞ (long-run)' if LONG_RUN_MODE else self.max_steps}")
        print(f"  Memory: {len(self.memory.data)} domains stored")
        print(f"{'━'*70}")
        
        # Initialize cursor on first page load
        try:
            await asyncio.sleep(0.5)  # Wait for page to be ready
            await self.page.evaluate(INIT_CURSOR_JS)
            cursor_pos = self.memory.get_cursor_position()
            x, y = cursor_pos["x"], cursor_pos["y"]
            await self.page.evaluate(f"window.__move_cursor && window.__move_cursor({x}, {y})")
            print(f"  🖱 Cursor humanization initialized at ({x}, {y})")
        except Exception as e:
            print(f"  ⚠ Initial cursor setup error: {e}")

        while self.step_count < effective_max:
            self.step_count += 1
            
            # Enforce max limit of 5 tabs
            pages = self.context.pages
            if len(pages) > 5:
                print(f"  🧹 Cleaning up tabs. Found {len(pages)} Tabs, Max is 5.")
                # We need to loop since playwright pages list doesn't update synchronously without context.pages re-retrieval
                for p in list(pages):
                    if len(self.context.pages) <= 5:
                        break
                    if p != self.page:
                        try:
                            # Safely close popup pages
                            print(f"  ✖ Auto-closing background tab: {p.url}")
                            await p.close()
                        except Exception as e:
                            print(f"  ⚠ Error closing tab: {e}")

            # Periodic progress save in long-run mode
            if LONG_RUN_MODE and self.step_count % 25 == 0:
                progress_note = f"Step {self.step_count}, {self._elapsed_str()} — still working on: {self.goal[:80]}"
                self.memory.write("_progress", progress_note)
                print(f"  💾 Auto-saved progress (step {self.step_count})")

            # Decide next action
            action_data = await self.decide_next_action()
            if not action_data:
                print("  ⚠ No valid action, retrying...")
                self.error_history.append("AI returned no valid action")
                self.consecutive_failures += 1
                
                # Trigger OCR if we've had too many consecutive failures
                if self.consecutive_failures >= VISION_FAILURE_THRESHOLD:
                    if not self.vision_context:
                        print(f"  👁 {self.consecutive_failures} consecutive failures (including AI response errors) — capturing vision snapshot...")
                        await self._capture_vision_snapshot()
                
                # Abort if too many failures
                if self.consecutive_failures >= self.max_consecutive_failures:
                    print(f"\n  🛑 {self.consecutive_failures} consecutive failures — aborting")
                    self.memory.mark_failed(f"{self.consecutive_failures} consecutive failures")
                    self.memory.save()
                    return False
                
                await asyncio.sleep(2)
                continue

            # Execute action
            result = await self.execute_action(action_data)

            if result == "completed":
                print(f"\n  ✅ Goal achieved in {self.step_count} steps ({self._elapsed_str()})")
                self.memory.mark_completed()
                self.memory.save()
                return True
            elif result == "failed":
                print(f"\n  ❌ Goal failed after {self.step_count} steps ({self._elapsed_str()})")
                self.memory.mark_failed("Goal explicitly marked as failed by agent")
                self.memory.save()
                return False
            elif result == "abort":
                print(f"\n  🛑 Aborted after {self.step_count} steps ({self._elapsed_str()})")
                self.memory.mark_failed("Aborted due to errors")
                self.memory.save()
                return False
            elif result == "switch_profile":
                print(f"\n  🔄 Profile switch requested after {self.step_count} steps ({self._elapsed_str()})")
                self.memory.save()
                return "switch_profile"

            # Small delay between steps
            await asyncio.sleep(0.5)

        print(f"\n  ⚠ Max steps ({self.max_steps}) reached ({self._elapsed_str()})")
        self.memory.mark_failed(f"Max steps ({self.max_steps}) reached")
        self.memory.save()
        return False
