# Nanobot Project Deep Dive - Learning Notes

**Date:** 2026-02-10
**Project:** nanobot - Ultra-Lightweight Personal AI Assistant
**Version:** 0.1.3.post6
**Repository:** HKUDS/nanobot

---

## 📋 Executive Summary

**Nanobot** is an ultra-lightweight personal AI assistant framework written primarily in Python (with a TypeScript bridge component for WhatsApp). It's designed to be a research-friendly, minimal alternative to larger agent frameworks, boasting only ~4,000 lines of core agent code (99% smaller than comparable projects like Clawdbot's 430k+ lines).

**Key Characteristics:**
- **Language:** Python 3.11+ (core), TypeScript (WhatsApp bridge)
- **Architecture:** Event-driven, message bus pattern
- **Process Model:** Single Python process with async/await (asyncio)
- **LLM Integration:** Provider-agnostic via LiteLLM
- **Deployment:** CLI-based, Docker support, installable via PyPI

---

## 🏗️ Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ENTRY POINTS                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐              │
│  │ CLI      │  │ Gateway  │  │ Docker       │              │
│  │ (Direct) │  │ (Server) │  │ Container    │              │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘              │
└───────┼─────────────┼───────────────┼─────────────────────┘
        │             │               │
        └─────────────┼───────────────┘
                      │
        ┌─────────────▼────────────────┐
        │      MessageBus (Queue)      │
        │   ┌──────────┬──────────┐    │
        │   │ Inbound  │ Outbound │    │
        │   │  Queue   │  Queue   │    │
        │   └────┬─────┴─────┬────┘    │
        └────────┼───────────┼─────────┘
                 │           │
    ┌────────────▼───────┐   │
    │   AgentLoop        │   │
    │   ┌──────────────┐ │   │
    │   │ Context      │ │   │
    │   │ Builder      │ │   │
    │   ├──────────────┤ │   │
    │   │ LLM Provider │ │   │
    │   ├──────────────┤ │   │
    │   │ Tool         │ │   │
    │   │ Registry     │ │   │
    │   ├──────────────┤ │   │
    │   │ Session      │ │   │
    │   │ Manager      │ │   │
    │   └──────────────┘ │   │
    └────────────────────┘   │
                             │
    ┌────────────────────────▼─────────────────┐
    │         Channel Manager                   │
    │  ┌───────┬────────┬─────────┬─────────┐  │
    │  │Telegram│Discord│WhatsApp │ Slack   │  │
    │  ├───────┼────────┼─────────┼─────────┤  │
    │  │Feishu │Mochat  │DingTalk │ Email   │  │
    │  ├───────┼────────┼─────────┼─────────┤  │
    │  │  QQ   │        │         │         │  │
    │  └───────┴────────┴─────────┴─────────┘  │
    └───────────────────────────────────────────┘
