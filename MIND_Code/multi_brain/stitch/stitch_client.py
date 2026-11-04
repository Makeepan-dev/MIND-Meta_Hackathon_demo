"""
MIND Google Stitch Client — Direct MCP & REST Client for Google Stitch Design Engine.
Connects MIND to Google Stitch for high-fidelity, design-first UI generation,
screen editing, variant exploration, and design system persistence.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("mind.multi_brain.stitch")


@dataclass
class StitchScreenResult:
    """Represents a generated or edited Stitch screen and its local assets."""
    screen_id: str
    project_id: str
    title: str
    html_content: str
    html_path: Optional[str] = None
    screenshot_path: Optional[str] = None
    design_system_id: Optional[str] = None
    design_md_path: Optional[str] = None
    site_md_path: Optional[str] = None
    raw_screen_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "screen_id": self.screen_id,
            "project_id": self.project_id,
            "title": self.title,
            "html_path": self.html_path,
            "screenshot_path": self.screenshot_path,
            "design_system_id": self.design_system_id,
            "design_md_path": self.design_md_path,
            "site_md_path": self.site_md_path,
        }


class StitchClient:
    """
    Client for interacting with Google Stitch via official MCP JSON-RPC protocol
    and direct REST APIs.
    """

    DEFAULT_MCP_URL = "https://stitch.googleapis.com/mcp"
    DEFAULT_REST_URL = "https://stitch.googleapis.com/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        mcp_url: Optional[str] = None,
        rest_url: Optional[str] = None,
        mock_mode: Optional[bool] = None,
    ) -> None:
        self.mcp_url = mcp_url or self.DEFAULT_MCP_URL
        self.rest_url = rest_url or self.DEFAULT_REST_URL
        
        # Load API key securely
        if api_key is not None:
            self._api_key = api_key
        else:
            self._api_key = self._resolve_api_key()
        
        # Determine mock mode: explicit flag, live stitch override, or test environment
        if mock_mode is not None:
            self._mock_mode = mock_mode
        elif os.environ.get("MIND_LIVE_STITCH") == "1":
            self._mock_mode = False
        else:
            is_test_env = bool(
                os.environ.get("MIND_TEST_MODE") == "1"
                or os.environ.get("MIND_OFFLINE_STITCH") == "1"
                or "pytest" in sys.modules
                or os.environ.get("PYTEST_CURRENT_TEST")
                or not self._api_key
            )
            self._mock_mode = is_test_env

        self._cached_project_id: Optional[str] = None

    def _resolve_api_key(self) -> Optional[str]:
        """Resolves STITCH_API_KEY from environment or workspace .env files without logging."""
        key = os.environ.get("STITCH_API_KEY", "").strip()
        if key:
            return key

        # Look in workspace root
        for candidate in [Path.cwd() / ".env", Path(__file__).resolve().parents[3] / ".env"]:
            if candidate.exists():
                try:
                    for line in candidate.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line.startswith("STITCH_API_KEY="):
                            val = line.split("=", 1)[1].strip()
                            # Strip surrounding quotes if present
                            if val.startswith(('"', "'")) and val.endswith(('"', "'")):
                                val = val[1:-1].strip()
                            if val:
                                return val
                except Exception:
                    pass
        return None

    def is_available(self) -> bool:
        """Returns True if Stitch is configured with a valid API key or in mock mode."""
        return bool(self._api_key) or self._mock_mode

    @property
    def mock_mode(self) -> bool:
        return self._mock_mode

    # -------------------------------------------------------------------------
    # JSON-RPC 2.0 MCP Bridge
    # -------------------------------------------------------------------------

    def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        timeout: int = 120,
    ) -> Dict[str, Any]:
        """
        Executes a Stitch MCP tool call over JSON-RPC 2.0.
        Returns the parsed dictionary from structuredContent or content[0].text.
        """
        if self._mock_mode:
            return self._handle_mock_call(tool_name, arguments)

        if not self._api_key:
            raise ValueError("STITCH_API_KEY is not configured.")

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "X-Goog-Api-Key": self._api_key,
            "Content-Type": "application/json",
        }

        req = urllib.request.Request(self.mcp_url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
        except urllib.error.HTTPError as he:
            logger.error("Stitch MCP HTTP Error: %s", he.code)
            raise RuntimeError(f"Stitch API error ({he.code})") from he
        except Exception as e:
            logger.error("Stitch MCP Connection Error: %s", type(e).__name__)
            raise

        if "error" in data:
            err_msg = data["error"].get("message", "Unknown Stitch RPC error")
            raise RuntimeError(f"Stitch Tool '{tool_name}' failed: {err_msg}")

        result = data.get("result", {})
        
        # 1. Prefer structuredContent
        structured = result.get("structuredContent")
        if structured and isinstance(structured, dict):
            return structured

        # 2. Parse text content
        content_items = result.get("content", [])
        for item in content_items:
            if item.get("type") == "text" and "text" in item:
                text_val = item["text"]
                try:
                    return json.loads(text_val)
                except Exception:
                    return {"text": text_val}

        return result

    # -------------------------------------------------------------------------
    # High-Level Stitch Operations
    # -------------------------------------------------------------------------

    def list_projects(self) -> List[Dict[str, Any]]:
        """Lists existing Stitch projects."""
        res = self.call_tool("list_projects", {})
        return res.get("projects", [])

    def create_project(self, title: str) -> Dict[str, Any]:
        """Creates a new Stitch project."""
        res = self.call_tool("create_project", {"title": title})
        project = res.get("project", res)
        name = project.get("name", "")
        # Extract numeric id from 'projects/12345'
        pid = name.replace("projects/", "").strip() if name else str(project.get("id", ""))
        if pid:
            self._cached_project_id = pid
        return project

    def get_or_create_default_project(self, default_title: str = "MIND Visual Workspace") -> str:
        """Returns a usable project ID, creating one if none exists."""
        if self._cached_project_id:
            return self._cached_project_id

        try:
            projects = self.list_projects()
            if projects:
                name = projects[0].get("name", "")
                pid = name.replace("projects/", "").strip()
                if pid:
                    self._cached_project_id = pid
                    return pid
        except Exception as e:
            logger.warning("Could not list Stitch projects: %s", e)

        # Create new project
        try:
            proj = self.create_project(default_title)
            name = proj.get("name", "")
            pid = name.replace("projects/", "").strip()
            if pid:
                self._cached_project_id = pid
                return pid
        except Exception as e:
            logger.warning("Failed to create Stitch project: %s", e)

        # Default fallback ID
        self._cached_project_id = "mind_default_project"
        return self._cached_project_id

    def generate_screen(
        self,
        prompt: str,
        project_id: Optional[str] = None,
        device_type: str = "DESKTOP",
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generates a new UI screen and complete design system using Stitch AI.
        """
        pid = project_id or self.get_or_create_default_project()
        clean_pid = pid.replace("projects/", "").strip()

        args: Dict[str, Any] = {
            "projectId": clean_pid,
            "prompt": prompt,
            "deviceType": device_type,
        }
        if model_id:
            args["modelId"] = model_id

        logger.info("Calling Stitch generate_screen_from_text for project %s...", clean_pid)
        res = self.call_tool("generate_screen_from_text", args, timeout=180)
        return res

    def edit_screen(
        self,
        screen_id: str,
        prompt: str,
        project_id: Optional[str] = None,
        device_type: str = "DESKTOP",
    ) -> Dict[str, Any]:
        """
        Edits an existing screen using natural-language revision instructions.
        """
        pid = project_id or self.get_or_create_default_project()
        clean_pid = pid.replace("projects/", "").strip()
        clean_sid = screen_id.replace("screens/", "").strip()
        if "/" in clean_sid:
            clean_sid = clean_sid.split("/")[-1]

        args = {
            "projectId": clean_pid,
            "selectedScreenIds": [clean_sid],
            "prompt": prompt,
            "deviceType": device_type,
        }
        logger.info("Calling Stitch edit_screens for screen %s in project %s...", clean_sid, clean_pid)
        res = self.call_tool("edit_screens", args, timeout=180)
        return res

    def generate_variants(
        self,
        screen_id: str,
        prompt: str,
        project_id: Optional[str] = None,
        variant_count: int = 2,
    ) -> Dict[str, Any]:
        """Generates alternative design variants of an existing screen."""
        pid = project_id or self.get_or_create_default_project()
        clean_pid = pid.replace("projects/", "").strip()
        clean_sid = screen_id.replace("screens/", "").strip()
        if "/" in clean_sid:
            clean_sid = clean_sid.split("/")[-1]

        args = {
            "projectId": clean_pid,
            "screenId": clean_sid,
            "prompt": prompt,
            "variantCount": variant_count,
        }
        return self.call_tool("generate_variants", args, timeout=180)

    def download_file(self, resource_name: str) -> Dict[str, Any]:
        """
        Downloads screen assets (HTML code or Screenshot) by resource name.
        """
        args = {"name": resource_name}
        return self.call_tool("download_file", args, timeout=60)

    # -------------------------------------------------------------------------
    # Screen Asset Persistence & Context Formatter
    # -------------------------------------------------------------------------

    def save_screen_assets(
        self,
        screen_data: Dict[str, Any],
        output_dir: Path,
        prompt: str = "",
        download_screenshot: bool = False,
    ) -> StitchScreenResult:
        """
        Downloads and saves HTML, screenshots (optional), and persists
        DESIGN.md and SITE.md design specifications into the target folder.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Screen metadata
        screen_name = screen_data.get("name", "")
        screen_id = screen_name.split("/")[-1] if "/" in screen_name else screen_name
        title = screen_data.get("title", "MIND Visual Design")
        project_id = self._cached_project_id or "mind_project"
        
        if "/" in screen_name and "projects/" in screen_name:
            parts = screen_name.split("/")
            try:
                p_idx = parts.index("projects")
                project_id = parts[p_idx + 1]
            except Exception:
                pass

        # 1. Fetch HTML Code
        html_code_info = screen_data.get("htmlCode", {}) or screen_data.get("html_code", {})
        html_name = html_code_info.get("name")
        html_text = ""

        if screen_data.get("html"):
            html_text = screen_data["html"]
        elif html_name:
            try:
                dl_result = self.download_file(html_name)
                html_text = dl_result.get("html", "")
            except Exception as e:
                logger.warning("Could not download Stitch HTML file '%s': %s", html_name, e)

        # Fallback if HTML was provided directly in screen_data
        if not html_text:
            html_text = screen_data.get("dataString", "")

        # Do NOT fabricate HTML here: an empty result must surface so the
        # coordinator can fall back to the MIND Native Design Engine.
        if not html_text or not html_text.strip():
            logger.warning("Stitch screen '%s' returned no HTML content.", screen_id)

        # Write index.html
        html_path = output_dir / "index.html"
        html_path.write_text(html_text, encoding="utf-8")

        # 2. Screenshot (optional, only if requested to avoid large payloads)
        screenshot_path: Optional[Path] = None
        screenshot_info = screen_data.get("screenshot", {})
        ss_name = screenshot_info.get("name")
        if download_screenshot and ss_name:
            try:
                ss_res = self.download_file(ss_name)
                img_b64 = ss_res.get("image", "")
                if img_b64:
                    screenshot_path = output_dir / "preview.png"
                    screenshot_path.write_bytes(base64.b64decode(img_b64))
            except Exception as e:
                logger.warning("Could not download screenshot '%s': %s", ss_name, e)

        # 3. Persist DESIGN.md
        design_system_id = screen_data.get("designSystem") or screen_data.get("design_system")
        design_md_content = self.format_design_md(screen_data, prompt)
        design_md_path = output_dir / "DESIGN.md"
        design_md_path.write_text(design_md_content, encoding="utf-8")

        # 4. Persist SITE.md
        site_md_content = self.format_site_md(screen_data, prompt)
        site_md_path = output_dir / "SITE.md"
        site_md_path.write_text(site_md_content, encoding="utf-8")

        return StitchScreenResult(
            screen_id=screen_id,
            project_id=project_id,
            title=title,
            html_content=html_text,
            html_path=str(html_path),
            screenshot_path=str(screenshot_path) if screenshot_path else None,
            design_system_id=design_system_id,
            design_md_path=str(design_md_path),
            site_md_path=str(site_md_path),
            raw_screen_data=screen_data,
        )

    def format_design_md(self, screen_data: Dict[str, Any], prompt: str) -> str:
        """Generates comprehensive DESIGN.md design system context."""
        title = screen_data.get("title", "MIND UI Design")
        device_type = screen_data.get("deviceType", "DESKTOP")
        design_system = screen_data.get("designSystem", "Autonomous Stitch Design System")
        screen_id = screen_data.get("name", "").split("/")[-1]

        return f"""# Design System Specification
