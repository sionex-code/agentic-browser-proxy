# ─────────────────────────── Action Execution ───────────────────────────
# All browser actions extracted from BrowserAgent._do_action.
# Each action handler receives the agent instance to access page, memory, etc.

import asyncio
import json
import os
import random

# Import cursor scripts for navigation actions
from .page_scripts import INIT_CURSOR_JS, GET_CURSOR_POSITION_JS


async def humanized_mouse_move(page, start_x, start_y, target_x, target_y, steps=40):
    """
    Moves the mouse from (start_x, start_y) to (target_x, target_y) with human-like Bezier curve.
    Uses quadratic Bezier curve with dramatic control points for natural, curved movement with overshoot.
    
    Args:
        page: Playwright page object
        start_x, start_y: Starting coordinates
        target_x, target_y: Target coordinates
        steps: Number of intermediate steps (higher = smoother)
    """
    # Ensure start position
    await page.mouse.move(start_x, start_y)
    # Update visual cursor at start
    await update_visual_cursor(page, start_x, start_y)

    # Calculate distance for scaling the curve
    distance = ((target_x - start_x) ** 2 + (target_y - start_y) ** 2) ** 0.5
    
    # Generate control point for Bezier curve with MORE dramatic offset
    mid_x = (start_x + target_x) / 2
    mid_y = (start_y + target_y) / 2
    
    # Scale offset based on distance - longer movements get more curve
    curve_intensity = min(distance * 0.3, 200)  # Max 200px offset
    
    # Random offset perpendicular to the movement direction for natural curves
    dx = target_x - start_x
    dy = target_y - start_y
    
    # Perpendicular vector (rotate 90 degrees)
    perp_x = -dy
    perp_y = dx
    
    # Normalize and scale
    perp_length = (perp_x ** 2 + perp_y ** 2) ** 0.5
    if perp_length > 0:
        perp_x = (perp_x / perp_length) * curve_intensity * random.uniform(-1, 1)
        perp_y = (perp_y / perp_length) * curve_intensity * random.uniform(-1, 1)
    
    control_x = mid_x + perp_x + random.uniform(-50, 50)
    control_y = mid_y + perp_y + random.uniform(-50, 50)
    
    print(f"  📐 Bezier control: ({control_x:.0f}, {control_y:.0f}), curve intensity: {curve_intensity:.0f}px")

    # Generate Bezier curve path
    for i in range(steps + 1):
        t = i / steps  # Parameter from 0 to 1
        
        # Quadratic Bezier curve formula: B(t) = (1-t)²P₀ + 2(1-t)tP₁ + t²P₂
        # P₀ = start, P₁ = control, P₂ = target
        x = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * control_x + t ** 2 * target_x
        y = (1 - t) ** 2 * start_y + 2 * (1 - t) * t * control_y + t ** 2 * target_y
        
        # Add overshoot near the end (90-100% of movement)
        if 0.9 <= t <= 0.98:
            overshoot_factor = (t - 0.9) * 10  # 0 to 0.8
            x += random.uniform(-5, 5) * overshoot_factor
            y += random.uniform(-5, 5) * overshoot_factor
        
        # Add slight jitter throughout for realism
        x += random.uniform(-3, 3)
        y += random.uniform(-3, 3)
        
        # Clip coordinates to stay within viewport
        viewport_size = page.viewport_size
        if viewport_size:
            x = max(0, min(x, viewport_size['width']))
            y = max(0, min(y, viewport_size['height']))

        # Move mouse to this point
        await page.mouse.move(x, y)
        # Update visual cursor at each step - THIS IS KEY!
        await update_visual_cursor(page, x, y)
        
        # Variable speed - slower at start/end, faster in middle (ease in/out)
        if i < steps * 0.15:
            await asyncio.sleep(random.uniform(0.025, 0.045))  # Slow start
        elif i > steps * 0.85:
            await asyncio.sleep(random.uniform(0.020, 0.040))  # Slow end
        else:
            await asyncio.sleep(random.uniform(0.008, 0.015))  # Fast middle

    # Ensure final position is exact
    await page.mouse.move(target_x, target_y)
    await update_visual_cursor(page, target_x, target_y)
    await asyncio.sleep(random.uniform(0.1, 0.3))  # Pause briefly at target like a human


async def update_visual_cursor(page, x, y):
    """Update the visual cursor position on the page."""
    try:
        await page.evaluate(f"window.__move_cursor && window.__move_cursor({x}, {y})")
    except Exception:
        pass  # Silently fail if cursor script not loaded


async def sync_cursor_position(agent):
    """Sync cursor position from page to memory."""
    try:
        cursor_pos = await agent.page.evaluate(GET_CURSOR_POSITION_JS)
        if cursor_pos and isinstance(cursor_pos, dict):
            x, y = cursor_pos.get("x", 100), cursor_pos.get("y", 100)
            agent.memory.save_cursor_position(x, y)
            return x, y
    except Exception:
        pass
    return None, None


