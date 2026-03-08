# iGenius MCP — Thin Memory Server for VS Code

A lightweight MCP (Model Context Protocol) server that gives AI agents
persistent memory via the [iGenius Memory](https://igenius-memory.com) service.

No database, no LLM, no local backend required — just an API key.

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

This package is a **thin proxy** — it translates MCP tool calls into REST API
requests. All processing (AI extraction, LLM summarization, encryption) happens
server-side. Your data never touches the local machine.

## Plans

| Plan | Price | Includes |
|------|-------|----------|
| Starter | Free | 50 memories, all 14 tools |
| Pro | $19/mo | Unlimited memories, priority, encryption |
| Enterprise | Contact | Custom deployment, SLA |

Details at [igenius-memory.store](https://igenius-memory.store)

## Links

- [Landing Page](https://igenius-memory.com)
- [Documentation](https://igenius-memory.info)
- [API Portal](https://igenius-memory.online)
- [Store & Plans](https://igenius-memory.store)

## License

MIT