```

### Process Architecture

**Single Process Model:**
- The entire application runs in a **single Python process**
- Uses Python's `asyncio` for concurrency (cooperative multitasking)
- No multi-processing or threading (except for blocking I/O operations)
- Event loop handles all async operations

**Components Running in the Same Process:**
1. **AgentLoop** - Main agent processing logic
2. **MessageBus** - Async queue-based message routing
3. **ChannelManager** - Manages all chat channel connections
4. **CronService** - Scheduled task execution
5. **HeartbeatService** - Proactive periodic execution
6. **SessionManager** - Conversation history management

**External Processes:**
- **WhatsApp Bridge**: Separate Node.js process (TypeScript) communicating via WebSocket
- **LLM API Servers**: External HTTP APIs (OpenRouter, Anthropic, etc.)
- **vLLM**: Optional local LLM server (separate process if used)

---

## 📁 Project Structure Deep Dive

### Directory Layout

```
nanobot/
├── nanobot/                    # Main Python package
│   ├── __init__.py            # Package initialization
│   ├── __main__.py            # Entry point (python -m nanobot)
│   │
│   ├── agent/                 # 🧠 Core agent logic
│   │   ├── context.py         # Prompt building with system context
│   │   ├── loop.py            # Main agent execution loop
│   │   ├── memory.py          # Persistent memory management
│   │   ├── skills.py          # Skill loading and management
│   │   ├── subagent.py        # Background task execution
│   │   └── tools/             # Built-in tools
│   │       ├── base.py        # Tool interface
│   │       ├── cron.py        # Cron management tool
│   │       ├── filesystem.py  # File read/write/edit/list
│   │       ├── message.py     # Send messages to channels
│   │       ├── registry.py    # Tool registration system
│   │       ├── shell.py       # Shell command execution
│   │       ├── spawn.py       # Spawn subagents
│   │       └── web.py         # Web search and fetch
│   │
│   ├── bus/                   # 🚌 Message routing
│   │   ├── events.py          # Event data classes
│   │   └── queue.py           # Async message bus
│   │
│   ├── channels/              # 📱 Chat integrations
│   │   ├── base.py            # Base channel interface
│   │   ├── dingtalk.py        # DingTalk integration
│   │   ├── discord.py         # Discord bot
│   │   ├── email.py           # Email (IMAP/SMTP)
│   │   ├── feishu.py          # Feishu/Lark
│   │   ├── manager.py         # Channel lifecycle management
│   │   ├── mochat.py          # Mochat (Socket.IO)
│   │   ├── qq.py              # QQ bot
│   │   ├── slack.py           # Slack bot
│   │   ├── telegram.py        # Telegram bot
│   │   └── whatsapp.py        # WhatsApp bridge client
│   │
│   ├── cli/                   # 🖥️ Command-line interface
│   │   └── commands.py        # Typer-based CLI commands
│   │
│   ├── config/                # ⚙️ Configuration
│   │   ├── loader.py          # Config loading and saving
│   │   └── schema.py          # Pydantic config models
│   │
│   ├── cron/                  # ⏰ Scheduled tasks
│   │   ├── service.py         # Cron job execution
│   │   └── types.py           # Cron job data models
│   │
│   ├── heartbeat/             # 💓 Proactive execution
│   │   └── service.py         # Periodic wake-up service
│   │
│   ├── providers/             # 🤖 LLM providers
│   │   ├── base.py            # Provider interface
│   │   ├── litellm_provider.py # LiteLLM wrapper
│   │   ├── registry.py        # Provider registry
│   │   └── transcription.py   # Voice transcription
│   │
│   ├── session/               # 💬 Conversation management
│   │   └── manager.py         # Session storage and retrieval
│   │
│   ├── skills/                # 🎯 Bundled skills
│   │   ├── cron/              # Cron skill
│   │   ├── github/            # GitHub skill
│   │   ├── skill-creator/     # Skill creation skill
│   │   ├── summarize/         # Summarization skill
│   │   └── tmux/              # Tmux session skill
│   │
│   └── utils/                 # 🔧 Utilities
│       └── helpers.py         # Helper functions
│
├── bridge/                    # 🌉 WhatsApp bridge (TypeScript)
│   ├── src/
│   │   ├── index.ts          # Main entry point
│   │   ├── server.ts         # WebSocket server
│   │   ├── types.d.ts        # Type definitions
│   │   └── whatsapp.ts       # Baileys integration
│   ├── package.json
│   └── tsconfig.json
│
├── tests/                     # 🧪 Tests
│   ├── test_email_channel.py
│   └── test_tool_validation.py
│
├── pyproject.toml             # Python project metadata
├── Dockerfile                 # Docker image definition
├── README.md                  # Documentation
└── core_agent_lines.sh        # Line count verification script
```

---

## 🚀 Entry Points and Execution Flow

### 1. Entry Point: `__main__.py`

**File:** `nanobot/__main__.py`

```python
from nanobot.cli.commands import app

if __name__ == "__main__":
    app()  # Typer CLI application
