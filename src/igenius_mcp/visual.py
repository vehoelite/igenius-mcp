"""
iGenius Visual — Render · Screenshot · Analyze

Gives AI agents eyes. Renders HTML/React locally via Playwright,
screenshots the output, feeds it to a local vision model (LM Studio),
and returns a detailed UI analysis report.

Usage (from MCP):
    visual_report(html="<html>...</html>")
    visual_report(file="/path/to/index.html")
    visual_report(url="http://localhost:3000")

Environment:
    IGENIUS_VISION_URL   — LM Studio endpoint (default: http://localhost:1234/v1)
    IGENIUS_VISION_MODEL — Vision model name (default: auto-detect)
    IGENIUS_VIEWPORT_W   — Browser width  (default: 1280)
    IGENIUS_VIEWPORT_H   — Browser height (default: 900)
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx

# ─── Configuration ──────────────────────────────────────────────────────────────

VISION_URL = os.environ.get("IGENIUS_VISION_URL", "http://localhost:1234/v1")
VISION_MODEL = os.environ.get("IGENIUS_VISION_MODEL", "")
VISION_API_KEY = os.environ.get("IGENIUS_VISION_KEY", "")
VIEWPORT_W = int(os.environ.get("IGENIUS_VIEWPORT_W", "1280"))
VIEWPORT_H = int(os.environ.get("IGENIUS_VIEWPORT_H", "900"))

def _vision_headers() -> dict[str, str]:
    """Build auth headers for the vision model endpoint."""
    if VISION_API_KEY:
        return {"Authorization": f"Bearer {VISION_API_KEY}"}
    return {}

# Tone-scaled analysis prompts (1 = gentle, 5 = brutal)
TONE_PROMPTS: dict[int, str] = {
    1: """You are a supportive UI/UX design partner reviewing a screenshot of a web interface.
Your goal is to celebrate what's working and only mention truly serious problems.

Structure your report as:
1. **What Works Well** — Highlight strong design choices generously.
2. **One Thing to Consider** — Only if something genuinely hurts usability or accessibility.
3. **Overall Impression** — Professional quality score 1-10, encouraging summary.

Be warm and encouraging. If the UI looks good, say so confidently. Skip minor nitpicks entirely.""",

    2: """You are a supportive UI/UX design partner reviewing a screenshot of a web interface.
Your goal is to highlight what's working well and gently flag only serious issues that would meaningfully
impact user experience, accessibility, or professionalism.

Structure your report as:
1. **What Works Well** — Call out strong design choices, good use of color, clean layout, nice typography, etc.
2. **Accessibility Check** — Only flag genuine WCAG concerns (contrast failures, missing labels, etc.)
3. **Suggestions** — 1-3 gentle improvement ideas if anything stands out. Use "consider" / "you might" language.
4. **Overall Impression** — A professional quality score 1-10 and a brief encouraging summary.

Keep the report concise and constructive. Focus on the big picture rather than nitpicking minor details.
Only mention CSS/HTML fixes for serious issues. If the UI looks good, say so confidently.""",

    3: """You are a balanced UI/UX reviewer analyzing a screenshot of a web interface.
Provide honest, constructive feedback — acknowledge what works well, then cover areas for improvement.

Structure your report as:
1. **Strengths** — What's working well in the design.
2. **Layout & Spacing** — Alignment, overflow, balance.
3. **Typography & Color** — Readability, contrast, hierarchy.
4. **Component Quality** — Are buttons, forms, cards polished?
5. **Suggestions** — Top 3 improvements with brief fix ideas.
6. **Overall Impression** — Professional quality score 1-10.

Be specific but fair. Reference element positions and provide CSS/HTML fix suggestions where helpful.""",

    4: """You are a thorough UI/UX reviewer analyzing a screenshot of a web interface.
Provide a detailed, actionable report. Be direct and don't sugarcoat issues.

