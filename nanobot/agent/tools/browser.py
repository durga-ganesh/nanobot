"""Browser automation tool using Playwright."""

import asyncio
import uuid
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger

from nanobot.agent.tools.base import Tool


@dataclass
class BrowserSession:
    """Represents a persistent browser session."""
    session_id: str
    context: Any  # BrowserContext from Playwright
    page: Any  # Page from Playwright
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    current_url: str = "about:blank"

    def update_last_used(self):
        self.last_used = datetime.now()


class BrowserTool(Tool):
    """
    Agentic browser automation tool.

    Enables the agent to interact with web pages like a human:
    - Navigate to URLs
    - Click buttons and links
    - Fill forms
    - Take screenshots for vision
    - Extract content
    """

    def __init__(
        self,
        headless: bool = False,
        timeout: int = 30000,
        allowed_domains: list[str] | None = None,
        max_sessions: int = 5,
        session_timeout: int = 300,  # 5 minutes
        screenshots_dir: Path | None = None,
    ):
        self.headless = headless
        self.timeout = timeout
        self.allowed_domains = allowed_domains or []  # Empty = allow all
        self.max_sessions = max_sessions
        self.session_timeout = session_timeout
        self.screenshots_dir = screenshots_dir or Path.home() / ".nanobot" / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

        # Browser state
        self._playwright = None
        self._browser = None
        self._sessions: dict[str, BrowserSession] = {}
        self._initialized = False

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return """Execute browser actions to interact with websites.

Can navigate, click, type, fill forms, take screenshots, and extract content.
Use this for web automation tasks like online shopping, form filling, or web scraping.

Sessions persist across calls - reuse session_id to continue in the same browser context."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "navigate",
                        "click",
                        "type",
                        "fill",
                        "screenshot",
                        "extract_text",
                        "extract_html",
                        "wait_for",
                        "scroll",
                        "go_back",
                        "go_forward",
                        "get_url",
                        "close_session",
                    ],
                    "description": "The browser action to perform"
                },
                "url": {
                    "type": "string",
                    "description": "URL to navigate to (for navigate action)"
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector for element (e.g., 'button.submit', '#search-box')"
                },
                "text": {
                    "type": "string",
                    "description": "Text to type or selector text to find (e.g., 'text=Add to Cart')"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Action timeout in milliseconds (default: 30000)"
                },
                "session_id": {
                    "type": "string",
                    "description": "Browser session ID. Omit to create new session, or provide to reuse existing."
                },
                "full_page": {
                    "type": "boolean",
                    "description": "Whether to capture full page screenshot (default: false)"
                },
                "wait_until": {
                    "type": "string",
                    "enum": ["load", "domcontentloaded", "networkidle"],
                    "description": "When to consider navigation complete (default: load)"
                }
            },
            "required": ["action"]
        }

    async def execute(
        self,
        action: str,
        url: str | None = None,
        selector: str | None = None,
        text: str | None = None,
        timeout: int | None = None,
        session_id: str | None = None,
        full_page: bool = False,
        wait_until: str = "load",
        **kwargs: Any
    ) -> str:
        """Execute a browser action."""
        try:
            # Initialize browser if needed
            if not self._initialized:
                await self._initialize()

            # Get or create session
            session = await self._get_or_create_session(session_id)
            session.update_last_used()

            # Clean up old sessions
            await self._cleanup_old_sessions()

            # Execute action
            timeout_ms = timeout or self.timeout

            # Prepare result with session_id prefix for all actions
            result_prefix = f"[Session: {session.session_id}]\n"

            if action == "navigate":
                result = await self._navigate(session, url, wait_until, timeout_ms)

            elif action == "click":
                result = await self._click(session, selector, text, timeout_ms)

            elif action == "type":
                result = await self._type(session, selector, text, timeout_ms)

            elif action == "fill":
                result = await self._fill(session, selector, text, timeout_ms)

            elif action == "screenshot":
                result = await self._screenshot(session, full_page)

            elif action == "extract_text":
                result = await self._extract_text(session, selector)

            elif action == "extract_html":
                result = await self._extract_html(session, selector)

            elif action == "wait_for":
                result = await self._wait_for(session, selector, timeout_ms)

            elif action == "scroll":
                result = await self._scroll(session, selector)

            elif action == "go_back":
                await session.page.go_back(timeout=timeout_ms)
                session.current_url = session.page.url
                result = f"Navigated back to: {session.page.url}"

            elif action == "go_forward":
                await session.page.go_forward(timeout=timeout_ms)
                session.current_url = session.page.url
                result = f"Navigated forward to: {session.page.url}"

            elif action == "get_url":
                result = f"Current URL: {session.page.url}\nTitle: {await session.page.title()}"

            elif action == "close_session":
                await self._close_session(session.session_id)
                return f"Closed browser session {session.session_id}"

            else:
                return f"Error: Unknown action '{action}'"

            # Return result with session_id so it can be reused
            return result_prefix + result

        except Exception as e:
            logger.error(f"Browser tool error: {e}")
            return f"Browser error: {str(e)}"

    async def _initialize(self) -> None:
        """Initialize Playwright and browser."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "Playwright is not installed. Install it with: pip install playwright && playwright install chromium"
            )

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._initialized = True
        logger.info("Browser tool initialized")

    async def _get_or_create_session(self, session_id: str | None) -> BrowserSession:
        """Get existing session or create new one."""
        # If session_id provided, try to reuse
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]

        # Create new session
        if len(self._sessions) >= self.max_sessions:
            # Remove oldest session
            oldest_id = min(self._sessions.keys(), key=lambda k: self._sessions[k].last_used)
            await self._close_session(oldest_id)

        # Generate session ID if not provided
        new_session_id = session_id or str(uuid.uuid4())[:8]

        # Create browser context and page
        context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()

        session = BrowserSession(
            session_id=new_session_id,
            context=context,
            page=page,
        )

        self._sessions[new_session_id] = session
        logger.info(f"Created browser session: {new_session_id}")

        return session

    async def _navigate(
        self,
        session: BrowserSession,
        url: str,
        wait_until: str,
        timeout: int
    ) -> str:
        """Navigate to a URL."""
        if not url:
            return "Error: URL is required for navigate action"

        # Check domain restrictions
        if self.allowed_domains:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc
            if not any(allowed in domain for allowed in self.allowed_domains):
                return f"Error: Domain {domain} not in allowed list: {self.allowed_domains}"

        try:
            await session.page.goto(url, wait_until=wait_until, timeout=timeout)
            session.current_url = session.page.url
            title = await session.page.title()

            # Get page summary
            summary = await self._get_page_summary(session.page)

            return f"Navigated to: {session.page.url}\nTitle: {title}\n\n{summary}"

        except Exception as e:
            return f"Navigation failed: {str(e)}"

    async def _click(
        self,
        session: BrowserSession,
        selector: str | None,
        text: str | None,
        timeout: int
    ) -> str:
        """Click an element."""
        try:
            # Support text selectors like "text=Add to Cart"
            if text and not selector:
                selector = f"text={text}"

            if not selector:
                return "Error: Either selector or text is required for click action"

            await session.page.click(selector, timeout=timeout)

            # Wait a bit for page to update
            await asyncio.sleep(0.5)

            return f"Clicked element: {selector}\nCurrent URL: {session.page.url}"

        except Exception as e:
            return f"Click failed: {str(e)}"

    async def _type(
        self,
        session: BrowserSession,
        selector: str,
        text: str,
        timeout: int
    ) -> str:
        """Type text into an element."""
        if not selector or not text:
            return "Error: Both selector and text are required for type action"

        try:
            await session.page.type(selector, text, timeout=timeout)
            return f"Typed '{text}' into: {selector}"

        except Exception as e:
            return f"Type failed: {str(e)}"

    async def _fill(
        self,
        session: BrowserSession,
        selector: str,
        text: str,
        timeout: int
    ) -> str:
        """Fill an input field (replaces existing content)."""
        if not selector or not text:
            return "Error: Both selector and text are required for fill action"

        try:
            await session.page.fill(selector, text, timeout=timeout)
            return f"Filled '{text}' into: {selector}"

        except Exception as e:
            return f"Fill failed: {str(e)}"

    async def _screenshot(
        self,
        session: BrowserSession,
        full_page: bool
    ) -> str:
        """Take a screenshot and return description + path."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{session.session_id}_{timestamp}.png"
            filepath = self.screenshots_dir / filename

            await session.page.screenshot(path=str(filepath), full_page=full_page)

            # Also get page summary
            summary = await self._get_page_summary(session.page)

            return f"""Screenshot saved: {filepath}