```

**Purpose:** Allows running nanobot as a module: `python -m nanobot`

### 2. CLI Commands: `cli/commands.py`

**Primary Commands:**

1. **`nanobot onboard`**
   - Initializes configuration at `~/.nanobot/config.json`
   - Creates workspace directory at `~/.nanobot/workspace/`
   - Sets up template files (AGENTS.md, SOUL.md, USER.md, memory/)

2. **`nanobot agent`**
   - **Direct mode:** `nanobot agent -m "message"` (single message)
   - **Interactive mode:** `nanobot agent` (REPL with readline support)
   - Processes messages through `AgentLoop.process_direct()`
   - No message bus involved (direct execution)

3. **`nanobot gateway`**
   - Starts the full gateway server
   - Initializes all components:
     - MessageBus
     - AgentLoop
     - ChannelManager (starts enabled channels)
     - CronService
     - HeartbeatService
   - Runs indefinitely handling messages from channels

4. **`nanobot channels login`**
   - WhatsApp-specific command
   - Builds and runs the Node.js bridge
   - Displays QR code for device linking

5. **`nanobot cron`**
   - Subcommands: `add`, `list`, `remove`, `enable`, `run`
   - Manages scheduled tasks

6. **`nanobot status`**
   - Shows configuration status
   - Lists configured providers and API keys

### 3. Execution Flow: Gateway Mode

```
┌─────────────────────────────────────────────────────┐
│  nanobot gateway                                     │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│  Load Config (~/.nanobot/config.json)                │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│  Initialize Components:                              │
│  • MessageBus (inbound/outbound queues)             │
│  • LiteLLMProvider (configured LLM)                 │
│  • SessionManager (conversation history)            │
│  • CronService (scheduled tasks)                    │
│  • AgentLoop (main processing engine)               │
│  • HeartbeatService (periodic execution)            │
│  • ChannelManager (chat channels)                   │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│  Start Async Tasks (asyncio.gather):                │
│  1. AgentLoop.run() - processes inbound messages    │
│  2. ChannelManager.start_all() - connects channels  │
│  3. CronService.start() - runs scheduled jobs       │
│  4. HeartbeatService.start() - periodic execution   │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│  Event Loop Running                                  │
│  ┌────────────────────────────────────────────┐     │
│  │  Channels → Inbound Queue → AgentLoop     │     │
│  │  AgentLoop → Outbound Queue → Channels    │     │
│  └────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────┘
```

### 4. Message Processing Flow

**Inbound Message Path:**

```
User sends message
       ↓
Channel receives (e.g., TelegramChannel)
       ↓
Channel.on_message() called
       ↓
Create InboundMessage object
       ↓
bus.publish_inbound(msg)
       ↓
Message placed in inbound queue
       ↓
AgentLoop.run() consumes from queue
       ↓
AgentLoop._process_message(msg)
       ↓
┌────────────────────────────────────┐
│  1. Get/create session             │
│  2. Build context (history + msg)  │
│  3. Call LLM with tools            │
│  4. Execute tool calls (loop)      │
│  5. Get final response             │
│  6. Save to session                │
└────────┬───────────────────────────┘
         ↓
Create OutboundMessage
         ↓
bus.publish_outbound(response)
         ↓
Outbound queue
         ↓
Channel receives and sends to user
```

---

## 🔧 Core Components Deep Dive

### 1. MessageBus (`bus/queue.py`)

**Purpose:** Decouples channels from agent logic using async queues

**Key Features:**
- Two async queues: `inbound` and `outbound`
- Publisher/subscriber pattern for outbound messages
- Non-blocking, async-first design

**Code Structure:**
```python
class MessageBus:
    inbound: asyncio.Queue[InboundMessage]
    outbound: asyncio.Queue[OutboundMessage]
    _outbound_subscribers: dict[str, list[Callback]]

    # Publishing
    async def publish_inbound(msg)
    async def publish_outbound(msg)

    # Consuming
    async def consume_inbound() -> InboundMessage
    async def consume_outbound() -> OutboundMessage

    # Subscription
    def subscribe_outbound(channel, callback)
    async def dispatch_outbound()  # Background task
