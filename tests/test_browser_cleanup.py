#!/usr/bin/env python3
"""Test browser session cleanup."""

import asyncio
from pathlib import Path

from nanobot.agent.tools.browser import BrowserTool


async def test_session_cleanup():
    """Test that browser sessions are cleaned up after timeout."""

    print("🔧 Testing session cleanup...")
    browser = BrowserTool(
        headless=True,
        timeout=30000,
        session_timeout=5,  # 5 seconds for testing
        screenshots_dir=Path.home() / ".nanobot" / "test_screenshots"
    )

    try:
        # Create session 1
        print("\n✅ Creating session 1...")
        result = await browser.execute(
            action="navigate",
            url="https://example.com"
        )
        print(f"Active sessions: {len(browser._sessions)}")

        # Create session 2
        print("\n✅ Creating session 2...")
        result = await browser.execute(
            action="navigate",
            url="https://httpbin.org/html"
        )
        print(f"Active sessions: {len(browser._sessions)}")

        # Wait for timeout
        print("\n⏳ Waiting 6 seconds for sessions to timeout...")
        await asyncio.sleep(6)

        # Trigger cleanup by making a new request
        print("\n✅ Creating session 3 (should trigger cleanup)...")
        result = await browser.execute(
            action="navigate",
            url="https://news.ycombinator.com"
        )
        print(f"Active sessions after cleanup: {len(browser._sessions)}")

        # Test close_all_sessions
        print("\n✅ Creating 2 more sessions...")
        await browser.execute(action="navigate", url="https://example.com")
        await browser.execute(action="navigate", url="https://example.com")
        print(f"Active sessions before close_all: {len(browser._sessions)}")

        print("\n🧹 Calling close_all_sessions()...")
        await browser.close_all_sessions()
        print(f"Active sessions after close_all: {len(browser._sessions)}")

        print("\n✅ Cleanup test completed!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await browser.cleanup()


if __name__ == "__main__":
    asyncio.run(test_session_cleanup())