**Project**: {title}
**Screen ID**: `{screen_id}`
**Device Target**: {device_type}
**Design Engine**: Google Stitch AI

## Objective & Prompt
> {prompt or title}

## Design Principles
- **Modern Component Architecture**: Tailwind CSS utility classes, responsive breakpoints, flex/grid layouts.
- **Visual Contrast & Hierarchy**: High-contrast typography with modern font pairings and balanced whitespace.
- **Interactive Affordance**: Buttons, navigation links, and call-to-action cards styled with active/hover states.
- **Dark Mode Support**: Styled using semantic dark themes (`bg-slate-900`, `text-slate-100`, `border-cyan-500/30`).

## Design System Tokens
- **Theme**: {design_system}
- **Primary Accent**: Cyan / Emerald Neon (`#00F5FF` / `#10B981`)
- **Background Palette**: Deep Onyx (`#050811`, `#0A1020`, `#101A2C`)
- **Typography**: Inter / Outfit / Sans-Serif system font stack
- **Layout Model**: Responsive Desktop Grid / Flexbox
"""

    def format_site_md(self, screen_data: Dict[str, Any], prompt: str) -> str:
        """Generates SITE.md site structure and component inventory."""
        title = screen_data.get("title", "MIND Web Application")
        return f"""# Site Structure & Architecture