```

**Event Types:**
- `InboundMessage`: From channels to agent
  - Fields: channel, sender_id, chat_id, content, timestamp, media, metadata
  - Property: `session_key` = f"{channel}:{chat_id}"

- `OutboundMessage`: From agent to channels
  - Fields: channel, chat_id, content, reply_to, media, metadata

### 2. AgentLoop (`agent/loop.py`)

**Purpose:** Core processing engine for the agent

**Initialization:**
```python
AgentLoop(
    bus: MessageBus,
    provider: LLMProvider,
    workspace: Path,
    model: str | None,
    max_iterations: int = 20,
    brave_api_key: str | None,
    exec_config: ExecToolConfig,
    cron_service: CronService,
    restrict_to_workspace: bool,
    session_manager: SessionManager,
)
```

**Main Loop:**
1. Consumes messages from `bus.inbound`
2. Processes each message with `_process_message()`
3. Publishes responses to `bus.outbound`
4. Handles errors gracefully

**Processing Steps:**
1. Get/create session by `session_key`
2. Build context with `ContextBuilder`
3. Enter LLM loop (max `max_iterations`):
   - Call LLM with tools
   - If tool calls: execute tools, add results to messages, continue
   - If no tool calls: return final response
4. Save conversation to session
5. Return `OutboundMessage`

**Tool Execution:**
- Tools registered in `ToolRegistry`
- Executed via `tools.execute(name, arguments)`
- Results added to message history

### 3. ContextBuilder (`agent/context.py`)

**Purpose:** Builds LLM context with system prompts, history, and current message

**Key Functions:**
- `build_messages()`: Constructs the full message array
- Loads system context from workspace files:
  - `AGENTS.md` - Agent instructions
  - `SOUL.md` - Personality/values
  - `USER.md` - User information
  - `memory/MEMORY.md` - Long-term memory
- Formats conversation history
- Adds current message
- Supports media attachments

### 4. SessionManager (`session/manager.py`)

**Purpose:** Manages conversation sessions with persistent storage

**Session Key Format:** `{channel}:{chat_id}`

**Features:**
- In-memory cache of active sessions
- File-based persistence in `~/.nanobot/data/sessions/`
- Conversation history in LLM-compatible format
- Auto-saving to disk

### 5. ToolRegistry (`agent/tools/registry.py`)

**Purpose:** Manages available tools for the agent

**Built-in Tools:**
1. **Filesystem:**
   - `read_file` - Read file contents
   - `write_file` - Write to file
   - `edit_file` - Edit file (find/replace)
   - `list_dir` - List directory contents

2. **Shell:**
   - `exec` - Execute shell commands

3. **Web:**
   - `web_search` - Search the web (Brave API)
   - `web_fetch` - Fetch and parse web pages

4. **Communication:**
   - `message` - Send messages to channels

5. **Task Management:**
   - `spawn` - Create background subagents
   - `cron` - Manage scheduled tasks

**Tool Definition Format:** OpenAI function calling format

### 6. Provider System (`providers/`)

**Purpose:** LLM provider abstraction layer

**Architecture:**
- `base.py`: Abstract `LLMProvider` interface
- `litellm_provider.py`: Implementation using LiteLLM
- `registry.py`: Provider registry with auto-configuration

**Supported Providers (via LiteLLM):**
- OpenRouter (recommended)
- Anthropic (Claude direct)
- OpenAI (GPT direct)
- DeepSeek, Groq, Gemini, MiniMax
- AIHubMix, Dashscope (Qwen), Moonshot, Zhipu
- vLLM (local)

**Provider Registry Pattern:**
```python
ProviderSpec(
    name="provider_name",
    keywords=("keyword1", "keyword2"),
    env_key="ENV_VAR_NAME",
    display_name="Display Name",
    litellm_prefix="prefix",
    skip_prefixes=("prefix/",),
)
```

**Auto-configuration:**
- Detects provider from API key or model name
- Sets environment variables for LiteLLM
- Handles model name prefixing

### 7. Channel System (`channels/`)

**Base Architecture:**
- `base.py`: Abstract `Channel` interface
- Each channel extends `Channel` class
- Channels run as async tasks

**Channel Interface:**
```python
class Channel:
    async def start()  # Connect and listen
    async def stop()   # Disconnect
    async def send_message(msg: OutboundMessage)
