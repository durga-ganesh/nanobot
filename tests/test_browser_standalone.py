#!/usr/bin/env python3
"""Standalone test for the browser tool."""

import asyncio
from pathlib import Path

from nanobot.agent.tools.browser import BrowserTool


def extract_session_id(result: str) -> str | None:
    """Extract session_id from browser tool result."""
    if result.startswith("[Session: "):
        end = result.find("]")
        if end != -1:
            return result[10:end]
    return None


async def test_browser():
    """Test the browser tool in isolation."""

    print("🔧 Initializing browser tool...")
    browser = BrowserTool(
        headless=False,  # Set to True if you don't want to see the browser
        timeout=30000,
        screenshots_dir=Path.home() / ".nanobot" / "test_screenshots"
    )

    session_id = None

    try:
        print("\n✅ Test 1: Navigate to a website")
        result = await browser.execute(
            action="navigate",
            url="https://example.com",
            session_id=session_id
        )
        session_id = extract_session_id(result)
        print(f"Result: {result}")
        print(f"📌 Session ID: {session_id}")

        print("\n✅ Test 2: Get current URL (reusing session)")
        result = await browser.execute(
            action="get_url",
            session_id=session_id
        )
        print(f"Result: {result}")

        print("\n✅ Test 3: Extract text from page (reusing session)")
        result = await browser.execute(
            action="extract_text",
            selector="h1",
            session_id=session_id
        )
        print(f"Result: {result}")

        print("\n✅ Test 4: Take screenshot (reusing session)")
        result = await browser.execute(
            action="screenshot",
            full_page=True,
            session_id=session_id
        )
        print(f"Result: {result}")

        print("\n✅ Test 5: Navigate to another page (reusing session)")
        result = await browser.execute(
            action="navigate",
            url="https://httpbin.org/html",
            session_id=session_id
        )
        print(f"Result: {result}")

        print("\n✅ Test 6: Extract all text (reusing session)")
        result = await browser.execute(
            action="extract_text",
            session_id=session_id
        )
        print(f"Result: {result[:500]}...")  # Print first 500 chars

        print("\n✅ Test 7: Close the session")
        result = await browser.execute(
            action="close_session",
            session_id=session_id
        )
        print(f"Result: {result}")

        print("\n✅ All tests passed!")

    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("\n🧹 Cleaning up browser...")
        await browser.cleanup()
        print("✅ Done!")


if __name__ == "__main__":
    asyncio.run(test_browser())