**Site Title**: {title}
**Generated via**: Google Stitch Engine
**Target**: Responsive Desktop Web Application

## Page Inventory
- **Landing / Main View (`index.html`)**:
  - Global Navigation Header (Brand, Links, CTA)
  - Hero Showcase Section (Headline, Subhead, Primary Action)
  - Feature Grid / Cards (Responsive multi-column showcase)
  - Detailed Information Section / Methodology
  - Contact / Footer

## Component Contracts
1. **Navbar**: Fixed/sticky top navigation bar with brand icon and navigation routes.
2. **HeroBanner**: High-impact introductory banner with prominent CTA button.
3. **CardGrid**: Dynamic responsive grid displaying core offerings or telemetry.
4. **Footer**: Copyright, links, and system status indicators.
"""

    # -------------------------------------------------------------------------
    # Deterministic Mock Mode for Tests and Offline Environments
    # -------------------------------------------------------------------------

    def _handle_mock_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Provides deterministic mock responses for test suites and offline modes."""
        if tool_name == "list_projects":
            return {
                "projects": [
                    {"name": "projects/mock_project_999", "title": "MIND Test Workspace"}
                ]
            }

        elif tool_name == "create_project":
            return {
                "project": {
                    "name": "projects/mock_project_999",
                    "title": arguments.get("title", "Mock Project"),
                }
            }

        elif tool_name == "generate_screen_from_text":
            prompt = arguments.get("prompt", "Default App")
            screen_id = "mock_screen_123"
            clean_title = prompt.replace("create a", "").replace("build a", "").strip().title()
            return {
                "name": f"projects/mock_project_999/screens/{screen_id}",
                "title": clean_title or "MIND AI Stitch Interface",
                "deviceType": arguments.get("deviceType", "DESKTOP"),
                "htmlCode": {
                    "name": f"projects/mock_project_999/files/mock_html_file",
                    "mimeType": "text/html",
                },
                "screenshot": {
                    "name": f"projects/mock_project_999/files/mock_ss_file",
                    "mimeType": "image/png",
                },
                "designSystem": "projects/mock_project_999/designSystems/ds_neon_cyber",
                "html": self._get_mock_html(clean_title, prompt, version=1),
            }

        elif tool_name == "edit_screens":
            prompt = arguments.get("prompt", "Revised App")
            screen_id = arguments.get("selectedScreenIds", ["mock_screen_123"])[0]
            return {
                "screens": [
                    {
                        "name": f"projects/mock_project_999/screens/{screen_id}",
                        "title": f"Revised: {prompt[:30]}",
                        "deviceType": arguments.get("deviceType", "DESKTOP"),
                        "htmlCode": {
                            "name": f"projects/mock_project_999/files/mock_revised_html_file",
                            "mimeType": "text/html",
                        },
                        "html": self._get_mock_html(f"Revised: {prompt[:30]}", prompt, version=2),
                    }
                ]
            }

        elif tool_name == "generate_variants":
            screen_id = arguments.get("screenId", "mock_screen_123")
            return {
                "screens": [
                    {
                        "name": f"projects/mock_project_999/screens/{screen_id}_var1",
                        "title": "Design Variant A (High Contrast)",
                        "html": self._get_mock_html("Variant A", "Variant A", version=1),
                    },
                    {
                        "name": f"projects/mock_project_999/screens/{screen_id}_var2",
                        "title": "Design Variant B (Minimalist)",
                        "html": self._get_mock_html("Variant B", "Variant B", version=1),
                    },
                ]
            }

        elif tool_name == "download_file":
            name = arguments.get("name", "")
            if "html" in name:
                ver = 2 if "revised" in name else 1
                return {
                    "html": self._get_mock_html("Stitch Generated Design", "Automated UI Prototype", version=ver)
                }
            else:
                # 1x1 transparent png mock base64
                mock_png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
                return {
                    "image": mock_png,
                    "image_metadata": {"mime_type": "image/png", "width": 1, "height": 1},
                }

        return {"status": "OK", "tool": tool_name}

    def _get_mock_html(self, title: str, prompt: str, version: int = 1) -> str:
        """Returns mock Stitch-quality Tailwind CSS HTML for tests."""
        badge_text = f"REVISED DESIGN PROTOTYPE v{version}" if version > 1 else "DESIGN PROTOTYPE v1"
        revision_banner = (
            f'<div class="revision-banner p-4 bg-slate-800/50 border-l-4 border-emerald-500 my-4 text-left">'
            f'<strong>Applied Revision:</strong> {prompt}</div>'
            if version > 1 else ''
        )
        return f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} (Prototype v{version})</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="style.css">