```

**Channel Types:**

1. **Telegram** (`telegram.py`)
   - Library: `python-telegram-bot`
   - Mode: Long polling
   - Features: Text, voice (transcription), media

2. **Discord** (`discord.py`)
   - Connection: WebSocket Gateway
   - Intents: MESSAGE_CONTENT required
   - Features: DMs and server messages

3. **WhatsApp** (`whatsapp.py`)
   - Architecture: Bridge pattern
   - Bridge: Node.js process (TypeScript)
   - Library: Baileys (WhatsApp Web API)
   - Communication: WebSocket between Python and Node.js
   - QR code login required

4. **Slack** (`slack.py`)
   - Mode: Socket Mode (no webhook needed)
   - SDK: `slack-sdk`
   - Features: DMs, channels, mentions

5. **Feishu/Lark** (`feishu.py`)
   - Connection: WebSocket long connection
   - SDK: `lark-oapi`
   - No public IP required

6. **Mochat** (`mochat.py`)
   - Connection: Socket.IO with msgpack
   - Features: Real-time messaging

7. **DingTalk** (`dingtalk.py`)
   - Mode: Stream Mode
   - SDK: `dingtalk-stream`

8. **Email** (`email.py`)
   - Inbound: IMAP polling
   - Outbound: SMTP
   - Features: Auto-reply, consent-based

9. **QQ** (`qq.py`)
   - SDK: `qq-botpy`
   - Connection: WebSocket
   - Mode: Private messages only (sandbox)

**ChannelManager:**
- Manages lifecycle of all channels
- Starts enabled channels from config
- Routes outbound messages to correct channel

### 8. Cron System (`cron/`)

**Purpose:** Scheduled task execution

**Features:**
- Three schedule types:
  - `every`: Interval in milliseconds
  - `cron`: Cron expression (parsed by `croniter`)
  - `at`: One-time execution at specific time

**Job Structure:**
```python
class CronJob:
    id: str
    name: str
    schedule: CronSchedule
    payload: CronPayload  # message, channel, recipient
    enabled: bool
    state: CronState  # next_run_at_ms, last_run_at_ms
```

**Execution:**
- Jobs executed through AgentLoop
- Can deliver responses to channels
- Persistent storage in `~/.nanobot/data/cron/jobs.json`

### 9. Subagent System (`agent/subagent.py`)

**Purpose:** Background task execution

**Architecture:**
- Managed by `SubagentManager`
- Tool: `spawn` - creates subagents
- Communication: Through message bus
- Announcement: Subagents announce completion via system messages

**Use Cases:**
- Long-running tasks
- Parallel processing
- Background monitoring

---

## 🔐 Security Features

### 1. Workspace Restriction
- **Config:** `tools.restrict_to_workspace: true`
- **Effect:** All file operations limited to workspace directory
- **Tools affected:** read_file, write_file, edit_file, list_dir, exec

### 2. Channel Allowlists
- **Config:** `channels.*.allow_from: []`
- **Behavior:**
  - Empty list = allow all users
  - Non-empty = only listed users can interact
- **Applied to:** All channels

### 3. Shell Command Safety
- **Timeout:** Configurable execution timeout
- **Working directory:** Defaults to workspace
- **Restrictions:** Can be limited to workspace

---

## 📦 Dependencies

### Python Dependencies (pyproject.toml)

**Core:**
- `typer` - CLI framework
- `litellm` - LLM provider abstraction
- `pydantic` - Configuration validation
- `loguru` - Logging

**Async/Network:**
- `httpx` - HTTP client
- `websockets` - WebSocket support
- `websocket-client` - WebSocket client
- `python-socketio` - Socket.IO client

**Channel SDKs:**
- `python-telegram-bot` - Telegram
- `lark-oapi` - Feishu/Lark
- `dingtalk-stream` - DingTalk
- `slack-sdk` - Slack
- `qq-botpy` - QQ

**Utilities:**
- `rich` - Terminal formatting
- `croniter` - Cron expression parsing
- `readability-lxml` - Web page parsing

### Node.js Dependencies (bridge/package.json)

**WhatsApp Bridge:**
- `@whiskeysockets/baileys` - WhatsApp Web API
- `ws` - WebSocket server
- `qrcode-terminal` - QR code display
- `pino` - Logging

---

## 🐳 Docker Setup

**Dockerfile Breakdown:**

1. **Base Image:** `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`
   - Uses `uv` for fast package installation

2. **Node.js Installation:**
   - Installs Node.js 20 from NodeSource
   - Required for WhatsApp bridge

3. **Python Dependencies:**
   - Two-stage install for better caching
   - First: Install package metadata
   - Second: Copy source and install

4. **Bridge Build:**
   - `npm install && npm run build`
   - Compiles TypeScript to JavaScript

5. **Configuration:**
   - Creates `~/.nanobot` directory
   - Mounts `~/.nanobot` for persistence

6. **Port:** Exposes 18790 (gateway default)

**Usage:**
```bash
# Build
docker build -t nanobot .

