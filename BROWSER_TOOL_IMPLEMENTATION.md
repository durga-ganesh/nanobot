# Browser Tool Implementation Guide

**Goal:** Add agentic browser automation to nanobot, enabling the agent to interact with websites like a human - navigate, click, fill forms, and complete tasks.

**Date:** 2026-02-10

---

## 🎯 Architecture Fit

**Perfect Match!** The existing tool pattern in nanobot is ideal for browser automation:

```
Current:  Agent → shell.py → Execute bash commands
New:      Agent → browser.py → Execute browser actions
```

**Key Similarities:**
- Both extend the `Tool` base class
- Both have async `execute()` methods
- Both return string results to the LLM
- Both need safety guards
- Both maintain state (shell has cwd, browser has session)

---

## 🔧 Technology Stack

### Recommended: **Playwright**

**Why Playwright over Selenium?**

✅ **Async-native** - Built for asyncio (perfect for nanobot)
✅ **Modern API** - Cleaner, more intuitive
✅ **Better debugging** - Screenshots, videos, traces
✅ **Multi-browser** - Chromium, Firefox, WebKit
✅ **No driver management** - Auto-downloads browsers
✅ **Headless by default** - Can run in Docker
✅ **Waiting built-in** - Auto-waits for elements

**Installation:**
```bash
pip install playwright
playwright install chromium  # Downloads browser
```

**Dependencies to add to `pyproject.toml`:**
```toml
dependencies = [
    ...
    "playwright>=1.40.0",
]
```

---

## 🏗️ Architecture Design

### Component Structure

```
nanobot/agent/tools/
├── browser.py              # Main browser tool
├── browser_session.py      # Session management
└── browser_actions.py      # Action primitives
```

### Session Management Strategy

**Challenge:** Browser state must persist across LLM tool calls

**Solution:** Maintain browser context pool

```python
# Agent says: "Navigate to amazon.com"
# → Creates browser context, navigates
# → Returns "Navigated to Amazon homepage"

# Agent says: "Search for 'laptop'"
# → Reuses same browser context
# → Returns "Found 1,234 results"

# Agent says: "Click first result"
# → Still same browser context
# → Returns "Opened product page for Dell XPS"
```

---

## 📐 Tool Design

### 1. BrowserTool Class

**File:** `nanobot/agent/tools/browser.py`

**Key Features:**
- Multiple action types (navigate, click, type, screenshot, etc.)
- Vision integration (LLM sees page screenshots)
- Session management (persistent browser contexts)
- Safety guards (domain restrictions, timeout)
- Accessibility tree for navigation

**Tool Interface:**

```python
class BrowserTool(Tool):
    """
    Agentic browser automation tool.

    Allows the agent to:
    - Navigate to URLs
    - Click elements
    - Fill forms
    - Take screenshots
    - Extract content
    - Wait for conditions
    """

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30000,  # 30 seconds
        allowed_domains: list[str] | None = None,
        viewport_width: int = 1280,
        viewport_height: int = 720,
    ):
        self.headless = headless
        self.timeout = timeout
        self.allowed_domains = allowed_domains or []
        self.viewport = {"width": viewport_width, "height": viewport_height}
        self._sessions: dict[str, BrowserSession] = {}
        self._playwright = None
        self._browser = None
```

### 2. Action Types

The tool should support multiple action types in a single tool:

```json
{
  "action": "navigate",
  "url": "https://amazon.com"
}

{
  "action": "click",
  "selector": "button[aria-label='Search']"
}

{
  "action": "type",
  "selector": "input[name='q']",
  "text": "laptop"
}

{
  "action": "screenshot",
  "full_page": false
}

{
  "action": "extract",
  "selector": "h1.product-title"
}

{
  "action": "wait_for",
  "selector": "div.search-results",
  "timeout": 5000
}
```

**Parameters Schema:**