</head>
<body class="bg-[#050811] text-[#EAF7FF] font-sans min-h-screen">
  <header class="border-b border-[#1B2A47] bg-[#0A1020]/90 backdrop-blur px-8 py-4 flex justify-between items-center">
    <div class="text-xl font-bold tracking-wider text-[#00F5FF]">MIND // STITCH // {title[:20]}</div>
    <div class="prototype-badge text-xs bg-[#00F5FF]/10 text-[#00F5FF] border border-[#00F5FF]/40 px-3 py-1 rounded-full font-mono font-bold">
      {badge_text}
    </div>
  </header>
  <main class="max-w-6xl mx-auto px-6 py-12">
    <div class="text-center mb-12">
      <h1 class="text-4xl font-extrabold tracking-tight text-white mb-4">{title}</h1>
      {revision_banner}
      <p class="text-slate-400 max-w-2xl mx-auto text-base">{prompt}</p>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
      <div class="p-6 rounded-xl bg-[#101A2C] border border-[#1B2A47] hover:border-[#00F5FF] transition-colors">
        <h3 class="text-lg font-bold text-[#00F5FF] mb-2">Tailwind Styling</h3>
        <p class="text-sm text-slate-400">High-fidelity responsive components generated by Stitch.</p>
      </div>
      <div class="p-6 rounded-xl bg-[#101A2C] border border-[#1B2A47] hover:border-[#00F5FF] transition-colors">
        <h3 class="text-lg font-bold text-[#00F5FF] mb-2">Live Preview</h3>
        <p class="text-sm text-slate-400">Integrated directly into MIND's split visual workspace.</p>
      </div>
      <div class="p-6 rounded-xl bg-[#101A2C] border border-[#1B2A47] hover:border-[#00F5FF] transition-colors">
        <h3 class="text-lg font-bold text-[#00F5FF] mb-2">Approval Gate</h3>
        <p class="text-sm text-slate-400">Awaiting explicit confirmation before writing production code.</p>
      </div>
    </div>
  </main>
</body>
</html>"""
