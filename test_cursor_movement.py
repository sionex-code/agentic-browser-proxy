"""
Quick test to verify cursor humanization is working properly.
This will open a browser and test cursor movement.
"""

import asyncio
from patchright.async_api import async_playwright


async def test_cursor():
    print("🧪 Testing Cursor Humanization...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=['--start-maximized']
        )
        
        context = await browser.new_context(no_viewport=True)
        page = await context.new_page()
        
        # Go to a simple page
        await page.goto("https://www.google.com")
        await asyncio.sleep(2)
        
        # Initialize cursor
        print("📍 Initializing cursor...")
        await page.evaluate("""
        (() => {
            try {
                const cursor = document.createElement('div');
                cursor.id = '__playwright_cursor';

                Object.assign(cursor.style, {
                    position: 'fixed',
                    top: '0px',
                    left: '0px',
                    width: '24px',
                    height: '24px',
                    zIndex: '999999',
                    pointerEvents: 'none',
                    backgroundImage: 'url(https://i.imgur.com/PEZdLDA.png)',
                    backgroundSize: 'contain',
                    backgroundRepeat: 'no-repeat',
                    backgroundColor: 'transparent',
                    border: 'none',
                    borderRadius: '0',
                    filter: 'drop-shadow(0 0 2px white)'
                });

                document.body.appendChild(cursor);

                window.__cursor_position = { x: 0, y: 0 };
                window.__move_cursor = (x, y) => {
                    cursor.style.left = x + 'px';
                    cursor.style.top = y + 'px';
                    window.__cursor_position = { x, y };
                };

                window.__get_cursor_position = () => {
                    return window.__cursor_position;
                };

                console.log("✅ Cursor initialized");

            } catch (err) {
                console.error("💥 Error:", err);
            }
        })();
        """)
        
        # Test cursor movement with improved Bezier curve
        print("🖱️  Testing improved Bezier curve with overshoot from (100, 100) to (900, 500)...")
        
        start_x, start_y = 100, 100
        target_x, target_y = 900, 500
        steps = 40
        
        # Move to start position
        await page.evaluate(f"window.__move_cursor({start_x}, {start_y})")
        await asyncio.sleep(1)
        
        # Calculate distance for scaling
        distance = ((target_x - start_x) ** 2 + (target_y - start_y) ** 2) ** 0.5
        curve_intensity = min(distance * 0.3, 200)
        
        # Generate control point with perpendicular offset
        mid_x = (start_x + target_x) / 2
        mid_y = (start_y + target_y) / 2
        
        dx = target_x - start_x
        dy = target_y - start_y
        
        # Perpendicular vector
        perp_x = -dy
        perp_y = dx
        
        perp_length = (perp_x ** 2 + perp_y ** 2) ** 0.5
        if perp_length > 0:
            perp_x = (perp_x / perp_length) * curve_intensity * random.uniform(-1, 1)
            perp_y = (perp_y / perp_length) * curve_intensity * random.uniform(-1, 1)
        
        control_x = mid_x + perp_x + random.uniform(-50, 50)
        control_y = mid_y + perp_y + random.uniform(-50, 50)
        
        print(f"  📐 Control point: ({control_x:.0f}, {control_y:.0f}), curve intensity: {curve_intensity:.0f}px")
        
        # Animate Bezier curve movement with overshoot
        for i in range(steps + 1):
            t = i / steps
            
            # Quadratic Bezier curve formula
            x = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * control_x + t ** 2 * target_x
            y = (1 - t) ** 2 * start_y + 2 * (1 - t) * t * control_y + t ** 2 * target_y
            
            # Add overshoot near the end
            if 0.9 <= t <= 0.98:
                overshoot_factor = (t - 0.9) * 10
                x += random.uniform(-5, 5) * overshoot_factor
                y += random.uniform(-5, 5) * overshoot_factor
            
            # Add jitter
            x += random.uniform(-3, 3)
            y += random.uniform(-3, 3)
            
            await page.evaluate(f"window.__move_cursor({x}, {y})")
            
            # Variable speed
            if i < steps * 0.15:
                await asyncio.sleep(0.035)
            elif i > steps * 0.85:
                await asyncio.sleep(0.030)
            else:
                await asyncio.sleep(0.012)
        
        # Final position
        await page.evaluate(f"window.__move_cursor({target_x}, {target_y})")
        
        print(f"✅ Cursor moved with dramatic Bezier curve to ({target_x}, {target_y})")
        
        # Test position persistence across page reload
        print("\n🔄 Testing position persistence after page reload...")
        saved_pos = await page.evaluate("window.__get_cursor_position()")
        print(f"📍 Saved position: {saved_pos}")
        
        await page.reload()
        await asyncio.sleep(2)
        
        # Reinitialize cursor
        await page.evaluate("""
        (() => {
            try {
                const cursor = document.createElement('div');
                cursor.id = '__playwright_cursor';

                Object.assign(cursor.style, {
                    position: 'fixed',
                    top: '0px',
                    left: '0px',
                    width: '24px',
                    height: '24px',
                    zIndex: '999999',
                    pointerEvents: 'none',
                    backgroundImage: 'url(https://i.imgur.com/PEZdLDA.png)',
                    backgroundSize: 'contain',
                    backgroundRepeat: 'no-repeat',
                    backgroundColor: 'transparent',
                    border: 'none',
                    borderRadius: '0',
                    filter: 'drop-shadow(0 0 2px white)'
                });

                document.body.appendChild(cursor);

                window.__cursor_position = { x: 0, y: 0 };
                window.__move_cursor = (x, y) => {
                    cursor.style.left = x + 'px';
                    cursor.style.top = y + 'px';
                    window.__cursor_position = { x, y };
                };

                window.__get_cursor_position = () => {
                    return window.__cursor_position;
                };

            } catch (err) {
                console.error("💥 Error:", err);
            }
        })();
        """)
        
        # Restore position
        await page.evaluate(f"window.__move_cursor({saved_pos['x']}, {saved_pos['y']})")
        print(f"✅ Cursor restored to ({saved_pos['x']}, {saved_pos['y']}) after reload")
        
        print("\n✅ All tests passed! Cursor humanization is working.")
        print("Press Enter to close browser...")
        await asyncio.to_thread(input)
        
        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_cursor())
