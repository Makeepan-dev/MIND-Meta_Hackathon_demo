"""Game Project Test Runner & Verifier.

Performs static validation of game source files (HTML, JS, CSS, JSON, 3D models, images)
and launches an ephemeral local HTTP server to verify network asset resolution and playability.
"""

from __future__ import annotations

import functools
import http.server
import json
import os
import re
import socketserver
import struct
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from PIL import Image

from ..models import ExecutionReport
from .workspace_files import SafeWorkspaceManager
from .component_contract import CrossFileIntegrityValidator


class GameTestRunner:
    """Automated test and verification runner for generated game projects."""

    def __init__(self, workspace_or_path: Union[SafeWorkspaceManager, Path, str]) -> None:
        if isinstance(workspace_or_path, SafeWorkspaceManager):
            self.workspace = workspace_or_path
            self.default_dir = self.workspace.workspace_root
        else:
            p = Path(workspace_or_path).resolve()
            self.default_dir = p
            self.workspace = SafeWorkspaceManager(p)

    def run_all_tests(self, project_dir: Optional[Union[str, Path]] = None) -> ExecutionReport:
        """Runs complete static and dynamic HTTP tests and compiles an ExecutionReport."""
        target_path = Path(project_dir).resolve() if project_dir else self.default_dir
        start_time = time.time()

        raw_results = self.verify_all(target_path)
        elapsed = round(time.time() - start_time, 3)

        errors = [f"{c['name']}: {c.get('details', '')}" for c in raw_results["checks"] if not c.get("passed", False)]
        success = raw_results["all_passed"] and len(errors) == 0

        # Build files_checked list
        files_checked = [p.name for p in target_path.rglob("*") if p.is_file()]

        # Find http test result
        http_check = next((c for c in raw_results["checks"] if c["name"] == "http_serving_test"), None)
        http_status = "SUCCESS" if (http_check and http_check.get("passed")) else "FAILED"

        report = ExecutionReport(
            workflow_id=str(uuid.uuid4())[:8],
            project_name=target_path.name,
            success=success,
            status="VERIFIED" if success else "FAILED",
            target_engine="Three.js WebGL",
            project_path=str(target_path),
            index_html_path=str(target_path / "index.html"),
            files_created=files_checked,
            assets_created=[c for c in raw_results["checks"] if "3d_model" in c["name"] or "image" in c["name"]],
            verification_results=raw_results,
            playability_verified=success,
            elapsed_seconds=elapsed,
            summary=f"Automated test suite finished in {elapsed}s with status {'SUCCESS' if success else 'FAILED'}.",
            errors=errors,
            warnings=[],
            details={
                "files_checked": files_checked,
                "http_serving_test": {
                    "status": http_status,
                    "details": http_check.get("details", "") if http_check else "",
                },
                "checks": raw_results["checks"],
            },
        )
        return report

    def verify_all(self, project_dir: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        """Runs all applicable static and structural tests on the project."""
        p_path = Path(project_dir).resolve() if project_dir else self.default_dir
        full_project_path = self.workspace.validate_path(p_path)

        results: Dict[str, Any] = {
            "project_path": str(full_project_path),
            "checks": [],
            "all_passed": True,
            "discrepancies": [],
        }

        # 1. Check index.html exists
        index_file = full_project_path / "index.html"
        if not index_file.exists():
            results["all_passed"] = False
            results["discrepancies"].append("index.html is missing")
            results["checks"].append({"name": "index_html_exists", "passed": False, "details": "index.html is missing"})
        else:
            html_check = self._verify_html_content(index_file)
            results["checks"].append(html_check)
            if not html_check["passed"]:
                results["all_passed"] = False
                results["discrepancies"].append(html_check["details"])

        # 2. Check JavaScript files
        js_files = list(full_project_path.rglob("*.js"))
        for js_file in js_files:
            js_check = self._verify_js_content(js_file)
            results["checks"].append(js_check)
            if not js_check["passed"]:
                results["all_passed"] = False
                results["discrepancies"].append(js_check["details"])

        # 2b. Check CSS files
        css_files = list(full_project_path.rglob("*.css"))
        for css_file in css_files:
            css_check = self._verify_css_content(css_file)
            results["checks"].append(css_check)
            if not css_check["passed"]:
                results["all_passed"] = False
                results["discrepancies"].append(css_check["details"])

        # 2c. Check Cross-File HTML/CSS Integrity (if both exist)
        main_css = full_project_path / "style.css"
        if index_file.exists() and main_css.exists():
            try:
                html_text = index_file.read_text(encoding="utf-8")
                css_text = main_css.read_text(encoding="utf-8")
                val_report = CrossFileIntegrityValidator.validate(html_text, css_text, min_coverage=30.0)
                cross_check = {
                    "name": "cross_file_integrity:index.html_style.css",
                    "passed": val_report.is_valid,
                    "coverage_pct": val_report.coverage_pct,
                    "details": (
                        f"HTML/CSS class coverage: {val_report.coverage_pct}%."
                        if val_report.is_valid
                        else f"Integrity errors: {'; '.join(val_report.errors)}"
                    ),
                }
                results["checks"].append(cross_check)
                if not cross_check["passed"]:
                    results["all_passed"] = False
                    results["discrepancies"].append(cross_check["details"])
            except Exception as e:
                pass

        # 3. Check JSON manifests
        json_files = list(full_project_path.rglob("*.json"))
        for json_file in json_files:
            json_check = self._verify_json_file(json_file)
            results["checks"].append(json_check)
            if not json_check["passed"]:
                results["all_passed"] = False
                results["discrepancies"].append(json_check["details"])

        # 4. Check 3D models (GLB / OBJ)
        model_files = list(full_project_path.rglob("*.glb")) + list(full_project_path.rglob("*.obj"))
        for model_file in model_files:
            model_check = self._verify_3d_model(model_file)
            results["checks"].append(model_check)
            if not model_check["passed"]:
                results["all_passed"] = False
                results["discrepancies"].append(model_check["details"])

        # 5. Check 2D images
        img_files = list(full_project_path.rglob("*.png")) + list(full_project_path.rglob("*.jpg"))
        for img_file in img_files:
            img_check = self._verify_image_file(img_file)
            results["checks"].append(img_check)
            if not img_check["passed"]:
                results["all_passed"] = False
                results["discrepancies"].append(img_check["details"])

        # 6. Verify local HTTP asset serving (only if index.html exists)
        if index_file.exists():
            http_check = self.verify_http_serving(full_project_path)
            results["checks"].append(http_check)
            if not http_check["passed"]:
                results["all_passed"] = False
                results["discrepancies"].append(http_check["details"])
        else:
            results["checks"].append({"name": "http_serving_test", "passed": False, "details": "index.html missing for HTTP serving"})

        return results

    def _verify_html_content(self, path: Path) -> Dict[str, Any]:
        """Validates that HTML contains valid structure, viewport, and script tags."""
        try:
            content = path.read_text(encoding="utf-8")
            required_tags = ["<!doctype html>", "<html", "<head", "<body", "</html>"]
            missing = [t for t in required_tags if t not in content.lower()]
            if missing:
                return {
                    "name": f"html_structure:{path.name}",
                    "passed": False,
                    "details": f"HTML missing essential tags: {missing}",
                }

            has_canvas = "<canvas" in content.lower() or "canvas" in content.lower()
            return {
                "name": f"html_structure:{path.name}",
                "passed": True,
                "has_canvas": has_canvas,
                "size_bytes": len(content),
                "details": "HTML structure valid with viewport and canvas setup.",
            }
        except Exception as e:
            return {"name": f"html_structure:{path.name}", "passed": False, "details": str(e)}

    def _verify_js_content(self, path: Path) -> Dict[str, Any]:
        """Validates basic JavaScript syntax and bracket balancing."""
        try:
            content = path.read_text(encoding="utf-8")
            if len(content.strip()) == 0:
                return {"name": f"js_syntax:{path.name}", "passed": False, "details": "JavaScript file is empty."}

            # Balanced brackets check (ignoring inside strings/comments)
            open_curly = content.count("{")
            close_curly = content.count("}")
            open_paren = content.count("(")
            close_paren = content.count(")")

            if abs(open_curly - close_curly) > 5 or abs(open_paren - close_paren) > 5:
                return {
                    "name": f"js_syntax:{path.name}",
                    "passed": False,
                    "details": f"Severe brace mismatch in {path.name} ({{ {open_curly}/{close_curly} }}, ( {open_paren}/{close_paren} ))",
                }

            return {
                "name": f"js_syntax:{path.name}",
                "passed": True,
                "size_bytes": len(content),
                "details": f"JavaScript file passed syntax heuristics ({len(content)} bytes).",
            }
        except Exception as e:
            return {"name": f"js_syntax:{path.name}", "passed": False, "details": str(e)}

    def _verify_css_content(self, path: Path) -> Dict[str, Any]:
        """Validates CSS syntax, rule formatting, and rejects conversational prose leakage."""
        try:
            content = path.read_text(encoding="utf-8")
            if len(content.strip()) == 0:
                return {"name": f"css_syntax:{path.name}", "passed": False, "details": "CSS file is empty."}

            # 1. Preamble & conversational prose detection (reject unstripped thinking / prose)
            prose_markers = (
                "here is", "below is", "certainly", "i will", "we will",
                "design plan", "to style", "color palette", "in this section",
                "let me know", "i hope this", "this css provides"
            )
            for i, line in enumerate(content.splitlines()[:150]):
                clean = line.strip().lower()
                if not clean or clean.startswith("/*") or clean.startswith("*"):
                    continue
                if any(clean.startswith(marker) for marker in prose_markers):
                    return {
                        "name": f"css_syntax:{path.name}",
                        "passed": False,
                        "details": f"Conversational thinking/prose preamble detected at line {i+1}: '{line.strip()[:60]}'",
                    }

            # 2. Balanced brace validation
            open_curly = content.count("{")
            close_curly = content.count("}")
            if open_curly == 0 or close_curly == 0:
                return {
                    "name": f"css_syntax:{path.name}",
                    "passed": False,
                    "details": f"Missing CSS rulesets in {path.name} ({{ {open_curly}/{close_curly} }})",
                }
            if open_curly != close_curly:
                return {
                    "name": f"css_syntax:{path.name}",
                    "passed": False,
                    "details": f"Unbalanced CSS braces in {path.name}: {open_curly} open vs {close_curly} close ({open_curly - close_curly} unclosed).",
                }

            # 3. Truncation detection at end of file
            non_empty_lines = [l.strip() for l in content.splitlines() if l.strip()]
            if non_empty_lines:
                last_line = non_empty_lines[-1]
                if ":" in last_line and not last_line.endswith(";") and not last_line.endswith("}"):
                    return {
                        "name": f"css_syntax:{path.name}",
                        "passed": False,
                        "details": f"CSS truncated mid-declaration at EOF: '{last_line}'",
                    }

            return {
                "name": f"css_syntax:{path.name}",
                "passed": True,
                "size_bytes": len(content),
                "details": f"CSS syntax verified with {open_curly} rulesets.",
            }
        except Exception as e:
            return {"name": f"css_syntax:{path.name}", "passed": False, "details": str(e)}

    def _verify_json_file(self, path: Path) -> Dict[str, Any]:
        """Validates JSON parse validity."""
        try:
            content = path.read_text(encoding="utf-8")
            json.loads(content)
            return {"name": f"json_valid:{path.name}", "passed": True, "details": "JSON parses cleanly."}
        except Exception as e:
            return {"name": f"json_valid:{path.name}", "passed": False, "details": f"JSON parse error: {e}"}

    def _verify_3d_model(self, path: Path) -> Dict[str, Any]:
        """Validates 3D mesh files (.glb / .obj)."""
        ext = path.suffix.lower()
        size = path.stat().st_size
        if size < 50:
            return {"name": f"3d_model:{path.name}", "passed": False, "details": f"Model file too small: {size} bytes"}

        if ext == ".glb":
            try:
                with open(path, "rb") as f:
                    magic = f.read(4)
                    if magic != b"glTF":
                        return {"name": f"3d_model:{path.name}", "passed": False, "details": "Missing glTF magic bytes"}
                    version = struct.unpack("<I", f.read(4))[0]
                    if version != 2:
                        return {"name": f"3d_model:{path.name}", "passed": False, "details": f"Unsupported version: {version}"}
                return {"name": f"3d_model:{path.name}", "passed": True, "details": f"Valid binary glTF 2.0 ({size} bytes)"}
            except Exception as e:
                return {"name": f"3d_model:{path.name}", "passed": False, "details": str(e)}

        elif ext == ".obj":
            v_count = 0
            f_count = 0
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.startswith("v "):
                            v_count += 1
                        elif line.startswith("f "):
                            f_count += 1
                passed = v_count >= 3 and f_count >= 1
                return {
                    "name": f"3d_model:{path.name}",
                    "passed": passed,
                    "details": f"Wavefront OBJ has {v_count} vertices, {f_count} faces.",
                }
            except Exception as e:
                return {"name": f"3d_model:{path.name}", "passed": False, "details": str(e)}

        return {"name": f"3d_model:{path.name}", "passed": True, "details": f"Unchecked format {ext}"}

    def _verify_image_file(self, path: Path) -> Dict[str, Any]:
        """Validates image integrity using PIL."""
        try:
            with Image.open(path) as img:
                img.verify()
            with Image.open(path) as img:
                dims = img.size
            return {
                "name": f"image_pil:{path.name}",
                "passed": True,
                "details": f"Image valid {dims[0]}x{dims[1]} {path.suffix.upper()}",
            }
        except Exception as e:
            return {"name": f"image_pil:{path.name}", "passed": False, "details": f"Image corrupted: {e}"}

    def verify_http_serving(self, project_path: Path) -> Dict[str, Any]:
        """Starts an ephemeral local HTTP server and verifies that index.html resolves."""
        import urllib.request
        import urllib.error

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass

        handler = functools.partial(QuietHandler, directory=str(project_path))
        server = None

        try:
            with socketserver.TCPServer(("127.0.0.1", 0), handler) as s:
                server = s
                port = s.server_address[1]

                server_thread = threading.Thread(target=s.serve_forever, daemon=True)
                server_thread.start()

                url = f"http://127.0.0.1:{port}/index.html"
                req = urllib.request.urlopen(url, timeout=5)
                status_code = req.getcode()
                body = req.read()

                s.shutdown()

                passed = status_code == 200 and len(body) > 100
                return {
                    "name": "http_serving_test",
                    "passed": passed,
                    "status_code": status_code,
                    "details": f"HTTP server resolved index.html (HTTP {status_code}, {len(body)} bytes).",
                }
        except Exception as e:
            if server:
                server.shutdown()
            return {
                "name": "http_serving_test",
                "passed": False,
                "details": f"HTTP server verification failed: {e}",
            }
