# Browser Tool Usage Guide

## How Browser Sessions Work

The browser tool maintains **persistent sessions** across multiple calls. To keep working in the same browser window, you must **extract and reuse the session_id** from previous results.

## Session ID Format

Every browser action returns a result starting with:
```
[Session: abc12345]
```

Extract this ID and pass it to subsequent calls to maintain state.

## Example: Multi-Step Web Automation

```python
import re

def extract_session_id(result: str) -> str | None:
    """Extract session_id from browser tool result."""
    match = re.match(r'\[Session: ([^\]]+)\]', result)
    return match.group(1) if match else None

# Step 1: Navigate (creates new session)
result = await browser.execute(
    action="navigate",
    url="https://example.com"
)
session_id = extract_session_id(result)
# Output: [Session: abc12345]
#         Navigated to: https://example.com/
#         Title: Example Domain

# Step 2: Click a button (reuse session)
result = await browser.execute(
    action="click",
    selector="button.login",
    session_id=session_id  # ← IMPORTANT: Reuse the session!
)
# Output: [Session: abc12345]
#         Clicked element: button.login

# Step 3: Fill a form (still in same session)
result = await browser.execute(
    action="fill",
    selector="#username",
    text="myuser",
    session_id=session_id  # ← Same session
)

# Step 4: Take screenshot
result = await browser.execute(
    action="screenshot",
    full_page=True,
    session_id=session_id
)

# Step 5: Close when done
result = await browser.execute(
    action="close_session",
    session_id=session_id
)
```

## Available Actions

### Navigation
- `navigate` - Go to a URL
- `go_back` - Browser back button
- `go_forward` - Browser forward button
- `get_url` - Get current URL and title

### Interaction
- `click` - Click an element by selector or text
- `type` - Type text into an element
- `fill` - Fill a form field (clears first)
- `scroll` - Scroll to element or bottom

### Extraction
- `extract_text` - Get text content from selector
- `extract_html` - Get HTML from selector
- `screenshot` - Take screenshot and save to disk

### Waiting
- `wait_for` - Wait for element to appear

### Session Management
- `close_session` - Close the browser session

## CSS Selectors

Use standard CSS selectors:
- `#id` - By ID
- `.class` - By class
- `button.submit` - Element with class
- `input[name="email"]` - By attribute
- `text=Click me` - By visible text

## Common Patterns

### Search Google
```python
# Navigate
result = await browser.execute(action="navigate", url="https://google.com")
sid = extract_session_id(result)

# Fill search box
await browser.execute(action="fill", selector="input[name='q']", text="python", session_id=sid)

# Click search button
await browser.execute(action="click", selector="input[value='Google Search']", session_id=sid)

# Take screenshot of results
await browser.execute(action="screenshot", full_page=True, session_id=sid)
```

### Fill a Form
```python
result = await browser.execute(action="navigate", url="https://example.com/signup")
sid = extract_session_id(result)

await browser.execute(action="fill", selector="#email", text="user@example.com", session_id=sid)
await browser.execute(action="fill", selector="#password", text="secure123", session_id=sid)
await browser.execute(action="click", selector="button[type='submit']", session_id=sid)
```

### Scrape Content
```python
result = await browser.execute(action="navigate", url="https://news.ycombinator.com")
sid = extract_session_id(result)

# Extract all post titles
titles = await browser.execute(action="extract_text", selector=".titleline a", session_id=sid)
print(titles)
```

## Important Notes

⚠️ **Always reuse the session_id** to maintain browser state
⚠️ **Sessions auto-expire** after 5 minutes of inactivity
⚠️ **Max 5 concurrent sessions** (oldest gets closed)
⚠️ **Screenshots saved to** `~/.nanobot/screenshots/`

## Troubleshooting

**Problem**: Page content is blank / not found
- **Cause**: Not reusing session_id, creating new blank sessions
- **Fix**: Extract session_id from first result and pass to all subsequent calls

**Problem**: Element not found
- **Cause**: Wrong selector or page hasn't loaded
- **Fix**: Use `wait_for` action first, or check with `extract_text` without selector

**Problem**: Timeout errors
- **Cause**: Page loading slowly or selector never appears
- **Fix**: Increase `timeout` parameter (default 30000ms)
