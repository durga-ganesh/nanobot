# Browser Tool Setup Instructions

This guide shows how to enable the browser automation tool in nanobot.

## Installation

### 1. Install Playwright

```bash
# Install the optional browser dependencies
pip install "nanobot-ai[browser]"

# Or if you already have nanobot installed
pip install playwright>=1.40.0

# Download Chromium browser (required)
playwright install chromium
```

### 2. Verify Installation

```bash
# Test that playwright is installed
python -c "from playwright.async_api import async_playwright; print('Playwright installed!')"
```

## Configuration

The browser tool is enabled by default. You can customize it in `~/.nanobot/config.json`:

```json
{
  "tools": {
    "browser": {
      "enabled": true,
      "headless": true,
      "timeout": 30000,
      "allowed_domains": [],
      "max_sessions": 5,
      "session_timeout": 300
    }
  }
}
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `enabled` | `true` | Enable/disable browser tool |
| `headless` | `true` | Run browser without GUI (recommended for production) |
| `timeout` | `30000` | Default timeout for browser actions (milliseconds) |
| `allowed_domains` | `[]` | Whitelist of allowed domains (empty = allow all) |
| `max_sessions` | `5` | Maximum number of concurrent browser sessions |
| `session_timeout` | `300` | Auto-close sessions after N seconds of inactivity |

### Security: Domain Restrictions

To restrict browser access to specific domains:

```json
{
  "tools": {
    "browser": {
      "allowed_domains": ["amazon.com", "ebay.com", "example.com"]
    }
  }
}
```

## Usage Examples

### Example 1: Navigate and Take Screenshot

```bash
nanobot agent -m "Navigate to example.com and take a screenshot"
```

**Expected behavior:**
1. Agent uses `browser(action="navigate", url="https://example.com")`
2. Agent uses `browser(action="screenshot")`
3. Screenshot saved to `~/.nanobot/screenshots/`

### Example 2: Fill a Form

```bash
nanobot agent -m "Go to example.com/contact and fill in the name field with 'John Doe'"
```

**Expected behavior:**
1. Agent navigates to the URL
2. Agent fills the form field using CSS selector
3. Returns confirmation

### Example 3: Search and Extract

```bash
nanobot agent -m "Search for 'laptop' on amazon.com and tell me the first 3 results"
```

**Expected behavior:**
1. Agent navigates to amazon.com
2. Agent fills search box with "laptop"
3. Agent clicks search button
4. Agent extracts product titles

### Example 4: Online Shopping (Complex Task)

```bash
nanobot agent -m "Add a Dell laptop to cart on Amazon"
```

**Expected behavior:**
1. Navigate to amazon.com
2. Search for "Dell laptop"
3. Click first result
4. Click "Add to Cart"
5. Confirm item added

## Available Browser Actions

The browser tool supports these actions:

| Action | Description | Parameters |
|--------|-------------|------------|
| `navigate` | Go to a URL | `url`, `wait_until`, `timeout` |
| `click` | Click an element | `selector` or `text` |
| `type` | Type text into element | `selector`, `text` |
| `fill` | Fill input field (replaces content) | `selector`, `text` |
| `screenshot` | Capture page screenshot | `full_page` |
| `extract_text` | Get text from element(s) | `selector` (optional) |
| `extract_html` | Get HTML from element | `selector` (optional) |
| `wait_for` | Wait for element to appear | `selector`, `timeout` |
| `scroll` | Scroll page or to element | `selector` (optional) |
| `go_back` | Browser back button | - |
| `go_forward` | Browser forward button | - |
| `get_url` | Get current URL and title | - |
| `close_session` | Close browser session | `session_id` |

## Session Management

Browser sessions persist across tool calls, allowing multi-step workflows:

```python
# Step 1: Create session and navigate
browser(action="navigate", url="https://example.com", session_id="my-session")

# Step 2: Interact with page (reuses same session)
browser(action="click", text="Login", session_id="my-session")

