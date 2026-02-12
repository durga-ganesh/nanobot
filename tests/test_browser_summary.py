#!/usr/bin/env python3
"""Test the improved page summary."""

import asyncio
from pathlib import Path

from nanobot.agent.tools.browser import BrowserTool


async def test_page_summary():
    """Test that page summaries provide useful context."""

    print("🔧 Testing page summaries...")
    browser = BrowserTool(
        headless=True,  # Use headless for this test
        timeout=30000,
        screenshots_dir=Path.home() / ".nanobot" / "test_screenshots"
    )

    try:
        # Test 1: Example.com (simple page)
        print("\n📄 Test 1: example.com")
        result = await browser.execute(
            action="navigate",
            url="https://example.com"
        )
        print(result)
        print("-" * 80)

        # Test 2: Google (complex page with forms)
        print("\n📄 Test 2: Google homepage")
        result = await browser.execute(
            action="navigate",
            url="https://www.google.com"
        )
        print(result)
        print("-" * 80)

        # Test 3: News site (lots of text)
        print("\n📄 Test 3: Hacker News")
        result = await browser.execute(
            action="navigate",
            url="https://news.ycombinator.com"
        )
        print(result)
        print("-" * 80)

        print("\n✅ Summary test completed!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await browser.cleanup()


if __name__ == "__main__":
    asyncio.run(test_page_summary())