URL: {session.page.url}
Title: {await session.page.title()}

Page content:
{summary}

Note: You can analyze this screenshot if you have vision capabilities."""

        except Exception as e:
            return f"Screenshot failed: {str(e)}"

    async def _extract_text(
        self,
        session: BrowserSession,
        selector: str | None
    ) -> str:
        """Extract text content from element(s)."""
        try:
            if selector:
                # Extract from specific selector
                elements = await session.page.query_selector_all(selector)
                if not elements:
                    return f"No elements found matching: {selector}"

                texts = []
                for elem in elements[:10]:  # Limit to first 10
                    text = await elem.text_content()
                    if text:
                        texts.append(text.strip())

                return "\n".join(texts)
            else:
                # Extract all text from body
                body = await session.page.query_selector("body")
                if body:
                    text = await body.text_content()
                    return text[:5000] if text else "No content found"  # Limit output
                return "No content found"

        except Exception as e:
            return f"Extract failed: {str(e)}"

    async def _extract_html(
        self,
        session: BrowserSession,
        selector: str | None
    ) -> str:
        """Extract HTML from element."""
        try:
            if selector:
                elem = await session.page.query_selector(selector)
                if not elem:
                    return f"No element found matching: {selector}"
                html = await elem.inner_html()
            else:
                html = await session.page.content()

            # Limit output size
            if len(html) > 10000:
                html = html[:10000] + "\n... (truncated)"

            return html

        except Exception as e:
            return f"Extract HTML failed: {str(e)}"

    async def _wait_for(
        self,
        session: BrowserSession,
        selector: str,
        timeout: int
    ) -> str:
        """Wait for element to appear."""
        if not selector:
            return "Error: Selector is required for wait_for action"

        try:
            await session.page.wait_for_selector(selector, timeout=timeout)
            return f"Element appeared: {selector}"

        except Exception as e:
            return f"Wait failed: {str(e)}"

    async def _scroll(
        self,
        session: BrowserSession,
        selector: str | None
    ) -> str:
        """Scroll page or to element."""
        try:
            if selector:
                # Scroll to element
                await session.page.eval_on_selector(
                    selector,
                    "el => el.scrollIntoView({behavior: 'smooth'})"
                )
                return f"Scrolled to: {selector}"
            else:
                # Scroll to bottom
                await session.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                return "Scrolled to bottom of page"

        except Exception as e:
            return f"Scroll failed: {str(e)}"

    async def _get_page_summary(self, page: Any) -> str:
        """Get a summary of the current page for the LLM."""
        try:
            # Extract key information
            summary_parts = []

            # Get page text content (first 1000 chars for context)
            try:
                body = await page.query_selector("body")
                if body:
                    text = await body.inner_text()
                    if text:
                        # Clean up and truncate
                        text = " ".join(text.split())[:1000]
                        summary_parts.append(f"Page text preview:\n{text}...")
            except:
                pass

            # Add headings for structure
            headings = await page.query_selector_all("h1, h2, h3")
            if headings:
                heading_texts = []
                for h in headings[:5]:
                    text = await h.text_content()
                    if text:
                        heading_texts.append(text.strip())
                if heading_texts:
                    summary_parts.append(f"\nHeadings: {', '.join(heading_texts)}")

            # Add interactive elements
            buttons = await page.query_selector_all("button, input[type='button'], input[type='submit']")
            if buttons:
                button_texts = []
                for btn in buttons[:10]:  # First 10 buttons
                    text = await btn.text_content() or await btn.get_attribute("value") or ""
                    if text:
                        button_texts.append(text.strip())
                if button_texts:
                    summary_parts.append(f"\nButtons: {', '.join(button_texts)}")

            # Add input fields
            inputs = await page.query_selector_all("input[type='text'], input[type='email'], input[type='search'], textarea")
            if inputs:
                input_names = []
                for inp in inputs[:10]:
                    name = await inp.get_attribute("name") or await inp.get_attribute("placeholder") or ""
                    if name:
                        input_names.append(name.strip())
                if input_names:
                    summary_parts.append(f"\nInput fields: {', '.join(input_names)}")

            # Add links (just count)
            links = await page.query_selector_all("a[href]")
            if len(links) > 0:
                summary_parts.append(f"\n{len(links)} links found on page")

            return "\n".join(summary_parts) if summary_parts else "Page loaded successfully"

        except Exception as e:
            return f"Could not generate page summary: {str(e)}"

    async def _close_session(self, session_id: str) -> None:
        """Close and remove a browser session."""
        if session_id in self._sessions:
            session = self._sessions[session_id]
            await session.context.close()
            del self._sessions[session_id]
            logger.info(f"Closed browser session: {session_id}")

    async def _cleanup_old_sessions(self) -> None:
        """Remove sessions that haven't been used recently."""
        now = datetime.now()
        to_remove = []

        for session_id, session in self._sessions.items():
            age = (now - session.last_used).total_seconds()
            if age > self.session_timeout:
                to_remove.append(session_id)

        if to_remove:
            logger.info(f"Cleaning up {len(to_remove)} idle browser session(s)")

        for session_id in to_remove:
            await self._close_session(session_id)

    async def close_all_sessions(self) -> None:
        """Close all active browser sessions immediately."""
        session_count = len(self._sessions)
        if session_count > 0:
            logger.info(f"Closing all {session_count} browser session(s)")
            for session_id in list(self._sessions.keys()):
                await self._close_session(session_id)

    async def cleanup(self) -> None:
        """Cleanup all browser resources."""
        for session_id in list(self._sessions.keys()):
            await self._close_session(session_id)

        if self._browser:
            await self._browser.close()

        if self._playwright:
            await self._playwright.stop()

        self._initialized = False
        logger.info("Browser tool cleaned up")
