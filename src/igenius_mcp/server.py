"""
iGenius MCP Server — Thin REST-API proxy.

Exposes all 14 iGenius Memory tools as MCP tools by forwarding requests to the
hosted API at igenius-memory.online. Requires only an API key — no database,
no LLM, no local backend.

Usage:
    pip install igenius-mcp
    IGENIUS_API_KEY=ig_xxx igenius-mcp

Or configure in VS Code mcp.json:
    {
      "servers": {
        "igenius-memory": {
          "command": "igenius-mcp",
          "env": { "IGENIUS_API_KEY": "ig_xxx" },
          "type": "stdio"
        }
      }
    }
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# ─── Configuration ──────────────────────────────────────────────────────────────

API_BASE = os.environ.get("IGENIUS_API_URL", "https://igenius-memory.online/v1")
API_KEY = os.environ.get("IGENIUS_API_KEY", "")

if not API_KEY:
    print(
        "ERROR: IGENIUS_API_KEY environment variable is required.\n"
        "Get a free key at https://igenius-memory.online#apikey",
        file=sys.stderr,
    )

# ─── HTTP Client ────────────────────────────────────────────────────────────────

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=API_BASE,
            headers={
                "X-API-Key": API_KEY,
                "Content-Type": "application/json",
                "User-Agent": "iGenius-MCP/0.1.0",
            },
            timeout=120.0,
        )
    return _client


async def _api(method: str, path: str, body: dict | None = None) -> dict:
    """Make an API request and return JSON response."""
    client = _get_client()
    if method == "GET":
        resp = await client.get(path)
    else:
        resp = await client.post(path, json=body or {})
    resp.raise_for_status()
    return resp.json()


# ─── MCP Server ─────────────────────────────────────────────────────────────────

server = Server("igenius-memory")

# ─── Tool Definitions ───────────────────────────────────────────────────────────

TOOLS: list[Tool] = [
    Tool(
        name="memory_briefing",
        description=(
            "Generate a smart, LLM-synthesised session briefing from ALL memory layers. "
            "Call this FIRST in every new conversation — it replaces the need to "
            "call memory_recall + memory_summarize separately. "
            "Results are cached and only regenerated when underlying memories change."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "force": {
                    "type": "boolean",
                    "description": "Force regeneration even if memories haven't changed (default: false).",
                },
            },
        },
    ),
    Tool(
        name="memory_ingest",
        description=(
            "Ingest a single interaction message for AI-powered extraction. "
            "This is the CORE tool — call it for EVERY user prompt, agent response, "
            "tool result, or system message. The AI reads the message, extracts "
            "facts, decisions, credentials, file paths, preferences, and context, "
            "then stores a smart summary as persistent memory."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The raw interaction message to process.",
                },
                "role": {
                    "type": "string",
                    "enum": ["user", "agent", "tool", "system"],
                    "description": "Who sent this message (default: user).",
                },
            },
            "required": ["message"],
        },
    ),
    Tool(
        name="memory_consolidate",
        description=(
            "Consolidate all accumulated interaction summaries into a master briefing. "
            "Call this before context resets or when context is getting full."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "force": {
                    "type": "boolean",
                    "description": "Force regeneration even if nothing new (default: false).",
                },
            },
        },
    ),
    Tool(
        name="memory_process",
        description=(
            "Process raw text through the trigger pipeline. "
            "Detects trigger words, classifies via LLM, and auto-stores to the "
            "appropriate memory layer."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The raw text to process.",
                },
            },
            "required": ["text"],
        },
    ),
    Tool(
        name="memory_store",
        description=(
            "Directly store a memory into a specific layer, bypassing LLM classification."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "layer": {
                    "type": "string",
                    "enum": ["persistent", "long_term", "short_term"],
                },
                "title": {"type": "string", "description": "Short title (max 512 chars)."},
                "content": {"type": "string", "description": "Full memory content."},
                "category": {"type": "string"},
                "importance": {"type": "integer", "minimum": 0, "maximum": 100},
            },
            "required": ["layer", "title", "content"],
        },
    ),
    Tool(
        name="memory_search",
        description=(
            "Search memories by natural language query across short_term and long_term layers."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="memory_recall",
        description=(
            "Retrieve all active persistent memories (interaction extracts from current session)."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="memory_summarize",
        description=(
            "Summarize memories in a layer using the LLM."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "layer": {
                    "type": "string",
                    "enum": ["persistent", "long_term", "short_term"],
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    ),
    Tool(
        name="memory_delete",
        description="Delete a memory by its ID.",
        inputSchema={
            "type": "object",
            "properties": {
                "memory_id": {"type": "integer", "description": "The memory ID to delete."},
            },
            "required": ["memory_id"],
        },
    ),
    Tool(
        name="memory_update",
        description="Update fields on an existing memory.",
        inputSchema={
            "type": "object",
            "properties": {
                "memory_id": {"type": "integer"},
                "title": {"type": "string"},
                "content": {"type": "string"},
                "category": {"type": "string"},
                "importance": {"type": "integer", "minimum": 0, "maximum": 100},
                "layer": {"type": "string", "enum": ["persistent", "long_term", "short_term"]},
            },
            "required": ["memory_id"],
        },
    ),
    Tool(
        name="memory_review",
        description=(
            "List short-term memories for user triage. Promote keepers or discard."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
        },
    ),
    Tool(
        name="memory_promote",
        description="Promote a short-term memory to long-term storage.",
        inputSchema={
            "type": "object",
            "properties": {
                "memory_id": {"type": "integer"},
            },
            "required": ["memory_id"],
        },
    ),
    Tool(
        name="memory_triggers_list",
        description="List all configured trigger words and their target layers.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="memory_triggers_add",
        description="Add a new trigger word that maps to a memory layer.",
        inputSchema={
            "type": "object",
            "properties": {
                "word": {"type": "string"},
                "target_layer": {"type": "string", "enum": ["persistent", "long_term", "short_term"]},
                "description": {"type": "string"},
            },
            "required": ["word", "target_layer"],
        },
    ),
]

# \u2500 Visual Tools (run locally \u2014 Playwright + vision model) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

VISUAL_TOOLS: list[Tool] = [
    Tool(
        name="visual_report",
        description=(
            "Render HTML/URL in a headless browser, screenshot it, and send the "
            "screenshot to a local vision AI for a detailed UI/UX analysis report. "
            "Returns layout issues, visual bugs, contrast problems, and fix suggestions. "
            "As seamless as a syntax check \u2014 one call, full visual feedback. "
            "Requires: pip install igenius-mcp[visual] && playwright install chromium"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "html": {
                    "type": "string",
                    "description": "Raw HTML string to render. Use this OR file OR url.",
                },
                "file": {
                    "type": "string",
                    "description": "Absolute path to an HTML file to render.",
                },
                "url": {
                    "type": "string",
                    "description": "URL to screenshot (e.g. http://localhost:3000).",
                },
                "focus": {
                    "type": "string",
                    "description": "Optional focus area for the analysis (e.g. 'navbar alignment', 'mobile layout', 'color contrast').",
                },
                "viewport_width": {
                    "type": "integer",
                    "description": "Browser viewport width in pixels (default: 1280).",
                },
                "viewport_height": {
                    "type": "integer",
                    "description": "Browser viewport height in pixels (default: 900).",
                },
                "full_page": {
                    "type": "boolean",
                    "description": "Capture the full scrollable page (default: true).",
                },
            },
        },
    ),
    Tool(
        name="visual_screenshot",
        description=(
            "Render HTML/URL and return ONLY the base64 screenshot (no vision analysis). "
            "Useful when you want to show the user what the UI looks like, or when "
            "using your own vision capabilities. Returns a base64 PNG string."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "html": {
                    "type": "string",
                    "description": "Raw HTML string to render. Use this OR file OR url.",
                },
                "file": {
                    "type": "string",
                    "description": "Absolute path to an HTML file to render.",
                },
                "url": {
                    "type": "string",
                    "description": "URL to screenshot (e.g. http://localhost:3000).",
                },
                "viewport_width": {
                    "type": "integer",
                    "description": "Browser viewport width in pixels (default: 1280).",
                },
                "viewport_height": {
                    "type": "integer",
                    "description": "Browser viewport height in pixels (default: 900).",
                },
                "full_page": {
                    "type": "boolean",
                    "description": "Capture the full scrollable page (default: true).",
                },
            },
        },
    ),
]


# ─── Tool Dispatch ──────────────────────────────────────────────────────────────

ROUTE_MAP: dict[str, tuple[str, str]] = {
    # name → (HTTP method, path template)
    "memory_briefing":       ("GET",  "/briefing"),
    "memory_ingest":         ("POST", "/ingest"),
    "memory_consolidate":    ("POST", "/consolidate"),
    "memory_process":        ("POST", "/process"),
    "memory_store":          ("POST", "/memories"),
    "memory_search":         ("GET",  "/memories/search"),
    "memory_recall":         ("GET",  "/memories/layer/persistent"),
    "memory_summarize":      ("POST", "/memories/summarize"),
    "memory_delete":         ("DELETE", "/memories/{memory_id}"),
    "memory_update":         ("PATCH",  "/memories/{memory_id}"),
    "memory_review":         ("GET",  "/memories/review"),
    "memory_promote":        ("POST", "/memories/{memory_id}/promote"),
    "memory_triggers_list":  ("GET",  "/triggers"),
    "memory_triggers_add":   ("POST", "/triggers"),
}


def _has_playwright() -> bool:
    """Check if playwright is installed."""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


@server.list_tools()
async def list_tools() -> list[Tool]:
    tools = list(TOOLS)
    if _has_playwright():
        tools.extend(VISUAL_TOOLS)
    return tools


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        # Visual tools run locally — not proxied to REST
        if name in ("visual_report", "visual_screenshot"):
            result = await _dispatch_visual(name, arguments)
        else:
            result = await _dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    except httpx.HTTPStatusError as e:
        detail = e.response.text
        try:
            detail = e.response.json().get("detail", detail)
        except Exception:
            pass
        return [TextContent(type="text", text=json.dumps({"error": str(detail), "status": e.response.status_code}))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def _dispatch(name: str, args: dict[str, Any]) -> Any:
    """Route tool calls to REST API endpoints."""
    route = ROUTE_MAP.get(name)
    if not route:
        return {"error": f"Unknown tool: {name}"}

    method, path_template = route
    client = _get_client()

    # Substitute path params like {memory_id}
    path = path_template
    path_args = {}
    for key in list(args.keys()):
        placeholder = f"{{{key}}}"
        if placeholder in path_template:
            path = path.replace(placeholder, str(args[key]))
            path_args[key] = args.pop(key)

    # Build request
    if method == "GET":
        # Convert remaining args to query params
        params = {}
        if name == "memory_briefing" and args.get("force"):
            params["force"] = "true"
        elif name == "memory_search":
            params["q"] = args.get("query", "")
            if args.get("limit"):
                params["limit"] = str(args["limit"])
        elif name == "memory_review":
            if args.get("limit"):
                params["limit"] = str(args["limit"])
        resp = await client.get(path, params=params)
    elif method == "DELETE":
        resp = await client.delete(path)
    elif method == "PATCH":
        resp = await client.patch(path, json=args)
    else:
        resp = await client.post(path, json=args)

    resp.raise_for_status()
    return resp.json()


# ─── Visual Dispatch ────────────────────────────────────────────────────────────

async def _dispatch_visual(name: str, args: dict[str, Any]) -> Any:
    """Handle visual tool calls locally."""
    from .visual import visual_report as _visual_report, render_screenshot
    import base64

    # Normalise args
    kwargs: dict[str, Any] = {}
    if args.get("html"):
        kwargs["html"] = args["html"]
    elif args.get("file"):
        kwargs["file"] = args["file"]
    elif args.get("url"):
        kwargs["url"] = args["url"]
    else:
        return {"error": "Provide one of: html, file, or url"}

    if args.get("viewport_width"):
        kwargs["viewport_w"] = args["viewport_width"]
    if args.get("viewport_height"):
        kwargs["viewport_h"] = args["viewport_height"]
    if "full_page" in args:
        kwargs["full_page"] = args["full_page"]

    if name == "visual_report":
        if args.get("focus"):
            kwargs["focus"] = args["focus"]
        return await _visual_report(**kwargs)

    elif name == "visual_screenshot":
        # Return just the base64 screenshot
        try:
            png_bytes = await render_screenshot(**kwargs)
            b64 = base64.b64encode(png_bytes).decode("utf-8")
            return {
                "screenshot_base64": b64,
                "size_kb": round(len(png_bytes) / 1024, 1),
                "viewport": f"{kwargs.get('viewport_w', 1280)}x{kwargs.get('viewport_h', 900)}",
            }
        except Exception as e:
            return {"error": str(e), "step": "render"}

    return {"error": f"Unknown visual tool: {name}"}


# ─── Entry point ────────────────────────────────────────────────────────────────

async def _run():
    if not API_KEY:
        print(
            "FATAL: Set IGENIUS_API_KEY environment variable.\n"
            "Get a free key at https://igenius-memory.online#apikey",
            file=sys.stderr,
        )
        sys.exit(1)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    asyncio.run(_run())


if __name__ == "__main__":
    main()