# Initialize
docker run -v ~/.nanobot:/root/.nanobot --rm nanobot onboard

# Run gateway
docker run -v ~/.nanobot:/root/.nanobot -p 18790:18790 nanobot gateway
```

---

## 📝 Configuration System

### Config File Location
- **Path:** `~/.nanobot/config.json`
- **Format:** JSON
- **Schema:** Validated by Pydantic models

### Config Structure
```json
{
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-v1-xxx",
      "apiBase": null,
      "extraHeaders": null
    }
  },
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5",
      "maxToolIterations": 20
    }
  },
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allowFrom": []
    },
    "whatsapp": {
      "enabled": false,
      "bridgeUrl": "ws://localhost:3001",
      "allowFrom": []
    }
  },
  "tools": {
    "web": {
      "search": {
        "apiKey": "BRAVE_API_KEY"
      }
    },
    "exec": {
      "timeout": 30000
    },
    "restrictToWorkspace": false
  },
  "workspacePath": "/Users/user/.nanobot/workspace"
}
```

### Workspace Structure
```
~/.nanobot/
├── config.json              # Main configuration
├── workspace/               # Agent workspace
│   ├── AGENTS.md           # Agent instructions
│   ├── SOUL.md             # Personality
│   ├── USER.md             # User info
│   ├── memory/             # Long-term memory
│   │   └── MEMORY.md
│   └── skills/             # Custom skills
├── data/                    # Runtime data
│   ├── sessions/           # Conversation history
│   │   └── {channel}_{chat_id}.json
│   └── cron/               # Scheduled jobs
│       └── jobs.json
├── bridge/                  # WhatsApp bridge (if built)
└── history/                 # CLI history
    └── cli_history