async def do_action(agent, action_type, action):
    """Execute a single action. Returns 'completed', 'failed', or 'continue'.
    
    Args:
        agent: BrowserAgent instance (provides .page, .context, .memory, etc.)
        action_type: String identifier for the action.
        action: Dict of action parameters.
    """

    # ─── Click Actions ───
    if action_type == "click":
        selector, idx = agent._resolve_selector(action)
        desc = f"[{idx}]" if idx is not None else selector
        print(f"  👆 Click {desc}")
        
        # Get element position
        el = await agent.page.query_selector(selector)
        if el:
            box = await el.bounding_box()
            if box:
                # Get current cursor position from memory
                cursor_pos = agent.memory.get_cursor_position()
                start_x, start_y = cursor_pos["x"], cursor_pos["y"]
                
                # Calculate target with slight random offset for realism
                target_x = box['x'] + box['width'] / 2 + random.uniform(-10, 10)
                target_y = box['y'] + box['height'] / 2 + random.uniform(-10, 10)
                
                print(f"  🖱 Moving cursor from ({start_x:.0f}, {start_y:.0f}) to ({target_x:.0f}, {target_y:.0f})")
                
                # Humanized mouse movement with Bezier curve
                await humanized_mouse_move(agent.page, start_x, start_y, target_x, target_y)
                
                # Save new cursor position
                agent.memory.save_cursor_position(target_x, target_y)
                
                # Perform click
                await agent.page.mouse.click(target_x, target_y)
            else:
                # Fallback to regular click if no bounding box
                await agent.page.click(selector, timeout=8000)
        else:
            # Fallback to regular click if element not found
            await agent.page.click(selector, timeout=8000)
            
        await asyncio.sleep(1)
        agent.action_history.append(f"Clicked {desc}")

    elif action_type == "double_click":
        selector, idx = agent._resolve_selector(action)
        desc = f"[{idx}]" if idx is not None else selector
        print(f"  👆👆 Double-click {desc}")
        
        # Get element position
        el = await agent.page.query_selector(selector)
        if el:
            box = await el.bounding_box()
            if box:
                # Get current cursor position from memory
                cursor_pos = agent.memory.get_cursor_position()
                start_x, start_y = cursor_pos["x"], cursor_pos["y"]
                
                # Calculate target with slight random offset
                target_x = box['x'] + box['width'] / 2 + random.uniform(-10, 10)
                target_y = box['y'] + box['height'] / 2 + random.uniform(-10, 10)
                
                print(f"  🖱 Moving cursor from ({start_x:.0f}, {start_y:.0f}) to ({target_x:.0f}, {target_y:.0f})")
                
                # Humanized mouse movement
                await humanized_mouse_move(agent.page, start_x, start_y, target_x, target_y)
                
                # Save new cursor position
                agent.memory.save_cursor_position(target_x, target_y)
                
                # Perform double-click
                await agent.page.mouse.dblclick(target_x, target_y)
            else:
                await agent.page.dblclick(selector, timeout=8000)
        else:
            await agent.page.dblclick(selector, timeout=8000)
            
        await asyncio.sleep(1)
        agent.action_history.append(f"Double-clicked {desc}")

    elif action_type == "right_click":
        selector, idx = agent._resolve_selector(action)
        desc = f"[{idx}]" if idx is not None else selector
        print(f"  👆🔧 Right-click {desc}")
        
        # Get element position
        el = await agent.page.query_selector(selector)
        if el:
            box = await el.bounding_box()
            if box:
                # Get current cursor position from memory
                cursor_pos = agent.memory.get_cursor_position()
                start_x, start_y = cursor_pos["x"], cursor_pos["y"]
                
                # Calculate target with slight random offset
                target_x = box['x'] + box['width'] / 2 + random.uniform(-10, 10)
                target_y = box['y'] + box['height'] / 2 + random.uniform(-10, 10)
                
                print(f"  🖱 Moving cursor from ({start_x:.0f}, {start_y:.0f}) to ({target_x:.0f}, {target_y:.0f})")
                
                # Humanized mouse movement
                await humanized_mouse_move(agent.page, start_x, start_y, target_x, target_y)
                
                # Save new cursor position
                agent.memory.save_cursor_position(target_x, target_y)
                
                # Perform right-click
                await agent.page.mouse.click(target_x, target_y, button="right")
            else:
                await agent.page.click(selector, button="right", timeout=8000)
        else:
            await agent.page.click(selector, button="right", timeout=8000)
            
        await asyncio.sleep(1)
        agent.action_history.append(f"Right-clicked {desc}")

    elif action_type == "hover":
        selector, idx = agent._resolve_selector(action)
        desc = f"[{idx}]" if idx is not None else selector
        print(f"  🖱 Hover {desc}")
        
        # Get element position
        el = await agent.page.query_selector(selector)
        if el:
            box = await el.bounding_box()
            if box:
                # Get current cursor position from memory
                cursor_pos = agent.memory.get_cursor_position()
                start_x, start_y = cursor_pos["x"], cursor_pos["y"]
                
                # Calculate target with slight random offset
                target_x = box['x'] + box['width'] / 2 + random.uniform(-10, 10)
                target_y = box['y'] + box['height'] / 2 + random.uniform(-10, 10)
                
                print(f"  🖱 Moving cursor from ({start_x:.0f}, {start_y:.0f}) to ({target_x:.0f}, {target_y:.0f})")
                
                # Humanized mouse movement
                await humanized_mouse_move(agent.page, start_x, start_y, target_x, target_y)
                
                # Save new cursor position
                agent.memory.save_cursor_position(target_x, target_y)
            else:
                await agent.page.hover(selector, timeout=8000)
        else:
            await agent.page.hover(selector, timeout=8000)
            
        await asyncio.sleep(0.8)
        agent.action_history.append(f"Hovered {desc}")

    elif action_type == "focus":
        selector, idx = agent._resolve_selector(action)
        desc = f"[{idx}]" if idx is not None else selector
        print(f"  🎯 Focus {desc}")
        await agent.page.focus(selector, timeout=8000)
        await asyncio.sleep(0.3)
        agent.action_history.append(f"Focused {desc}")

    # ─── Typing Actions ───
    elif action_type == "type_text":
        selector, idx = agent._resolve_selector(action)
        text = action.get("text", "")
        desc = f"[{idx}]" if idx is not None else selector
        delay = random.randint(30, 90)
        print(f"  ⌨ Type '{text}' into {desc} (delay={delay}ms)")
        
        # Get element position and move cursor there first
        el = await agent.page.query_selector(selector)
        if el:
            box = await el.bounding_box()
            if box:
                cursor_pos = agent.memory.get_cursor_position()
                start_x, start_y = cursor_pos["x"], cursor_pos["y"]
                target_x = box['x'] + box['width'] / 2 + random.uniform(-10, 10)
                target_y = box['y'] + box['height'] / 2 + random.uniform(-10, 10)
                
                await humanized_mouse_move(agent.page, start_x, start_y, target_x, target_y)
                await update_visual_cursor(agent.page, target_x, target_y)
                agent.memory.save_cursor_position(target_x, target_y)
        
        await agent.page.click(selector, timeout=8000)
        await asyncio.sleep(0.2)
        await agent.page.type(selector, text, delay=delay, timeout=245000)
        await asyncio.sleep(0.5)
        agent.action_history.append(f"Typed '{text}' into {desc}")

    elif action_type == "clear_and_type":
        selector, idx = agent._resolve_selector(action)
        text = action.get("text", "")
        desc = f"[{idx}]" if idx is not None else selector
        delay = random.randint(30, 90)
        print(f"  ⌨ Clear & type '{text}' into {desc}")
        
        # Get element position and move cursor there first
        el = await agent.page.query_selector(selector)
        if el:
            box = await el.bounding_box()
            if box:
                cursor_pos = agent.memory.get_cursor_position()
                start_x, start_y = cursor_pos["x"], cursor_pos["y"]
                target_x = box['x'] + box['width'] / 2 + random.uniform(-10, 10)
                target_y = box['y'] + box['height'] / 2 + random.uniform(-10, 10)
                
                await humanized_mouse_move(agent.page, start_x, start_y, target_x, target_y)
                await update_visual_cursor(agent.page, target_x, target_y)
                agent.memory.save_cursor_position(target_x, target_y)
        
        await agent.page.click(selector, timeout=8000)
        await asyncio.sleep(0.2)
        # Ctrl+A selects ALL text reliably (triple-click can miss multi-line)
        await agent.page.press(selector, "Control+a")
        await asyncio.sleep(0.1)
        await agent.page.press(selector, "Backspace")
        await asyncio.sleep(0.2)
        await agent.page.type(selector, text, delay=delay, timeout=245000)
        await asyncio.sleep(0.5)
        agent.action_history.append(f"Cleared & typed '{text}' into {desc}")

    # ─── Keyboard Actions ───
    elif action_type == "press_key":
        key = action.get("key", "Enter")
        selector = action.get("selector", "")
        if "index" in action:
            selector, _ = agent._resolve_selector(action)
        target = selector or "body"
        print(f"  ⌨ Press {key}")
        await agent.page.press(target, key, timeout=5000)
        await asyncio.sleep(1)
        agent.action_history.append(f"Pressed {key}")

    elif action_type == "press_combo":
        keys = action.get("keys", "Control+a")
        print(f"  ⌨ Combo {keys}")
        await agent.page.keyboard.press(keys)
        await asyncio.sleep(0.5)
        agent.action_history.append(f"Pressed combo {keys}")

    # ─── Form Actions ───
    elif action_type == "select_option":
        selector, idx = agent._resolve_selector(action)
        desc = f"[{idx}]" if idx is not None else selector
        if "value" in action:
            print(f"  📝 Select value='{action['value']}' on {desc}")
            await agent.page.select_option(selector, value=action["value"], timeout=5000)
        elif "label" in action:
            print(f"  📝 Select label='{action['label']}' on {desc}")
            await agent.page.select_option(selector, label=action["label"], timeout=5000)
        await asyncio.sleep(0.5)
        agent.action_history.append(f"Selected option on {desc}")

    elif action_type == "check":
        selector, idx = agent._resolve_selector(action)
        desc = f"[{idx}]" if idx is not None else selector
        print(f"  ☑ Check {desc}")
        await agent.page.check(selector, timeout=5000)
        await asyncio.sleep(0.3)
        agent.action_history.append(f"Checked {desc}")

    elif action_type == "uncheck":
        selector, idx = agent._resolve_selector(action)
        desc = f"[{idx}]" if idx is not None else selector
        print(f"  ☐ Uncheck {desc}")
        await agent.page.uncheck(selector, timeout=5000)
        await asyncio.sleep(0.3)
        agent.action_history.append(f"Unchecked {desc}")

    # ─── Scroll Actions ───
    elif action_type == "scroll_down":
        print(f"  ⬇ Scroll down")
        await agent.page.evaluate("window.scrollBy(0, window.innerHeight * 0.75)")
        await asyncio.sleep(1)
        
        # Update cursor position after scroll (cursor stays in same viewport position)
        try:
            cursor_pos = await agent.page.evaluate(GET_CURSOR_POSITION_JS)
            if cursor_pos and isinstance(cursor_pos, dict):
                agent.memory.save_cursor_position(cursor_pos.get("x", 0), cursor_pos.get("y", 0))
        except Exception:
            pass
        
        agent.action_history.append("Scrolled down")

    elif action_type == "scroll_up":
        print(f"  ⬆ Scroll up")
        await agent.page.evaluate("window.scrollBy(0, -window.innerHeight * 0.75)")
        await asyncio.sleep(1)
        
        # Update cursor position after scroll
        try:
            cursor_pos = await agent.page.evaluate(GET_CURSOR_POSITION_JS)
            if cursor_pos and isinstance(cursor_pos, dict):
                agent.memory.save_cursor_position(cursor_pos.get("x", 0), cursor_pos.get("y", 0))
        except Exception:
            pass
        
        agent.action_history.append("Scrolled up")

    elif action_type == "scroll_to_element":
        selector, idx = agent._resolve_selector(action)
        desc = f"[{idx}]" if idx is not None else selector
        print(f"  🔍 Scroll to {desc}")
        el = await agent.page.query_selector(selector)
        if el:
            await el.scroll_into_view_if_needed(timeout=5000)
        await asyncio.sleep(0.8)
        
        # Update cursor position after scroll
        try:
            cursor_pos = await agent.page.evaluate(GET_CURSOR_POSITION_JS)
            if cursor_pos and isinstance(cursor_pos, dict):
                agent.memory.save_cursor_position(cursor_pos.get("x", 0), cursor_pos.get("y", 0))
        except Exception:
            pass
        
        agent.action_history.append(f"Scrolled to {desc}")

    # ─── Navigation Actions ───
    elif action_type == "navigate":
        url = action.get("url", "")
        print(f"  🌐 Navigate to {url}")
        
        # Save cursor position before navigation
        x, y = await sync_cursor_position(agent)
        if x is not None:
            print(f"  💾 Saved cursor position before navigation: ({x:.0f}, {y:.0f})")
        
        await agent.page.goto(url, wait_until="domcontentloaded", timeout=50000)
        await asyncio.sleep(2.5)
        
        # Reinitialize cursor after navigation
        try:
            print(f"  🔄 Reinitializing cursor after navigation...")
            await agent.page.evaluate(INIT_CURSOR_JS)
            await asyncio.sleep(0.3)
            
            # Get saved position from memory (from file)
            cursor_pos = agent.memory.get_cursor_position()
            x, y = cursor_pos["x"], cursor_pos["y"]
            print(f"  📂 Loaded cursor position from memory: ({x:.0f}, {y:.0f})")
            
            # Restore position
            await agent.page.evaluate(f"window.__move_cursor && window.__move_cursor({x}, {y})")
            print(f"  ✅ Cursor restored to ({x:.0f}, {y:.0f}) after navigation")
        except Exception as e:
            print(f"  ⚠ Cursor restore error: {e}")
        
        agent.action_history.append(f"Navigated to {url}")

    elif action_type == "go_back":
        print(f"  ◀ Go back")
        
        # Save cursor position before navigation
        x, y = await sync_cursor_position(agent)
        if x is not None:
            print(f"  💾 Saved cursor position before going back: ({x:.0f}, {y:.0f})")
        
        await agent.page.go_back(wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2.5)
        
        # Reinitialize cursor after navigation
        try:
            print(f"  🔄 Reinitializing cursor after going back...")
            await agent.page.evaluate(INIT_CURSOR_JS)
            await asyncio.sleep(0.3)
            
            cursor_pos = agent.memory.get_cursor_position()
            x, y = cursor_pos["x"], cursor_pos["y"]
            print(f"  📂 Loaded cursor position from memory: ({x:.0f}, {y:.0f})")
            
            await agent.page.evaluate(f"window.__move_cursor && window.__move_cursor({x}, {y})")
            print(f"  ✅ Cursor restored to ({x:.0f}, {y:.0f}) after going back")
        except Exception as e:
            print(f"  ⚠ Cursor restore error: {e}")
        
        agent.action_history.append("Went back")

    elif action_type == "go_forward":
        print(f"  ▶ Go forward")
        
        # Save cursor position before navigation
        x, y = await sync_cursor_position(agent)
        if x is not None:
            print(f"  💾 Saved cursor position before going forward: ({x:.0f}, {y:.0f})")
        
        await agent.page.go_forward(wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2.5)
        
        # Reinitialize cursor after navigation
        try:
            print(f"  🔄 Reinitializing cursor after going forward...")
            await agent.page.evaluate(INIT_CURSOR_JS)
            await asyncio.sleep(0.3)
            
            cursor_pos = agent.memory.get_cursor_position()
            x, y = cursor_pos["x"], cursor_pos["y"]
            print(f"  📂 Loaded cursor position from memory: ({x:.0f}, {y:.0f})")
            
            await agent.page.evaluate(f"window.__move_cursor && window.__move_cursor({x}, {y})")
            print(f"  ✅ Cursor restored to ({x:.0f}, {y:.0f}) after going forward")
        except Exception as e:
            print(f"  ⚠ Cursor restore error: {e}")
        
        agent.action_history.append("Went forward")

    elif action_type == "open_new_tab":
        url = action.get("url", "about:blank")
        print(f"  ➕ Open new tab: {url}")
        
        # Enforce max limit of 5 tabs
        pages = agent.context.pages
        while len(pages) >= 5:
            closed_one = False
            for p in pages:
                if p != agent.page:
                    print(f"  ✖ Max tabs reached (5). Closing background tab: {p.url}")
                    await p.close()
                    # playwright doesn't immediately remove it from context.pages in the same tick if we don't refresh the list, but it's okay we will break out of this loop
                    pages.remove(p)
                    closed_one = True
                    break
            if not closed_one:
                break
                
        # Create a new page in the same context
        new_page = await agent.context.new_page()
        
        # Set up event handlers for the new page
        new_page.on("dialog", agent._handle_dialog)
        new_page.on("popup", agent._handle_popup)
        
        if url and url != "about:blank":
            try:
                await new_page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"  ⚠ Navigation error in new tab: {e}")
        # Switch to the new tab
        agent.page = new_page
        await agent.page.bring_to_front()
        print(f"  ➕ New tab opened and switched to: {url}")
        agent.action_history.append(f"Opened new tab: {url}")

    elif action_type == "switch_tab":
        tab_index = action.get("tab_index", 0)
        pages = agent.context.pages
        if 0 <= tab_index < len(pages):
            agent.page = pages[tab_index]
            await agent.page.bring_to_front()
            print(f"  📑 Switched to tab {tab_index}: {agent.page.url}")
            agent.action_history.append(f"Switched to tab {tab_index}")
        else:
            raise ValueError(f"Tab index {tab_index} out of range (0-{len(pages)-1})")

    elif action_type == "close_tab":
        print(f"  ✖ Close current tab")
        pages = agent.context.pages
        if len(pages) > 1:
            current_url = agent.page.url
            await agent.page.close()
            agent.page = agent.context.pages[-1]
            await agent.page.bring_to_front()
            print(f"  ✖ Closed tab: {current_url}")
            agent.action_history.append(f"Closed tab: {current_url}")
            
            # Clear pending_popup if we just closed the popup
            if agent.pending_popup and agent.pending_popup.get("url") == current_url:
                agent.pending_popup = None
        else:
            print("  ⚠ Cannot close last tab")

    elif action_type == "switch_to_popup":
        print(f"  🪟 Switch to popup window")
        if agent.pending_popup and agent.pending_popup.get("page"):
            popup_page = agent.pending_popup["page"]
            # Check if popup is still open
            if not popup_page.is_closed():
                agent.page = popup_page
                await agent.page.bring_to_front()
                print(f"  🪟 Switched to popup: {agent.page.url}")
                agent.action_history.append(f"Switched to popup: {agent.page.url}")
                # Clear pending_popup since we've handled it
                agent.pending_popup = None
            else:
                print("  ⚠ Popup window has already closed")
                agent.pending_popup = None
                raise ValueError("Popup window is closed")
        else:
            print("  ⚠ No popup window detected")
            raise ValueError("No popup window available")

    elif action_type == "list_tabs":
        print(f"  📋 Listing all tabs")
        pages = agent.context.pages
        tab_info = []
        for i, p in enumerate(pages):
            try:
                title = await p.title()
                url = p.url
                is_current = (p == agent.page)
                tab_info.append(f"  [{i}] {'→ ' if is_current else '  '}{title[:60]} | {url}")
                print(f"  [{i}] {'→ ' if is_current else '  '}{title[:60]} | {url}")
            except Exception as e:
                tab_info.append(f"  [{i}] Error: {e}")
                print(f"  [{i}] Error: {e}")
        tab_report = "\n".join(tab_info)
        agent.action_history.append(f"Listed {len(pages)} tabs:\n{tab_report}")
        return "continue"

    # ─── Frame Actions ───
    elif action_type == "switch_to_iframe":
        selector, idx = agent._resolve_selector(action)
        desc = f"[{idx}]" if idx is not None else selector
        print(f"  🖼 Switch to iframe {desc}")
        frame_el = await agent.page.query_selector(selector)
        if frame_el:
            frame = await frame_el.content_frame()
            if frame:
                agent.page = frame
                agent.in_iframe = True
                agent.action_history.append(f"Entered iframe {desc}")
            else:
                raise ValueError("Could not get iframe content frame")
        else:
            raise ValueError(f"Iframe not found: {selector}")

    elif action_type == "switch_to_main":
        print(f"  🖼 Switch to main frame")
        pages = agent.context.pages
        current_idx = 0
        for i, p in enumerate(pages):
            if agent.page in [p] + list(p.frames):
                current_idx = i
                break
        agent.page = pages[current_idx]
        agent.in_iframe = False
        agent.action_history.append("Switched to main frame")

    # ─── Dialog Actions ───
    elif action_type == "accept_dialog":
        text = action.get("text", "")
        print(f"  ✅ Accept dialog" + (f" with text '{text}'" if text else ""))
        # Dialog is auto-handled; we set up the handler
        agent.page.once("dialog", lambda d: asyncio.ensure_future(d.accept(text) if text else d.accept()))
        agent.pending_dialog = None
        await asyncio.sleep(0.5)
        agent.action_history.append("Accepted dialog")

    elif action_type == "dismiss_dialog":
        print(f"  ❌ Dismiss dialog")
        agent.page.once("dialog", lambda d: asyncio.ensure_future(d.dismiss()))
        agent.pending_dialog = None
        await asyncio.sleep(0.5)
        agent.action_history.append("Dismissed dialog")

    # ─── Utility Actions ───
    elif action_type == "wait":
        seconds = action.get("seconds", 2)
        print(f"  ⏳ Wait {seconds}s")
        await asyncio.sleep(seconds)
        agent.action_history.append(f"Waited {seconds}s")

    elif action_type == "wait_for_element":
        selector = action.get("selector", "")
        timeout = action.get("timeout", 10000)
        print(f"  ⏳ Wait for '{selector}' (timeout={timeout}ms)")
        await agent.page.wait_for_selector(selector, timeout=timeout)
        await asyncio.sleep(0.5)
        agent.action_history.append(f"Waited for '{selector}'")

    elif action_type == "extract_text":
        selector, idx = agent._resolve_selector(action)
        desc = f"[{idx}]" if idx is not None else selector
        el = await agent.page.query_selector(selector)
        text = ""
        if el:
            text = await el.inner_text()
        print(f"  📄 Extract text from {desc}: '{text[:100]}'")
        agent.action_history.append(f"Extracted text from {desc}: '{text[:80]}'")

    elif action_type == "drag_and_drop":
        source_sel = action.get("source_selector", "")
        target_sel = action.get("target_selector", "")
        if "source_index" in action:
            source_sel = f"[data-agent-idx='{action['source_index']}']"
        if "target_index" in action:
            target_sel = f"[data-agent-idx='{action['target_index']}']"
        print(f"  🔄 Drag {source_sel} → {target_sel}")
        await agent.page.drag_and_drop(source_sel, target_sel, timeout=8000)
        await asyncio.sleep(1)
        agent.action_history.append(f"Dragged {source_sel} → {target_sel}")

    # ─── Form Inspection Actions ───
    elif action_type == "verify_form":
        print(f"  📝 Verifying form fields...")
        form_data = await agent.page.evaluate("""
        (() => {
            const fields = [];
            const inputs = document.querySelectorAll('input, textarea, select');
            for (const el of inputs) {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;
                const style = getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') continue;
                const info = {
                    tag: el.tagName.toLowerCase(),
                    type: el.type || 'text',
                    name: el.name || el.id || '',
                    label: '',
                    value: '',
                    required: el.required || false,
                    idx: el.getAttribute('data-agent-idx')
                };
                // Get label
                if (el.id) {
                    const lbl = document.querySelector('label[for="' + el.id + '"]');
                    if (lbl) info.label = lbl.innerText.trim().substring(0, 60);
                }
                if (!info.label) info.label = el.getAttribute('aria-label') || el.placeholder || '';
                // Get value
                if (el.tagName === 'SELECT') {
                    const opt = el.options[el.selectedIndex];
                    info.value = opt ? opt.text.trim() : '';
                } else if (el.type === 'radio' || el.type === 'checkbox') {
                    info.value = el.checked ? 'CHECKED' : 'unchecked';
                    info.label = (info.label || el.value || '').substring(0, 60);
                } else {
                    info.value = (el.value || '').substring(0, 100);
                }
                info.empty = !info.value || info.value === 'unchecked';
                fields.push(info);
            }
            return JSON.stringify(fields);
        })()
        """)
        fields = json.loads(form_data)
        field_report = []
        empty_count = 0
        for f in fields:
            status = "✅" if not f.get("empty") else "❌ EMPTY"
            if f.get("empty"): empty_count += 1
            idx_str = f"[{f['idx']}]" if f.get('idx') else "[-]"
            req = " (REQUIRED)" if f.get("required") else ""
            field_report.append(f"  {idx_str} {status} <{f['tag']}> type={f['type']} name=\"{f['name']}\" label=\"{f.get('label', '')}\" value=\"{f.get('value', '')}\"{req}")
        report = "\n".join(field_report)
        print(f"  📝 Form has {len(fields)} fields ({empty_count} empty):\n{report}")
        agent.action_history.append(f"Verified form: {len(fields)} fields, {empty_count} empty. Fields: {report[:200]}")

    elif action_type == "verify_form_values":
        print(f"  📋 Reading back all form field values...")
        form_data = await agent.page.evaluate("""
        (() => {
            const fields = [];
            const inputs = document.querySelectorAll('input, textarea, select');
            for (const el of inputs) {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;
                const style = getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') continue;
                const info = {
                    tag: el.tagName.toLowerCase(),
                    type: el.type || 'text',
                    name: el.name || el.id || '',
                    label: '',
                    value: '',
                    idx: el.getAttribute('data-agent-idx')
                };
                // Get label
                if (el.id) {
                    const lbl = document.querySelector('label[for="' + el.id + '"]');
                    if (lbl) info.label = lbl.innerText.trim().substring(0, 60);
                }
                if (!info.label) info.label = el.getAttribute('aria-label') || el.placeholder || '';
                // Get FULL value
                if (el.tagName === 'SELECT') {
                    const opt = el.options[el.selectedIndex];
                    info.value = opt ? opt.text.trim() : '';
                } else if (el.type === 'radio' || el.type === 'checkbox') {
                    info.value = el.checked ? 'CHECKED(' + (el.getAttribute('aria-label') || el.value || '') + ')' : 'unchecked';
                } else {
                    info.value = el.value || '';
                }
                fields.push(info);
            }
            return JSON.stringify(fields);
        })()
        """)
        fields = json.loads(form_data)
        value_report = []
        for f in fields:
            idx_str = f"[{f['idx']}]" if f.get('idx') else "[-]"
            label = f.get('label', '') or f.get('name', '')
            val = f.get('value', '')
            val_display = val[:120] + ('...' if len(val) > 120 else '') if val else '(empty)'
            value_report.append(f"  {idx_str} {label}: \"{val_display}\"")
        report = "\n".join(value_report)
        print(f"  📋 Form values ({len(fields)} fields):\n{report}")
        agent.action_history.append(f"Form values readback ({len(fields)} fields):\n{report}")

    elif action_type == "set_value":
        selector, idx = agent._resolve_selector(action)
        value = action.get("value", "")
        desc = f"[{idx}]" if idx is not None else selector
        print(f"  ⚡ Set value of {desc} to '{value}'")
        el = await agent.page.query_selector(selector)
        if el:
            tag = await el.evaluate("e => e.tagName")
            input_type = await el.evaluate("e => e.type || ''")
            if tag == "SELECT":
                await agent.page.select_option(selector, value=value, timeout=5000)
            elif input_type in ("date", "time", "datetime-local", "month", "week", "color", "range"):
                # Direct .value assignment on the element ref avoids Illegal invocation
                await el.evaluate("(e, v) => { e.value = v; e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true})); }", value)
            else:
                # For text/textarea, use Playwright's fill() which is most reliable
                await el.fill(value)
        else:
            print(f"  ⚠ Element not found: {selector}")
        await asyncio.sleep(0.5)
        agent.action_history.append(f"Set value of {desc} to '{value}'")

    elif action_type == "get_element_html":
        selector, idx = agent._resolve_selector(action)
        desc = f"[{idx}]" if idx is not None else selector
        print(f"  🔍 Inspecting HTML of {desc}")
        html = await agent.page.evaluate(
            """(selector) => {
                const el = document.querySelector(selector);
                if (!el) return 'Element not found';
                return el.outerHTML.substring(0, 2000);
            }""",
            selector
        )
        print(f"  🔍 HTML: {html[:300]}")
        agent.action_history.append(f"HTML of {desc}: {html[:300]}")

    elif action_type == "fetch_section_html":
        selector = action.get("selector", "")
        if "index" in action:
            selector, idx = agent._resolve_selector(action)
        else:
            idx = None
        max_len = action.get("max_length", 5000)
        desc = f"[{idx}]" if idx is not None else selector
        print(f"  📄 Fetching section HTML from {desc} (max {max_len} chars)")
        html = await agent.page.evaluate(
            """(args) => {
                const el = document.querySelector(args.selector);
                if (!el) return 'Element not found';
                return el.innerHTML.substring(0, args.maxLen);
            }""",
            {"selector": selector, "maxLen": max_len}
        )
        print(f"  📄 Section HTML ({len(html)} chars): {html[:200]}...")
        agent.action_history.append(f"Fetched section HTML from {desc} ({len(html)} chars): {html[:300]}")

    elif action_type == "run_js":
        code = action.get("code", "")
        print(f"  🔧 Running JS: {code[:100]}")
        try:
            result = await agent.page.evaluate(code)
            result_str = json.dumps(result, ensure_ascii=False) if result is not None else "undefined"
            if len(result_str) > 2000:
                result_str = result_str[:2000] + "...[truncated]"
            print(f"  🔧 JS result: {result_str[:200]}")
            agent.action_history.append(f"JS result: {result_str[:500]}")
        except Exception as e:
            print(f"  ⚠ JS error: {e}")
            agent.action_history.append(f"JS error: {str(e)[:200]}")

    elif action_type == "capture_screenshot_ocr":
        print(f"  👁 Manual OCR capture requested")
        await agent._capture_vision_snapshot()
        if agent.vision_context:
            print(f"  👁 OCR captured: {len(agent.vision_context)} chars")
            agent.action_history.append(f"OCR captured ({len(agent.vision_context)} chars): {agent.vision_context[:300]}")
        else:
            agent.action_history.append("OCR capture failed or returned no result")

    # ─── Memory Actions ───
    elif action_type == "save_memory":
        domain = action.get("domain", "_general")
        note = action.get("note", "")
        if note:
            agent.memory.write(domain, note)
            print(f"  🧠 Memory saved [{domain}]: {note[:80]}")
            agent.action_history.append(f"Saved memory [{domain}]: {note[:60]}")
        else:
            print(f"  ⚠ Empty memory note, skipped")

    # ─── File Actions ───
    elif action_type == "write_to_file":
        filename = action.get("filename", "output.txt")
        content = action.get("content", "")
        # Safety: only allow filenames, no path traversal
        filename = os.path.basename(filename)
        try:
            with open(filename, "a", encoding="utf-8") as f:
                f.write(content + "\n")
            print(f"  📝 Wrote to {filename}: {content[:80]}")
            
            # Immediately verify the write by reading back the last line
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    if lines:
                        last_line = lines[-1].rstrip("\n")
                        if last_line == content:
                            print(f"  ✅ Verified: File write successful")
                            agent.action_history.append(f"Wrote to {filename}: {content[:50]} [VERIFIED]")
                        else:
                            print(f"  ⚠ Verification mismatch: Expected '{content[:50]}...' but got '{last_line[:50]}...'")
                            agent.action_history.append(f"Wrote to {filename} but verification failed")
                    else:
                        print(f"  ⚠ Verification failed: File is empty after write")
                        agent.action_history.append(f"Wrote to {filename} but file appears empty")
            except Exception as verify_err:
                print(f"  ⚠ Verification error: {verify_err}")
                agent.action_history.append(f"Wrote to {filename}: {content[:50]} [verification failed: {verify_err}]")
        except Exception as e:
            print(f"  ⚠ File write error: {e}")
            agent.action_history.append(f"FAILED write to {filename}: {e}")

    elif action_type == "read_file":
        filename = action.get("filename", "output.txt")
        filename = os.path.basename(filename)
        try:
            if os.path.exists(filename):
                with open(filename, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                # Show last 50 lines if file is large
                if len(lines) > 50:
                    content = f"[...{len(lines)-50} earlier lines...]\n" + "".join(lines[-50:])
                else:
                    content = "".join(lines)
                print(f"  📖 Read {filename}: {len(lines)} lines")
                agent.action_history.append(f"Read {filename} ({len(lines)} lines): {content[:100]}")
            else:
                print(f"  📖 File {filename} does not exist yet")
                agent.action_history.append(f"File {filename} not found (empty)")
        except Exception as e:
            print(f"  ⚠ File read error: {e}")
            agent.action_history.append(f"FAILED read {filename}: {e}")

    # ─── Skill Actions ───
    elif action_type == "check_duplicate":
        item = action.get("item", "")
        if hasattr(agent, 'duplicate_tracker') and agent.duplicate_tracker:
            is_dup = agent.duplicate_tracker.is_done(item)
            status = "DUPLICATE" if is_dup else "NEW"
            print(f"  🔍 Duplicate check '{item[:60]}': {status}")
            agent.action_history.append(f"Duplicate check: {item[:50]} → {status}")
        else:
            print(f"  ⚠ No duplicate tracker loaded (no skill file?)")
            agent.action_history.append(f"Duplicate check skipped (no tracker): {item[:50]}")

    elif action_type == "mark_completed_item":
        item = action.get("item", "")
        if hasattr(agent, 'duplicate_tracker') and agent.duplicate_tracker:
            agent.duplicate_tracker.mark_done(item)
            # Increment answer counter
            if hasattr(agent, 'answers_count'):
                agent.answers_count += 1
                print(f"  📊 Answer count: {agent.answers_count}")
                # Check if we need to switch profiles
                if hasattr(agent, 'skill_config') and agent.skill_config:
                    from .profile_manager import should_switch_profile
                    if should_switch_profile(agent.skill_config, agent.answers_count):
                        print(f"  🔄 Reached {agent.answers_count} answers — profile switch recommended")
                        agent.action_history.append(f"Marked complete: {item[:50]} (answer #{agent.answers_count} — switch profile recommended)")
                    else:
                        agent.action_history.append(f"Marked complete: {item[:50]} (answer #{agent.answers_count})")
                else:
                    agent.action_history.append(f"Marked complete: {item[:50]} (answer #{agent.answers_count})")
            else:
                agent.action_history.append(f"Marked complete: {item[:50]}")
        else:
            print(f"  ⚠ No duplicate tracker loaded (no skill file?)")
            agent.action_history.append(f"Mark complete skipped (no tracker): {item[:50]}")

    elif action_type == "switch_profile":
        profile_name = action.get("profile_name", "")
        if hasattr(agent, 'skill_config') and agent.skill_config:
            from .profile_manager import get_next_profile
            if not profile_name:
                current = getattr(agent, 'current_profile', agent.skill_config.active_profile)
                profile_name = get_next_profile(agent.skill_config, current)
            if profile_name:
                print(f"  🔄 Profile switch requested → {profile_name}")
                agent.action_history.append(f"Profile switch → {profile_name}")
                # Signal the outer loop to restart with new profile
                agent._switch_to_profile = profile_name
                return "switch_profile"
            else:
                print(f"  ⚠ No next profile available (only 1 profile defined)")
                agent.action_history.append("Profile switch failed: only 1 profile")
        else:
            print(f"  ⚠ No skill config loaded — cannot switch profiles")
            agent.action_history.append("Profile switch failed: no skill config")

    # ─── Completion Actions ───
    elif action_type == "goal_completed":
        reason = action.get("reason", "Goal completed")
        print(f"\n  🎉 GOAL COMPLETED: {reason}")
        return "completed"

    elif action_type == "goal_failed":
        reason = action.get("reason", "Goal could not be achieved")
        print(f"\n  💀 GOAL FAILED: {reason}")
        return "failed"

    else:
        print(f"  ⚠ Unknown action: {action_type}")
        agent.action_history.append(f"Unknown action: {action_type}")

    return "continue"
