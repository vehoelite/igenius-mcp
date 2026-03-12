# iGenius MCP — Thin Memory Server for VS Code

[![PyPI](https://img.shields.io/pypi/v/igenius-mcp?color=blue)](https://pypi.org/project/igenius-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/igenius-mcp)](https://pypi.org/project/igenius-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![GitHub](https://img.shields.io/github/stars/vehoelite/igenius-mcp?style=social)](https://github.com/vehoelite/igenius-mcp)

A lightweight MCP (Model Context Protocol) server that gives AI agents
persistent memory via the [iGenius Memory](https://igenius-memory.com) service.

Core memory tools require only an API key — all AI processing happens server-side.
Optional visual tools add local Playwright rendering and vision-model analysis.

<p align="center">
  <img src="https://raw.githubusercontent.com/vehoelite/igenius-vscode/main/igenius-motion_sm.gif" alt="iGenius Memory" width="600">
</p>

## Quick Start

```bash
pip install igenius-mcp
```

Set your API key and run:

```bash
export IGENIUS_API_KEY=ig_your_key_here
igenius-mcp
```

> **Get a free key** at [igenius-memory.online](https://igenius-memory.online#apikey)

## VS Code Setup

Add to `~/.vscode/mcp.json`:

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

Restart VS Code — all 14 memory tools are now available to Copilot and any
MCP-compatible agent.

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
| `memory_triggers_list` | List trigger words and their layers |
| `memory_triggers_add` | Add a new trigger word |

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
(e.g. `Qwen2.5-VL-7B-Instruct`).

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

## Links

- [Landing Page](https://igenius-memory.com)
- [Documentation](https://igenius-memory.info)
- [API Portal](https://igenius-memory.online)
- [Store & Plans](https://igenius-memory.store)

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