# Step 3: Fill form (still same session)
browser(action="fill", selector="#email", text="user@example.com", session_id="my-session")
```

Sessions auto-expire after 5 minutes of inactivity (configurable).

## Selectors

The browser tool supports CSS selectors and text selectors:

### CSS Selectors
```python
selector="button.submit"          # Class selector
selector="#login-button"          # ID selector
selector="input[name='email']"    # Attribute selector
selector="div > p:first-child"    # Child selector
```

### Text Selectors
```python
text="Add to Cart"                # Finds element with this text
selector="text=Login"             # Alternative syntax
```

## Screenshots

Screenshots are saved to `~/.nanobot/screenshots/` with timestamped filenames:

```
~/.nanobot/screenshots/
  screenshot_abc123_20260210_143022.png
  screenshot_abc123_20260210_143045.png
```

Each screenshot includes:
- URL of the page
- Page title
- Summary of interactive elements (buttons, inputs)

## Troubleshooting

### "Playwright is not installed"

```bash
pip install playwright
playwright install chromium
```

### "Browser tool not available"

Check the agent logs:
```bash
nanobot agent --logs -m "test"
```

If you see "Browser tool not available (playwright not installed)", run the installation steps above.

### "Navigation failed: net::ERR_NAME_NOT_RESOLVED"

The domain might be misspelled or unreachable. Try with a known working URL like `https://example.com`.

### Sessions not persisting

Make sure you're using the same `session_id` across calls:

```python
# Wrong - creates new session each time
browser(action="navigate", url="...")
browser(action="click", text="...")  # Different session!

# Correct - reuses session
browser(action="navigate", url="...", session_id="my-session")
browser(action="click", text="...", session_id="my-session")
```

### Timeout errors

Increase the timeout for slow-loading pages:

```python
browser(action="navigate", url="...", timeout=60000)  # 60 seconds
```

Or change the default in config:

```json
{
  "tools": {
    "browser": {
      "timeout": 60000
    }
  }
}
```

## Docker Deployment

If running nanobot in Docker, you'll need to install additional dependencies.

Add to your Dockerfile:

```dockerfile
# Install Playwright system dependencies
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

# Install Playwright and browsers
RUN pip install playwright && \
    playwright install chromium --with-deps
```

## Performance Notes

- **Browser startup:** ~1-2 seconds (one-time cost)
- **Session creation:** ~100ms (lightweight)
- **Screenshot:** ~200-500ms
- **Navigation:** Depends on page load time
- **Memory:** ~50-100MB per browser session

## Security Best Practices

1. **Use headless mode in production**
   ```json
   {"headless": true}
   ```

2. **Restrict domains** for sensitive deployments
   ```json
   {"allowed_domains": ["trusted-site.com"]}
   ```

3. **Set reasonable timeouts** to prevent hanging
   ```json
   {"timeout": 30000}
   ```

4. **Limit max sessions** to prevent resource exhaustion
   ```json
   {"max_sessions": 5}
   ```

5. **Review screenshots** regularly
   - Screenshots saved to `~/.nanobot/screenshots/`
   - Audit what the agent is viewing

## Advanced Usage

### Custom User Agent

The browser uses a standard user agent:
```
Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36
```

This can be customized by modifying the `BrowserTool` class in `nanobot/agent/tools/browser.py`.

### File Downloads

File downloads are not yet supported but can be added by handling download events in Playwright.

### Multiple Tabs

Currently limited to one tab per session. Multiple tab support can be added in future versions.

## Testing

Run the browser tool tests:

```bash
# Install dev dependencies
pip install "nanobot-ai[dev,browser]"

# Run browser tool tests
pytest tests/test_browser_tool.py -v
```

## Next Steps

- **Vision Integration:** Use Claude's vision capabilities to analyze screenshots
- **Stealth Mode:** Add anti-detection features for scraping
- **Cookie Persistence:** Save login sessions across restarts
- **File Downloads:** Handle PDF and file downloads
- **Multi-tab Support:** Open multiple tabs in one session

## Support

If you encounter issues:

1. Check the [troubleshooting section](#troubleshooting)
2. Review logs: `nanobot agent --logs -m "test browser"`
3. Open an issue: https://github.com/HKUDS/nanobot/issues

---

**Ready to browse!** The browser tool is now configured and ready to use.