Structure your report as:
1. **Layout & Spacing** — Alignment issues, overflow, cramped or empty areas, visual balance.
2. **Typography** — Readability, contrast, hierarchy, font sizing consistency.
3. **Color & Contrast** — WCAG compliance concerns, color harmony, dark/light mode issues.
4. **Component Quality** — Buttons, forms, cards, navbars — do they look polished?
5. **Responsiveness Clues** — Does the layout look like it would break at other sizes?
6. **Visual Bugs** — Overlapping elements, cut-off text, broken images, unwanted scrollbars.
7. **Overall Impression** — Professional quality score 1-10, top 3 things to fix first.

Be specific. Reference element positions and provide CSS/HTML fix suggestions.""",

    5: """You are a ruthless UI/UX critic analyzing a screenshot of a web interface.
Tear it apart. Find every flaw, no matter how small. No compliments unless truly earned.

Structure your report as:
1. **Layout & Spacing** — Every alignment issue, overflow, imbalance, wasted space.
2. **Typography** — Every readability issue, inconsistency, bad hierarchy.
3. **Color & Contrast** — Every WCAG failure, clashing colors, contrast problems.
4. **Component Quality** — Every unpolished button, form, card. Does it look amateur?
5. **Responsiveness** — Will it break? Where and how?
6. **Visual Bugs** — Everything: overlaps, cut-off text, broken images, phantom scrollbars.
7. **Pixel-level Issues** — Misaligned elements, inconsistent padding, rounding errors.
8. **Verdict** — Harsh quality score 1-10, ranked list of everything to fix.

Be specific and unforgiving. Reference exact positions. Provide CSS/HTML fixes for every issue found.""",
}

DEFAULT_STRICTNESS = int(os.environ.get("IGENIUS_VISUAL_STRICTNESS", "2"))


# ─── Renderer ───────────────────────────────────────────────────────────────────

async def render_screenshot(
    *,
    html: str | None = None,
    file: str | None = None,
    url: str | None = None,
    viewport_w: int = VIEWPORT_W,
    viewport_h: int = VIEWPORT_H,
    full_page: bool = True,
    wait_ms: int = 1500,
) -> bytes:
    """
    Render a page and return a PNG screenshot as bytes.

    Exactly one of html, file, or url must be provided.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright is required for visual reports.\n"
            "Install it:  pip install playwright && playwright install chromium"
        )

    # Determine what to load
    if html:
        # Write HTML to temp file so Playwright can open it
        tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8")
        tmp.write(html)
        tmp.close()
        target_url = f"file:///{tmp.name.replace(os.sep, '/')}"
        cleanup_path = tmp.name
    elif file:
        resolved = Path(file).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"File not found: {file}")
        target_url = f"file:///{str(resolved).replace(os.sep, '/')}"
        cleanup_path = None
    elif url:
        target_url = url
        cleanup_path = None
    else:
        raise ValueError("Provide one of: html, file, or url")

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(
                viewport={"width": viewport_w, "height": viewport_h}
            )
            await page.goto(target_url, wait_until="networkidle", timeout=15000)

            # Extra wait for animations/fonts to settle
            if wait_ms > 0:
                await asyncio.sleep(wait_ms / 1000)

            screenshot_bytes = await page.screenshot(full_page=full_page, type="png")
            await browser.close()
    finally:
        # Clean up temp file if we created one
        if cleanup_path:
            try:
                os.unlink(cleanup_path)
            except OSError:
                pass

    return screenshot_bytes


# ─── Vision Model ───────────────────────────────────────────────────────────────

async def _detect_vision_model(client: httpx.AsyncClient) -> str:
    """Auto-detect a loaded vision model from LM Studio."""
    try:
        resp = await client.get("/models", timeout=5.0)
        resp.raise_for_status()
        models = resp.json().get("data", [])
        # Prefer known vision-capable models (ordered by priority)
        vision_keywords = [
            "qwen3.5",    # Qwen3.5 has native vision support
            "llava",
            "vision",
            "vl",
            "minicpm",
            "qwen2-vl",
            "internvl",
            "image-engineer",
        ]
        for kw in vision_keywords:
            for m in models:
                model_id = m.get("id", "").lower()
                if kw in model_id:
                    return m["id"]
        # Fallback: use first available model
        if models:
            return models[0]["id"]
    except Exception:
        pass
    return ""