```python
@property
def parameters(self) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "navigate",      # Go to URL
                    "click",         # Click element
                    "type",          # Type text
                    "fill",          # Fill input
                    "select",        # Select dropdown
                    "screenshot",    # Capture page
                    "extract",       # Get text/HTML
                    "wait_for",      # Wait for element
                    "scroll",        # Scroll page
                    "go_back",       # Browser back
                    "go_forward",    # Browser forward
                    "close",         # Close session
                ],
                "description": "The browser action to perform"
            },
            "url": {
                "type": "string",
                "description": "URL to navigate to (for navigate action)"
            },
            "selector": {
                "type": "string",
                "description": "CSS selector or text selector for element"
            },
            "text": {
                "type": "string",
                "description": "Text to type or fill"
            },
            "timeout": {
                "type": "integer",
                "description": "Action timeout in milliseconds"
            },
            "session_id": {
                "type": "string",
                "description": "Browser session ID (auto-created if not provided)"
            },
        },
        "required": ["action"]
    }
```

---

## 💻 Implementation

### Complete BrowserTool Implementation

**File:** `nanobot/agent/tools/browser.py`

```python
"""Browser automation tool using Playwright."""

import asyncio
import base64
import json
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field
from datetime import datetime
import uuid

from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from loguru import logger

from nanobot.agent.tools.base import Tool


@dataclass
class BrowserSession:
    """Represents a persistent browser session."""
    session_id: str
    context: BrowserContext
    page: Page
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
        headless: bool = True,
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
        self._browser: Browser | None = None
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

            if action == "navigate":
                return await self._navigate(session, url, wait_until, timeout_ms)

            elif action == "click":
                return await self._click(session, selector, text, timeout_ms)

            elif action == "type":
                return await self._type(session, selector, text, timeout_ms)

            elif action == "fill":
                return await self._fill(session, selector, text, timeout_ms)

            elif action == "screenshot":
                return await self._screenshot(session, full_page)

            elif action == "extract_text":
                return await self._extract_text(session, selector)

            elif action == "extract_html":
                return await self._extract_html(session, selector)

            elif action == "wait_for":
                return await self._wait_for(session, selector, timeout_ms)

            elif action == "scroll":
                return await self._scroll(session, selector)

            elif action == "go_back":
                await session.page.go_back(timeout=timeout_ms)
                session.current_url = session.page.url
                return f"Navigated back to: {session.page.url}"

            elif action == "go_forward":
                await session.page.go_forward(timeout=timeout_ms)
                session.current_url = session.page.url
                return f"Navigated forward to: {session.page.url}"

            elif action == "get_url":
                return f"Current URL: {session.page.url}\nTitle: {await session.page.title()}"

            elif action == "close_session":
                await self._close_session(session.session_id)
                return f"Closed browser session {session.session_id}"

            else:
                return f"Error: Unknown action '{action}'"

        except Exception as e:
            logger.error(f"Browser tool error: {e}")
            return f"Browser error: {str(e)}"

    async def _initialize(self) -> None:
        """Initialize Playwright and browser."""
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
                    return text[:5000]  # Limit output
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

    async def _get_page_summary(self, page: Page) -> str:
        """Get a summary of the current page for the LLM."""
        try:
            # Extract key information using accessibility tree
            # This gives a structural view of the page
            snapshot = await page.accessibility.snapshot()

            # Simplified summary
            summary_parts = []

            # Add interactive elements
            buttons = await page.query_selector_all("button, input[type='button'], input[type='submit']")
            if buttons:
                button_texts = []
                for btn in buttons[:10]:  # First 10 buttons
                    text = await btn.text_content() or await btn.get_attribute("value") or ""
                    if text:
                        button_texts.append(text.strip())
                if button_texts:
                    summary_parts.append(f"Buttons: {', '.join(button_texts)}")

            # Add input fields
            inputs = await page.query_selector_all("input[type='text'], input[type='email'], input[type='search'], textarea")
            if inputs:
                input_names = []
                for inp in inputs[:10]:
                    name = await inp.get_attribute("name") or await inp.get_attribute("placeholder") or ""
                    if name:
                        input_names.append(name.strip())
                if input_names:
                    summary_parts.append(f"Input fields: {', '.join(input_names)}")

            # Add links
            links = await page.query_selector_all("a[href]")
            if len(links) > 0:
                summary_parts.append(f"Links: {len(links)} links found")

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

        for session_id in to_remove:
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
```

### 2. Register the Tool

**File:** `nanobot/agent/loop.py` (modify `_register_default_tools`)

```python
def _register_default_tools(self) -> None:
    """Register the default set of tools."""
    # ... existing tools ...

    # Browser tool
    from nanobot.agent.tools.browser import BrowserTool
    self.tools.register(BrowserTool(
        headless=True,  # Can be config option
        allowed_domains=self.config.tools.browser.allowed_domains if self.config else [],
    ))
```