```

---

## 🧩 Skills System

**Location:** `nanobot/skills/`

**Bundled Skills:**
1. **cron** - Cron job management
2. **github** - GitHub integration
3. **skill-creator** - Create new skills
4. **summarize** - Text summarization
5. **tmux** - Tmux session management

**Skill Structure:**
- Each skill has a `SKILL.md` file
- Skills are loaded by `agent/skills.py`
- Can include shell scripts and additional files

**Custom Skills:**
- User skills go in `~/.nanobot/workspace/skills/`
- Auto-loaded at agent startup

---

## 🔄 Process Lifecycle

### Gateway Startup Sequence

1. **Load Configuration**
   ```python
   config = load_config()  # From ~/.nanobot/config.json
   ```

2. **Initialize MessageBus**
   ```python
   bus = MessageBus()
   ```

3. **Initialize Provider**
   ```python
   provider = LiteLLMProvider(
       api_key=config.get_provider().api_key,
       api_base=config.get_api_base(),
       default_model=config.agents.defaults.model,
   )
   ```

4. **Initialize Services**
   ```python
   session_manager = SessionManager(config.workspace_path)
   cron = CronService(cron_store_path)
   ```

5. **Initialize AgentLoop**
   ```python
   agent = AgentLoop(
       bus=bus,
       provider=provider,
       workspace=config.workspace_path,
       model=config.agents.defaults.model,
       max_iterations=config.agents.defaults.max_tool_iterations,
       brave_api_key=config.tools.web.search.api_key,
       exec_config=config.tools.exec,
       cron_service=cron,
       restrict_to_workspace=config.tools.restrict_to_workspace,
       session_manager=session_manager,
   )
   ```

6. **Initialize Heartbeat**
   ```python
   heartbeat = HeartbeatService(
       workspace=config.workspace_path,
       on_heartbeat=agent.process_direct,
       interval_s=30 * 60,  # 30 minutes
   )
   ```

7. **Initialize Channels**
   ```python
   channels = ChannelManager(config, bus, session_manager)
   ```

8. **Start Everything**
   ```python
   async def run():
       await cron.start()
       await heartbeat.start()
       await asyncio.gather(
           agent.run(),
           channels.start_all(),
       )

   asyncio.run(run())
   ```

### Shutdown Sequence

```python
# On KeyboardInterrupt or signal
heartbeat.stop()
cron.stop()
agent.stop()
await channels.stop_all()
```

---

## 🔍 Key Insights

### 1. Single Process, Async-First
- **No multiprocessing:** Entire application runs in one process
- **Async I/O:** All network operations are non-blocking
- **Event loop:** Python asyncio handles concurrency
- **Benefits:** Simpler architecture, easier debugging, lower overhead

### 2. Message Bus Pattern
- **Decoupling:** Channels don't directly call agent
- **Queue-based:** Async queues for message passing
- **Scalability:** Easy to add new channels without modifying agent
- **Reliability:** Messages can be queued if agent is busy

### 3. Provider Abstraction
- **LiteLLM:** Single interface to 100+ LLM providers
- **Registry pattern:** Easy to add new providers
- **Auto-configuration:** Detects provider from API keys/model names
- **Flexibility:** Switch providers without code changes

### 4. Tool-Based Architecture
- **OpenAI function calling:** Standard tool format
- **Registry system:** Dynamic tool registration
- **Composability:** Tools can call other tools
- **Extensibility:** Easy to add new tools

### 5. Session Management
- **Per-channel sessions:** Separate history for each chat
- **Persistence:** Conversations survive restarts
- **LLM-compatible format:** Direct integration with provider
- **Efficiency:** In-memory cache with disk backing

### 6. Minimal Dependencies
- **Core dependencies:** ~15 packages
- **Selective channel deps:** Only install what you use
- **No heavy frameworks:** Direct use of SDKs
- **Fast installation:** Minimal package download

### 7. Research-Friendly Design
- **Readable code:** Clear structure, good naming
- **Minimal abstraction:** No over-engineering
- **Well-commented:** Docstrings and inline comments
- **Easy to modify:** Small, focused files

---

## 🎯 Common Operations

### Adding a New Channel

1. **Create channel file:** `nanobot/channels/mychannel.py`
2. **Extend `Channel` base class**
3. **Implement required methods:**
   - `async def start()`
   - `async def stop()`
   - `async def send_message(OutboundMessage)`
4. **Add config schema:** In `config/schema.py`
5. **Register in `ChannelManager`:** In `channels/manager.py`

### Adding a New Tool

1. **Create tool file:** `nanobot/agent/tools/mytool.py`
2. **Extend `Tool` base class**
3. **Implement:**
   - `get_definition()` - OpenAI function format
   - `async def execute(**kwargs)` - Tool logic
4. **Register in `AgentLoop._register_default_tools()`**

### Adding a New Provider

1. **Add to `providers/registry.py`:**
   ```python
   ProviderSpec(
       name="myprovider",
       keywords=("myprovider", "mymodel"),
       env_key="MYPROVIDER_API_KEY",
       display_name="My Provider",
       litellm_prefix="myprovider",
   )
   ```

2. **Add to `config/schema.py`:**
   ```python
   class ProvidersConfig(BaseModel):
       ...
       myprovider: ProviderConfig = ProviderConfig()
   ```

3. **Done!** Auto-configuration handles the rest

---

## 📊 Performance Characteristics

### Resource Usage
- **Memory:** ~50-100MB idle, ~200-500MB under load
- **CPU:** Minimal when idle, spikes during LLM calls
- **Network:** Depends on LLM provider and channel activity
- **Disk:** Sessions and config files (<10MB typically)

### Scalability Limits
- **Single process:** Limited by Python GIL for CPU-bound tasks
- **Async I/O:** Can handle many concurrent network connections
- **Session limit:** Thousands of sessions (memory-limited)
- **Tool execution:** Serial within a conversation turn

### Bottlenecks
- **LLM API calls:** Primary latency source
- **Tool execution:** Synchronous within iteration
- **Message processing:** Serial per session (parallel across sessions)

---

## 🐛 Debugging Tips

### Enable Logging
```bash
# CLI mode
nanobot agent --logs -m "test"