async def analyze_screenshot(
    screenshot_png: bytes,
    *,
    prompt: str | None = None,
    focus: str | None = None,
    strictness: int = DEFAULT_STRICTNESS,
) -> dict[str, Any]:
    """
    Send a screenshot to a local vision model and get a UI analysis report.

    Args:
        screenshot_png: Raw PNG bytes of the screenshot.
        prompt: Custom analysis prompt (overrides default and strictness).
        focus: Optional focus area (e.g. "navbar alignment" or "mobile layout").
               Gets appended to the system prompt.
        strictness: Tone slider 1-5 (1=gentle, 2=supportive, 3=balanced, 4=thorough, 5=brutal).

    Returns:
        dict with keys: report, model, tokens_used, image_size_kb, strictness
    """
    b64_image = base64.b64encode(screenshot_png).decode("utf-8")
    image_size_kb = round(len(screenshot_png) / 1024, 1)

    # Clamp strictness to valid range
    strictness = max(1, min(5, strictness))
    system_prompt = prompt or TONE_PROMPTS[strictness]
    if focus:
        system_prompt += f"\n\n**FOCUS AREA:** Pay special attention to: {focus}"

    async with httpx.AsyncClient(
        base_url=VISION_URL, timeout=120.0, headers=_vision_headers()
    ) as client:
        model = VISION_MODEL or await _detect_vision_model(client)
        if not model:
            return {
                "error": "No vision model detected. Load a vision model in LM Studio "
                         "(e.g. LLaVA, Qwen2-VL, MiniCPM-V) or set IGENIUS_VISION_MODEL.",
                "report": None,
            }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64_image}",
                            },
                        },
                        {
                            "type": "text",
                            "text": "Analyze this UI screenshot and provide your detailed report.",
                        },
                    ],
                },
            ],
            "max_tokens": 2048,
            "temperature": 0.3,
        }

        resp = await client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

    report = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})

    return {
        "report": report,
        "model": model,
        "tokens_used": usage.get("total_tokens", 0),
        "image_size_kb": image_size_kb,
        "viewport": f"{VIEWPORT_W}x{VIEWPORT_H}",
        "strictness": strictness,
    }


# ─── High-level Pipeline ───────────────────────────────────────────────────────

async def visual_report(
    *,
    html: str | None = None,
    file: str | None = None,
    url: str | None = None,
    focus: str | None = None,
    strictness: int = DEFAULT_STRICTNESS,
    viewport_w: int = VIEWPORT_W,
    viewport_h: int = VIEWPORT_H,
    full_page: bool = True,
) -> dict[str, Any]:
    """
    Full pipeline: render → screenshot → analyze → report.

    One call, complete visual feedback. As seamless as a syntax check.
    """
    # Step 1: Render & screenshot
    try:
        screenshot = await render_screenshot(
            html=html, file=file, url=url,
            viewport_w=viewport_w, viewport_h=viewport_h,
            full_page=full_page,
        )
    except RuntimeError as e:
        return {"error": str(e), "step": "render"}
    except FileNotFoundError as e:
        return {"error": str(e), "step": "render"}
    except Exception as e:
        return {"error": f"Render failed: {e}", "step": "render"}

    # Step 2: Vision analysis
    try:
        result = await analyze_screenshot(screenshot, focus=focus, strictness=strictness)
    except httpx.ConnectError:
        return {
            "error": "Cannot connect to vision model. Is LM Studio running? "
                     f"Tried: {VISION_URL}",
            "step": "vision",
            "screenshot_size_kb": round(len(screenshot) / 1024, 1),
        }
    except httpx.HTTPStatusError as e:
        detail = e.response.text
        try:
            detail = e.response.json()
        except Exception:
            pass
        return {
            "error": f"Vision model returned {e.response.status_code}: {detail}",
            "step": "vision",
        }
    except Exception as e:
        return {"error": f"Vision analysis failed: {type(e).__name__}: {e}", "step": "vision"}

    return result