### 3. Add Configuration

**File:** `nanobot/config/schema.py`

```python
class BrowserToolConfig(BaseModel):
    """Browser tool configuration."""
    enabled: bool = True
    headless: bool = True
    timeout: int = 30000
    allowed_domains: list[str] = Field(default_factory=list)  # Empty = allow all
    max_sessions: int = 5
    session_timeout: int = 300

class ToolsConfig(BaseModel):
    """Tools configuration."""
    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    browser: BrowserToolConfig = Field(default_factory=BrowserToolConfig)  # ADD THIS
    restrict_to_workspace: bool = False
```

---

## 🎬 Usage Examples

### Example 1: Online Shopping

**User:** "Order a laptop from Amazon"

**Agent conversation:**

```
Tool call: browser(action="navigate", url="https://amazon.com")
→ "Navigated to Amazon.com. Buttons: Search, Sign In, Cart..."

Tool call: browser(action="fill", selector="input[name='field-keywords']", text="laptop")
→ "Filled 'laptop' into search box"

Tool call: browser(action="click", text="Go")
→ "Clicked search button. Current URL: amazon.com/s?k=laptop"

Tool call: browser(action="screenshot", full_page=false)
→ "Screenshot saved. Found 50 results. Top products: Dell XPS 13, MacBook Pro..."

Tool call: browser(action="click", text="Dell XPS 13")
→ "Clicked product link. Now on product page."

Tool call: browser(action="click", text="Add to Cart")
→ "Clicked Add to Cart button"

Tool call: browser(action="click", text="Proceed to Checkout")
→ "Navigated to checkout page"
```

### Example 2: Form Filling

**User:** "Fill out the contact form on example.com with my info"

```
Tool call: browser(action="navigate", url="https://example.com/contact")
→ "Loaded contact form page"

Tool call: browser(action="fill", selector="#name", text="John Doe")
→ "Filled name field"

Tool call: browser(action="fill", selector="#email", text="john@example.com")
→ "Filled email field"

Tool call: browser(action="fill", selector="#message", text="I'm interested in your product")
→ "Filled message field"

Tool call: browser(action="click", selector="button[type='submit']")
→ "Submitted form successfully"
```

### Example 3: Research Task

**User:** "Find the price of Tesla stock"

```
Tool call: browser(action="navigate", url="https://finance.yahoo.com")
→ "Loaded Yahoo Finance"

Tool call: browser(action="fill", selector="input[name='q']", text="TSLA")
→ "Typed TSLA in search"

Tool call: browser(action="click", text="Search")
→ "Searched for TSLA"

Tool call: browser(action="extract_text", selector="fin-streamer[data-symbol='TSLA']")
→ "$245.67"
```

---

## 🔐 Security Considerations

### 1. Domain Restrictions

```python
browser = BrowserTool(
    allowed_domains=["amazon.com", "ebay.com"]  # Whitelist
)
```

### 2. Timeout Limits

```python
browser = BrowserTool(
    timeout=30000,  # 30 seconds max per action
    session_timeout=300,  # 5 minutes max session age
)
```

### 3. Session Limits

```python
browser = BrowserTool(
    max_sessions=5,  # Prevent memory exhaustion
)
```

### 4. Headless Mode

```python
browser = BrowserTool(
    headless=True,  # No GUI, safer for production
)
```

### 5. Screenshot Storage

```python
# Screenshots saved to ~/.nanobot/screenshots/
# User can review what the agent saw
```

---

## 🚀 Deployment

### Docker Support

**Dockerfile additions:**

```dockerfile
# Install Playwright dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 && \
    rm -rf /var/lib/apt/lists/*

# Install Playwright
RUN pip install playwright && \
    playwright install chromium --with-deps
```

### Headless Server

```bash
# Run in headless mode (no display needed)
nanobot gateway
```

---

## 🎨 Vision Integration (Future Enhancement)

For truly agentic behavior, integrate with vision models:

```python
async def _screenshot_with_vision(self, session: BrowserSession) -> str:
    """Take screenshot and analyze with vision model."""
    # Take screenshot
    screenshot_bytes = await session.page.screenshot()

    # Encode as base64
    screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

    # Return in format that LLM can process
    # (Claude 3.5 Sonnet supports vision)
    return f"""Screenshot captured.

    To analyze this screenshot, I can see:
    - URL: {session.page.url}
    - Title: {await session.page.title()}

    [Base64 image data would be passed to vision model here]
    """
```

