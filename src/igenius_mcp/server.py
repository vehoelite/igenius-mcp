"""
iGenius MCP Server — Client-side LLM proxy.

Exposes all iGenius Memory tools as MCP tools.  LLM-dependent operations
(ingest, consolidate, process, summarize) use a **prepare → local-LLM →
finalize** flow so no AI model is needed on the server.

The client calls the server's ``/xxx/prepare`` endpoint to get a prompt,
runs the prompt through a local OpenAI-compatible LLM (e.g. LM Studio,
Ollama, vLLM), then sends the result back via ``/xxx/finalize``.

Usage:
    pip install igenius-mcp
    IGENIUS_API_KEY=ig_xxx igenius-mcp

Or configure in VS Code mcp.json:
    {
      "servers": {
        "igenius-memory": {
          "command": "igenius-mcp",
          "env": {
            "IGENIUS_API_KEY": "ig_xxx",
            "IGENIUS_PROJECT": "my-app",
            "IGENIUS_LLM_BASE_URL": "http://localhost:1234/v1",
            "IGENIUS_LLM_MODEL": "auto"
          },
          "type": "stdio"
        }
      }
    }

Environment Variables:
    IGENIUS_API_KEY      — Required. Your API key.
    IGENIUS_API_URL      — Optional. Override the API base URL (default: igenius-memory.online).
    IGENIUS_PROJECT      — Optional. Default project scope for all memory operations.
    IGENIUS_LLM_BASE_URL — Optional. OpenAI-compatible base URL (default: http://localhost:1234/v1).
    IGENIUS_LLM_MODEL    — Optional. Model name or "auto" to detect first loaded model (default: auto).
    IGENIUS_LLM_API_KEY  — Optional. API key for the local LLM (default: lm-studio).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# ─── Configuration ──────────────────────────────────────────────────────────────

API_BASE = os.environ.get("IGENIUS_API_URL", "https://igenius-memory.online/v1")
API_KEY = os.environ.get("IGENIUS_API_KEY", "")

# Local LLM configuration (OpenAI-compatible endpoint)
LLM_BASE_URL = os.environ.get("IGENIUS_LLM_BASE_URL", "http://localhost:1234/v1")
LLM_MODEL = os.environ.get("IGENIUS_LLM_MODEL", "auto")
LLM_API_KEY = os.environ.get("IGENIUS_LLM_API_KEY", "lm-studio")

if not API_KEY:
    print(
        "ERROR: IGENIUS_API_KEY environment variable is required.\n"
        "Get a free key at https://igenius-memory.online#apikey",
        file=sys.stderr,
    )

# ─── HTTP Client (API server) ──────────────────────────────────────────────────

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=API_BASE,
            headers={
                "X-API-Key": API_KEY,
                "Content-Type": "application/json",
                "User-Agent": "iGenius-MCP/0.5.5",
            },
            timeout=120.0,
        )
    return _client


# ─── Local LLM Client ──────────────────────────────────────────────────────────

_llm_client: httpx.AsyncClient | None = None
_resolved_model: str | None = None


def _get_llm_client() -> httpx.AsyncClient:
    global _llm_client
    if _llm_client is None or _llm_client.is_closed:
        _llm_client = httpx.AsyncClient(
            base_url=LLM_BASE_URL,
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=300.0,
        )
    return _llm_client


async def _resolve_model() -> str:
    """Resolve the model name. If 'auto', pick the first loaded model."""
    global _resolved_model
    if _resolved_model:
        return _resolved_model
    if LLM_MODEL and LLM_MODEL.lower() != "auto":
        _resolved_model = LLM_MODEL
        return _resolved_model
    # Auto-detect: query /v1/models
    client = _get_llm_client()
    try:
        resp = await client.get("/models")
        resp.raise_for_status()
        models = resp.json().get("data", [])
        # Filter out embedding models
        chat_models = [
            m["id"] for m in models
            if "embed" not in m["id"].lower()
        ]
        if chat_models:
            _resolved_model = chat_models[0]
        elif models:
            _resolved_model = models[0]["id"]
        else:
            raise RuntimeError("No models loaded in local LLM server")
    except httpx.ConnectError:
        raise RuntimeError(
            f"Cannot connect to local LLM at {LLM_BASE_URL}. "
            "Start LM Studio / Ollama or set IGENIUS_LLM_BASE_URL."
        )
    return _resolved_model


async def _call_local_llm(
    system_prompt: str,
    user_content: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    response_format: dict | None = None,
) -> str:
    """Call the local OpenAI-compatible LLM and return the response text."""
    model = await _resolve_model()
    client = _get_llm_client()

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = response_format

    resp = await client.post("/chat/completions", json=payload)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


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
            "Return the latest consolidated briefing with pinned facts prepended. "
            "This is a PURE READER — no LLM call, no mutations.  It serves: "
            "(1) Pinned facts verbatim, (2) Consolidated briefing prose from last "
            "memory_consolidate, (3) Suggested pins for user review, (4) Live stats. "
            "Call memory_consolidate first, then this to read the result. "
            "ALWAYS pass 'project' to get the briefing for the current workspace."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "force": {
                    "type": "boolean",
                    "description": "Force regeneration even if memories haven't changed (default: false).",
                },
                "project": {
                    "type": "string",
                    "description": "Project/workspace name. Returns briefing scoped to this project + global context.",
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
            "then stores a smart summary as short-term memory scoped to the current project. "
            "ALWAYS pass the 'project' parameter so memories stay isolated per workspace."
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
                "project": {
                    "type": "string",
                    "description": (
                        "Project/workspace name to scope this memory to. "
                        "Use the workspace folder name (e.g. 'my-app', 'igenius'). "
                        "Omit for global memories visible in all projects."
                    ),
                },
            },
            "required": ["message"],
        },
    ),
    Tool(
        name="memory_consolidate",
        description=(
            "Consolidate all short-term interaction summaries into a master briefing. "
            "Call this FIRST at every session start, before memory_briefing. "
            "Also call when context is getting full. "
            "ALWAYS pass the 'project' parameter to scope consolidation to the current workspace."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "force": {
                    "type": "boolean",
                    "description": "Force regeneration even if nothing new (default: false).",
                },
                "project": {
                    "type": "string",
                    "description": "Project/workspace name to scope consolidation to. Omit for global.",
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
                "project": {
                    "type": "string",
                    "description": "Project scope. Omit for global memory.",
                },
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
                "project": {
                    "type": "string",
                    "description": "Project scope. Returns project-scoped + global results.",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="memory_recall",
        description=(
            "Retrieve all active short-term memories (interaction extracts from current session). "
            "For consolidated briefing, use memory_briefing instead."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project": {
                    "type": "string",
                    "description": "Project scope. Returns project-scoped + global memories.",
                },
            },
        },
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
                "project": {
                    "type": "string",
                    "description": "Project scope. Returns project-scoped + global memories.",
                },
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
    Tool(
        name="memory_pin",
        description=(
            "Pin a fact permanently. Pinned memories NEVER expire, are always "
            "encrypted, and appear at the top of every briefing. IMPORTANT: "
            "Only call this after the USER has explicitly confirmed they want "
            "the fact pinned.\n\n"
            "PROJECT SCOPING: Ask the user 'Pin this globally or just for "
            "[current project]?' — global pins (omit project) appear in ALL "
            "project briefings; project-scoped pins appear only in that project."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short title for the pinned fact (max 512 chars).",
                },
                "content": {
                    "type": "string",
                    "description": "The fact to pin permanently.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category (credential, identity, config, etc.).",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for filtering.",
                },
                "project": {
                    "type": "string",
                    "description": (
                        "Project scope for the pin. Omit or null = GLOBAL pin "
                        "(visible in every project). Set to a project name for "
                        "a project-specific pin. The agent MUST ask the user "
                        "which they prefer."
                    ),
                },
            },
            "required": ["title", "content"],
        },
    ),
]

# \u2500 Visual Tools (run locally \u2014 Playwright + vision model) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

VISUAL_TOOLS: list[Tool] = [
    Tool(
        name="visual_report",
        description=(
            "Render HTML/URL in a LOCAL headless browser on the USER'S MACHINE, "
            "screenshot it, and send the screenshot to a local vision AI for a "
            "detailed UI/UX analysis report. Returns layout issues, visual bugs, "
            "contrast problems, and fix suggestions. "
            "IMPORTANT: This tool runs LOCALLY — it CAN access localhost, "
            "127.0.0.1, and any URL reachable from the user's machine. "
            "Screenshots and analysis never leave the user's computer. "
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
                "strictness": {
                    "type": "integer",
                    "description": "How critical the review should be, 1-5. 1=gentle (mostly positive), 2=supportive (default), 3=balanced, 4=thorough, 5=brutal (nitpicks everything).",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 2,
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
            "Render HTML/URL in a LOCAL headless browser on the USER'S MACHINE "
            "and return ONLY the base64 screenshot (no vision analysis). "
            "IMPORTANT: This tool runs LOCALLY — it CAN access localhost, "
            "127.0.0.1, and any URL reachable from the user's machine. "
            "Screenshots never leave the user's computer. "
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
    "memory_store":          ("POST", "/memories"),
    "memory_search":         ("GET",  "/memories/search"),
    "memory_recall":         ("GET",  "/memories/layer/short_term"),
    "memory_delete":         ("DELETE", "/memories/{memory_id}"),
    "memory_update":         ("PATCH",  "/memories/{memory_id}"),
    "memory_review":         ("GET",  "/memories/review"),
    "memory_promote":        ("POST", "/memories/{memory_id}/promote"),
    "memory_triggers_list":  ("GET",  "/triggers"),
    "memory_triggers_add":   ("POST", "/triggers"),
    "memory_pin":            ("POST", "/memories"),
}

# Tools that go through prepare → local LLM → finalize
LLM_TOOLS = {"memory_ingest", "memory_consolidate", "memory_process", "memory_summarize"}


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
        elif name in LLM_TOOLS:
            result = await _dispatch_llm(name, arguments)
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


async def _dispatch_llm(name: str, args: dict[str, Any]) -> Any:
    """Route LLM-dependent tools through prepare → local LLM → finalize."""
    client = _get_client()

    # Resolve project scope (same logic as _dispatch)
    _NO_PROJECT = object()
    project = args.pop("project", _NO_PROJECT)
    if project is _NO_PROJECT:
        project = os.environ.get("IGENIUS_PROJECT")
    elif not project:
        project = None

    if name == "memory_ingest":
        # Step 1: prepare
        body = {"message": args["message"], "role": args.get("role", "user")}
        if project:
            body["project"] = project
        resp = await client.post("/ingest/prepare", json=body)
        resp.raise_for_status()
        prep = resp.json()
        if not prep.get("ready"):
            return prep  # e.g. empty message

        # Step 2: call local LLM
        llm_response = await _call_local_llm(
            prep["system_prompt"],
            prep["user_content"],
            temperature=prep.get("temperature", 0.15),
            max_tokens=prep.get("max_tokens", 1024),
            response_format=prep.get("response_format"),
        )

        # Step 3: finalize
        resp = await client.post("/ingest/finalize", json={
            "llm_response": llm_response,
            "metadata": prep["metadata"],
        })
        resp.raise_for_status()
        return resp.json()

    elif name == "memory_consolidate":
        # Step 1: prepare
        params: dict[str, str] = {}
        if args.get("force"):
            params["force"] = "true"
        if project:
            params["project"] = project
        resp = await client.post("/consolidate/prepare", params=params)
        resp.raise_for_status()
        prep = resp.json()
        if not prep.get("ready"):
            return prep.get("fallback_response", prep)

        # Step 2: call local LLM
        llm_response = await _call_local_llm(
            prep["system_prompt"],
            prep["user_content"],
            temperature=prep.get("temperature", 0.25),
            max_tokens=prep.get("max_tokens", 4096),
        )

        # Step 3: finalize
        resp = await client.post("/consolidate/finalize", json={
            "llm_response": llm_response,
            "metadata": prep["metadata"],
        })
        resp.raise_for_status()
        return resp.json()

    elif name == "memory_process":
        # Step 1: prepare
        resp = await client.post("/process/prepare", json={"text": args["text"]})
        resp.raise_for_status()
        prep = resp.json()
        if not prep.get("ready"):
            return prep

        # Step 2: call local LLM
        llm_response = await _call_local_llm(
            prep["system_prompt"],
            prep["user_content"],
            temperature=prep.get("temperature", 0.2),
            max_tokens=prep.get("max_tokens", 1024),
            response_format=prep.get("response_format"),
        )

        # Step 3: finalize
        resp = await client.post("/process/finalize", json={
            "llm_response": llm_response,
            "metadata": prep["metadata"],
        })
        resp.raise_for_status()
        return resp.json()

    elif name == "memory_summarize":
        # Step 1: prepare
        params = {}
        if args.get("layer"):
            params["layer"] = args["layer"]
        if args.get("limit"):
            params["limit"] = str(args["limit"])
        if project:
            params["project"] = project
        resp = await client.post("/memories/summarize/prepare", params=params)
        resp.raise_for_status()
        prep = resp.json()
        if not prep.get("ready"):
            return prep

        # Step 2: call local LLM
        llm_response = await _call_local_llm(
            prep["system_prompt"],
            prep["user_content"],
            temperature=prep.get("temperature", 0.3),
            max_tokens=prep.get("max_tokens", 2048),
        )

        # Step 3: finalize
        resp = await client.post("/memories/summarize/finalize", json={
            "llm_response": llm_response,
            "metadata": prep["metadata"],
        })
        resp.raise_for_status()
        return resp.json()

    return {"error": f"Unknown LLM tool: {name}"}


async def _dispatch(name: str, args: dict[str, Any]) -> Any:
    """Route tool calls to REST API endpoints."""
    route = ROUTE_MAP.get(name)
    if not route:
        return {"error": f"Unknown tool: {name}"}

    method, path_template = route
    client = _get_client()

    # Special handling: memory_pin -> store with layer=pinned
    if name == "memory_pin":
        args = {
            "layer": "pinned",
            "title": args["title"],
            "content": args["content"],
            "category": args.get("category", "pinned"),
            "tags": args.get("tags", ["pinned"]),
            "importance": 100,
            "project": args.get("project"),
        }

    # Extract project for query param use on GET/consolidate/summarize
    # Use a sentinel so we can tell "agent didn't pass project" apart from
    # "agent explicitly passed project=null" (meaning global/unscoped).
    _NO_PROJECT = object()
    project = args.pop("project", _NO_PROJECT)

    if project is _NO_PROJECT:
        # Agent didn't pass project at all — fall back to env var
        project = os.environ.get("IGENIUS_PROJECT")
    elif not project:
        # Agent explicitly passed null / empty string — means global scope
        project = None

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
        if name == "memory_briefing":
            if args.get("force"):
                params["force"] = "true"
        elif name == "memory_search":
            params["q"] = args.get("query", "")
            if args.get("limit"):
                params["limit"] = str(args["limit"])
        elif name == "memory_review":
            if args.get("limit"):
                params["limit"] = str(args["limit"])
        elif name == "memory_recall":
            pass  # no extra params beyond project
        # Always add project to GET query params
        if project:
            params["project"] = project
        resp = await client.get(path, params=params)
    elif method == "DELETE":
        resp = await client.delete(path)
    elif method == "PATCH":
        resp = await client.patch(path, json=args)
    else:
        # POST: include project in JSON body
        if project is not None:
            args["project"] = project
        # consolidate uses query params, not body
        if name == "memory_consolidate":
            params = {}
            if args.get("force"):
                params["force"] = "true"
            if project:
                params["project"] = project
            resp = await client.post(path, params=params)
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
        if args.get("strictness"):
            kwargs["strictness"] = int(args["strictness"])
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