# Gateway mode
nanobot gateway --verbose
```

### Log Locations
- **Loguru:** Outputs to stderr
- **Session data:** `~/.nanobot/data/sessions/`
- **Cron jobs:** `~/.nanobot/data/cron/jobs.json`

### Common Issues
1. **No API key:** Check `~/.nanobot/config.json`
2. **Channel not responding:** Verify `enabled: true` and credentials
3. **Tool execution timeout:** Increase `tools.exec.timeout`
4. **WhatsApp bridge fails:** Check Node.js version ≥20

---

## 🚀 Future Architecture Considerations

### Potential Enhancements
1. **Multi-processing:** For CPU-intensive tool execution
2. **Redis-backed queues:** For distributed deployment
3. **Database sessions:** PostgreSQL/SQLite for better querying
4. **Streaming responses:** For real-time output
5. **Plugin system:** Dynamic tool/channel loading
6. **Metrics/Observability:** Prometheus, OpenTelemetry

### Current Limitations
1. **Single process:** No horizontal scaling
2. **No authentication:** Channels use allowlists only
3. **Limited caching:** No LLM response cache
4. **No rate limiting:** Provider-dependent
5. **Sequential tool execution:** No parallel tool calls

---

## 📚 Key Files to Study

### Essential Reading Order

1. **Start here:**
   - `README.md` - Overview and features
   - `nanobot/__main__.py` - Entry point
   - `nanobot/cli/commands.py` - CLI commands

2. **Core architecture:**
   - `nanobot/bus/events.py` - Event types
   - `nanobot/bus/queue.py` - Message bus
   - `nanobot/agent/loop.py` - Main agent loop

3. **Context and tools:**
   - `nanobot/agent/context.py` - Context building
   - `nanobot/agent/tools/registry.py` - Tool system
   - `nanobot/agent/tools/base.py` - Tool interface

4. **Configuration:**
   - `nanobot/config/schema.py` - Config models
   - `nanobot/config/loader.py` - Config loading

5. **Channels (pick one):**
   - `nanobot/channels/base.py` - Base interface
   - `nanobot/channels/telegram.py` - Example channel

6. **Providers:**
   - `nanobot/providers/registry.py` - Provider system
   - `nanobot/providers/litellm_provider.py` - LLM integration

---

## 🎓 Learning Outcomes

### What We Learned

1. **Architecture Pattern:**
   - Message bus for decoupling
   - Single process, async-first design
   - Tool-based agent architecture

2. **Process Model:**
   - Entire system runs in one Python process
   - Uses asyncio for concurrency
   - WhatsApp bridge is the only external process

3. **Entry Points:**
   - CLI for direct interaction
   - Gateway for channel-based operation
   - Docker for containerized deployment

4. **Component Interactions:**
   - Channels → Bus → Agent → Tools
   - Sessions for persistence
   - Cron for scheduling

5. **Extension Points:**
   - Adding channels via `Channel` base class
   - Adding tools via `Tool` base class
   - Adding providers via registry

6. **Configuration System:**
   - JSON-based config with Pydantic validation
   - Workspace for agent context
   - Provider auto-configuration

---

## 📖 References

- **Repository:** https://github.com/HKUDS/nanobot
- **PyPI:** https://pypi.org/project/nanobot-ai/
- **Documentation:** README.md in repo
- **Discord:** https://discord.gg/MnCvHqpUGB

---

**Last Updated:** 2026-02-10
**Nanobot Version:** 0.1.3.post6
**Lines of Core Code:** ~3,510 (verified by core_agent_lines.sh)
