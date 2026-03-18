# iGenius Memory — Persistent AI Memory for Any Agent

[![PyPI](https://img.shields.io/pypi/v/igenius-mcp?color=blue)](https://pypi.org/project/igenius-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/igenius-mcp)](https://pypi.org/project/igenius-mcp/)
[![VS Code Marketplace](https://img.shields.io/visual-studio-marketplace/v/igenius-memory.igenius-memory?label=VS%20Code&color=blue)](https://marketplace.visualstudio.com/items?itemName=igenius-memory.igenius-memory)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![GitHub](https://img.shields.io/github/stars/vehoelite/igenius-mcp?style=social)](https://github.com/vehoelite/igenius-mcp)

A structured, AI-powered memory backend that gives any MCP-compatible agent
persistent memory via the [iGenius Memory](https://igenius-memory.com) service.
All AI processing happens server-side — you just need an API key.

<p align="center">
  <img src="https://raw.githubusercontent.com/vehoelite/igenius-vscode/main/igenius-motion_sm.gif" alt="iGenius Memory" width="600">
</p>

---

## 3 Ways to Use iGenius

| Client | Install | Best For |
|--------|---------|----------|
| **🧩 VS Code Extension** | [Marketplace](https://marketplace.visualstudio.com/items?itemName=igenius-memory.igenius-memory) | Full sidebar UI, memory browser, AI provider settings |
| **⚡ MCP Server** | `pip install igenius-mcp` | Any MCP client — VS Code, Claude Desktop, Cursor, Windsurf |
| **🖥️ Desktop App** | [Windows Installer](https://github.com/vehoelite/igenius-desktop/releases/latest) | Standalone system-tray app, works with any editor |

> **Get a free API key** at [igenius-memory.online](https://igenius-memory.online#apikey) — all three clients use the same key.

---

### 1. VS Code Extension (Marketplace)

Install directly from the VS Code Marketplace — no pip, no config files:

```
ext install igenius-memory.igenius-memory
```

Or search **"iGenius Memory"** in the Extensions panel. Includes sidebar UI,
memory browser, status bar indicator, AI provider settings, and auto-warms
briefings on a configurable interval.

### 2. MCP Server (pip)

For any MCP-compatible client (VS Code Copilot, Claude Desktop, Cursor, Windsurf, etc.):

```bash
pip install igenius-mcp
```

Then add to your MCP config:

**VS Code** — `~/.vscode/mcp.json`:
```json
{
  "servers": {
    "igenius-memory": {
      "command": "igenius-mcp",
      "env": { "IGENIUS_API_KEY": "ig_your_key_here" },
      "type": "stdio"
    }
  }
}
```

**Claude Desktop / Cursor / Windsurf** — add to your MCP config file:
```json
{
  "mcpServers": {
    "igenius-memory": {
      "command": "python",
      "args": ["-m", "igenius_mcp.server"],
      "env": { "IGENIUS_API_KEY": "ig_your_key_here" }
    }
  }
}
```

> **⚠️ Windows users:** If VS Code can't find `igenius-mcp`, use `python -m igenius_mcp.server` instead.

### 3. Desktop App (Windows)

Standalone system-tray application — works alongside any editor or IDE:

- **[Download Installer](https://github.com/vehoelite/igenius-desktop/releases/latest)** (NSIS setup or MSI)
- Built with Tauri + Rust — lightweight, native, ~5 MB
- System tray with quick access to briefings, search, and memory stats
- Configure LLM provider (LM Studio, OpenAI, Anthropic, Google) from the UI

Restart VS Code after installing the extension or adding MCP config — all 17
memory tools become available to Copilot and any MCP-compatible agent.

## Available Tools

| Tool | Description |
|------|-------------|
| `memory_briefing` | Session briefing from all memory layers (call FIRST) |
| `memory_ingest` | Ingest user/agent messages for AI extraction |
| `memory_consolidate` | Merge accumulated extracts into master briefing |
| `memory_process` | Detect trigger words and auto-classify text |
| `memory_store` | Direct store to a specific memory layer |
| `memory_search` | Natural language search across memories |
| `memory_recall` | Retrieve all persistent session memories |
| `memory_summarize` | LLM-powered summary of a memory layer |
| `memory_delete` | Delete a memory by ID |
| `memory_update` | Update fields on an existing memory |
| `memory_review` | List short-term memories for triage |
| `memory_promote` | Promote short-term → long-term |
| `memory_pin` | Pin a fact permanently (user-confirmed, never expires) |
| `memory_triggers_list` | List trigger words and their layers |
| `memory_triggers_add` | Add a new trigger word |

## LLM Requirements

iGenius uses an LLM backend for AI extraction, consolidation, and (optionally)
visual analysis. You can use a **local** or **remote** LLM provider.

### Local Setup (LM Studio, Ollama, etc.)

| Requirement | Minimum |
|---|---|
| **GPU VRAM** | 6 GB+ |
| **Recommended model** | Qwen 3.5 4B (non-thinking) or equivalent |
| **Context window** | 3,000+ tokens |

> **⚠️ IMPORTANT: Do NOT use thinking/reasoning models** (e.g. QwQ, DeepSeek R1,
> o1, o3). Thinking models emit `<think>` chains before the actual response,
> which **breaks iGenius's structured JSON extraction pipeline**. Only use
> standard non-thinking (instruct/chat) models.

> **Why these specs?** iGenius sends structured extraction prompts that expect
> clean JSON output. A 4B-parameter non-thinking model at 3k context is the
> sweet spot for fast, accurate extraction without hallucination or timeouts.
> Larger models (8B+) work too — just ensure you have the VRAM headroom and
> that the model is a **non-thinking** variant.

### Remote Setup (OpenAI, Anthropic, Google, etc.)

No local hardware requirements. Any API-accessible model works — configure the
provider, model name, and API key in the VS Code extension settings or
environment variables.

## Environment Variables

| Variable | Required | Default |
|----------|----------|---------|
| `IGENIUS_API_KEY` | Yes | — |
| `IGENIUS_API_URL` | No | `https://igenius-memory.online/v1` |

## Visual Tools (Optional)

Give your AI agent **eyes** — render any URL, take a pixel-perfect screenshot,
and get instant UI/UX analysis from a local vision model.

### Install

```bash
pip install "igenius-mcp[visual]"
python -m playwright install chromium
```

Then load a vision-capable model in [LM Studio](https://lmstudio.ai)
(e.g. Qwen 3.5 9B Vision, non-thinking).

> **⚠️ Do NOT use thinking/reasoning vision models** — same restriction as above.

### Visual MCP Tools

| Tool | Description |
|------|-------------|
| `visual_report` | Render URL → screenshot → vision analysis → full UI/UX report |
| `visual_screenshot` | Render URL → return base64-encoded PNG (no analysis) |

### Visual Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `IGENIUS_VISION_URL` | `http://localhost:1234/v1` | Vision model API endpoint |
| `IGENIUS_VISION_MODEL` | *auto-detect* | Override the vision model name |
| `IGENIUS_VIEWPORT_W` | `1280` | Screenshot viewport width |
| `IGENIUS_VIEWPORT_H` | `800` | Screenshot viewport height |

> **100% local** — screenshots and analysis never leave your machine.

## Agent Instructions

For best results, add the iGenius agent instructions to your workspace:

- **VS Code**: Place `igenius.instructions.md` in `~/.vscode/prompts/`
- **Claude Code**: Add to `CLAUDE.md`
- **Workspace**: Add to `.github/copilot-instructions.md`

Get the template at [igenius-memory.info](https://igenius-memory.info)

## How It Works

```
Agent ←→ MCP (stdio) ←→ igenius-mcp ←→ REST API ←→ iGenius Backend
```

The memory tools are a **thin proxy** — they translate MCP tool calls into REST API
requests. All AI extraction, LLM summarization, and encryption happens server-side.

The visual tools run **locally** — Playwright renders URLs on your machine and a
local vision model (e.g. LM Studio + Qwen2.5-VL) analyzes the screenshots.
Screenshots and analysis never leave your machine.

## Plans

| Plan | Price | Requests | API Keys | IPs/Key |
|------|-------|----------|----------|---------|
| Starter | Free | 1,000/week | 1 | 3 |
| Pro | $19/mo | 50,000/day | 5 | 10 |
| Enterprise | Contact | 500,000/day | 20 | 50 |

Details at [igenius-memory.store](https://igenius-memory.store)

## Coming Soon

**iGenius Context Engine** — unlimited effective context for local LLMs through
intelligent recursive summarization. Run a 3B model with a 4K context window
and handle conversations of any length.

## Links

- [Landing Page](https://igenius-memory.com)
- [Documentation](https://igenius-memory.info)
- [API Portal & Free Key](https://igenius-memory.online)
- [Store & Plans](https://igenius-memory.store)
- [VS Code Extension](https://marketplace.visualstudio.com/items?itemName=igenius-memory.igenius-memory)
- [Desktop App](https://github.com/vehoelite/igenius-desktop/releases/latest)

## Support the Project

iGenius Memory is built and maintained by [NovaMind Labs](https://github.com/vehoelite).
If you find it useful, here's how you can help:

- **Star the repo** — it helps more developers discover iGenius
- **Upgrade to Pro** — $19/mo directly funds development → [igenius-memory.store](https://igenius-memory.store)
- **Report bugs & ideas** — [open an issue](https://github.com/vehoelite/igenius-mcp/issues)
- **Spread the word** — tell your friends, tweet about it, write a blog post

Every user, star, and subscription helps keep iGenius alive and improving. Thank you!

## License

MIT