**With vision support:**
- Agent can "see" the page layout
- Can locate buttons by visual appearance
- Can read text from images
- Can verify actions visually

---

## 📊 Performance Considerations

### 1. Browser Initialization

**Cost:** ~1-2 seconds to launch browser

**Solution:** Keep browser running, reuse across sessions

```python
# Browser initialized once, contexts are lightweight
self._browser = await self._playwright.chromium.launch()  # Expensive
context = await self._browser.new_context()  # Cheap
```

### 2. Session Management

**Cost:** Memory per browser context (~50-100MB)

**Solution:** Limit max sessions, auto-cleanup old ones

### 3. Screenshot Storage

**Cost:** ~500KB per screenshot

**Solution:** Clean up old screenshots periodically

```python
# Add to BrowserTool
async def _cleanup_old_screenshots(self, max_age_days: int = 7):
    """Remove screenshots older than max_age_days."""
    import time
    now = time.time()

    for screenshot in self.screenshots_dir.glob("screenshot_*.png"):
        age_days = (now - screenshot.stat().st_mtime) / 86400
        if age_days > max_age_days:
            screenshot.unlink()
```

---

## 🧪 Testing

### Unit Tests

**File:** `tests/test_browser_tool.py`

```python
import pytest
from nanobot.agent.tools.browser import BrowserTool

@pytest.mark.asyncio
async def test_browser_navigate():
    tool = BrowserTool(headless=True)

    result = await tool.execute(
        action="navigate",
        url="https://example.com"
    )

    assert "example.com" in result.lower()
    await tool.cleanup()

@pytest.mark.asyncio
async def test_browser_screenshot():
    tool = BrowserTool(headless=True)

    # Navigate first
    await tool.execute(action="navigate", url="https://example.com")

    # Take screenshot
    result = await tool.execute(action="screenshot")

    assert "Screenshot saved" in result
    await tool.cleanup()

@pytest.mark.asyncio
async def test_browser_session_reuse():
    tool = BrowserTool(headless=True)

    # Create session
    result1 = await tool.execute(
        action="navigate",
        url="https://example.com",
        session_id="test-session"
    )

    # Reuse session
    result2 = await tool.execute(
        action="get_url",
        session_id="test-session"
    )

    assert "example.com" in result2.lower()
    await tool.cleanup()
```

### Integration Test

```python
@pytest.mark.asyncio
async def test_end_to_end_shopping():
    tool = BrowserTool(headless=True)

    # Navigate to site
    await tool.execute(action="navigate", url="https://demo-shop.com")

    # Search
    await tool.execute(action="fill", selector="#search", text="laptop")
    await tool.execute(action="click", selector="button.search")

    # Click first product
    await tool.execute(action="click", selector=".product:first-child")

    # Add to cart
    result = await tool.execute(action="click", text="Add to Cart")

    assert "cart" in result.lower()
    await tool.cleanup()
```

---

## 🎯 Summary

### Implementation Steps

1. ✅ **Install Playwright**
   ```bash
   pip install playwright
   playwright install chromium
   ```

2. ✅ **Create browser.py**
   - Copy the complete implementation above
   - Place in `nanobot/agent/tools/browser.py`

3. ✅ **Register the tool**
   - Modify `nanobot/agent/loop.py`
   - Add to `_register_default_tools()`

4. ✅ **Add configuration**
   - Update `nanobot/config/schema.py`
   - Add `BrowserToolConfig`

5. ✅ **Update dependencies**
   - Add `playwright>=1.40.0` to `pyproject.toml`

6. ✅ **Test it**
   ```bash
   nanobot agent -m "Navigate to example.com and take a screenshot"
   ```

### Time Estimate

- **Core implementation:** 4-6 hours
- **Testing:** 2-3 hours
- **Documentation:** 1-2 hours
- **Total:** ~8-11 hours

### Complexity

⭐⭐⭐☆☆ **Medium**

- Tool pattern is straightforward (just like shell.py)
- Playwright API is well-documented
- Main challenge is session management
- Vision integration is optional (future enhancement)

---

**Ready to implement?** The architecture is perfect for this - it's just another tool in the registry!

