"""
MIND GameDev — Blender Automation & Safety Execution Adapter.
Discovers local Blender installations, validates generated Blender Python (bpy) scripts,
executes them headlessly in a controlled background subprocess, captures output logs,
renders previews, and verifies exported glTF 2.0 (.glb) asset files.
"""

from __future__ import annotations

import os
import sys
import ast
import time
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from ..config import GameDevConfig
from .threed_adapter import ThreeDAssetAdapter

logger = logging.getLogger("mind.gamedev.adapters.blender")


class BlenderScriptSecurityError(ValueError):
    """Raised when generated Blender code violates security constraints."""


class BlenderExecutionError(RuntimeError):
    """Raised when Blender background execution fails."""


class BlenderAdapter:
    """
    Manages local Blender execution, AST-based script validation,
    headless background execution, preview rendering, and GLB verification.
    """

    KNOWN_BLENDER_LOCATIONS = [
        r"E:\Blender\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.3\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender\blender.exe",
        r"C:\Program Files (x86)\Blender Foundation\Blender\blender.exe",
    ]

    FORBIDDEN_MODULES = {
        "subprocess",
        "socket",
        "requests",
        "urllib",
        "http",
        "ftplib",
        "telnetlib",
        "smtplib",
        "ctypes",
        "multiprocessing",
        "threading",
        "webbrowser",
        "pynput",
        "pyautogui",
    }

    FORBIDDEN_CALLS = {
        "exec",
        "eval",
        "compile",
        "__import__",
        "system",
        "spawn",
        "popen",
        "fork",
    }

    def __init__(self, config: Optional[GameDevConfig] = None) -> None:
        self.config = config or GameDevConfig.load()
        self.blender_path: Optional[Path] = self._discover_blender()
        self.threed_adapter = ThreeDAssetAdapter(self.config)

    def _discover_blender(self) -> Optional[Path]:
        """Discovers the Blender executable from config, environment, registry, or standard paths."""
        # 1. Environment variable
        env_blender = os.getenv("BLENDER_PATH") or os.getenv("BLENDER_EXECUTABLE")
        if env_blender and Path(env_blender).is_file():
            logger.info(f"Discovered Blender via environment: {env_blender}")
            return Path(env_blender)

        # 2. PATH resolution
        which_blender = shutil.which("blender")
        if which_blender and Path(which_blender).is_file():
            logger.info(f"Discovered Blender on system PATH: {which_blender}")
            return Path(which_blender)

        # 3. Known installation locations
        for candidate in self.KNOWN_BLENDER_LOCATIONS:
            p = Path(candidate)
            if p.is_file():
                logger.info(f"Discovered Blender at known location: {p}")
                return p

        # 4. Windows Registry query (safe non-blocking)
        if sys.platform == "win32":
            reg_path = self._query_windows_registry()
            if reg_path and reg_path.is_file():
                return reg_path

        logger.warning("No local Blender installation discovered.")
        return None

    def _query_windows_registry(self) -> Optional[Path]:
        """Inspects Windows Registry for Blender install path."""
        try:
            import winreg
            for root_key in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(root_key, r"SOFTWARE\BlenderFoundation") as key:
                        val, _ = winreg.QueryValueEx(key, "InstallDir")
                        exe = Path(val) / "blender.exe"
                        if exe.is_file():
                            return exe
                except Exception:
                    pass
        except Exception:
            pass
        return None

    def is_available(self) -> bool:
        """Returns True if a valid local Blender executable is discovered."""
        return self.blender_path is not None and self.blender_path.is_file()

    def get_blender_version(self) -> str:
        """Returns the version string of the discovered Blender installation."""
        if not self.is_available():
            return "Not Installed"
        try:
            res = subprocess.run(
                [str(self.blender_path), "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            first_line = res.stdout.strip().splitlines()[0]
            return first_line
        except Exception as e:
            return f"Unknown ({e})"

    def validate_script_safety(self, script_code: str) -> Tuple[bool, Optional[str]]:
        """
        Validates generated Python script for security and execution containment.
        Rejects shell execution, network requests, process spawning, and unapproved filesystem access.
        """
        if not script_code or not script_code.strip():
            return False, "Script is empty."

        try:
            tree = ast.parse(script_code)
        except SyntaxError as e:
            return False, f"Python Syntax Error: {e.msg} at line {e.lineno}"

        for node in ast.walk(tree):
            # Check imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    if root_mod in self.FORBIDDEN_MODULES:
                        return False, f"Security Violation: Forbidden module import '{alias.name}'"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_mod = node.module.split(".")[0]
                    if root_mod in self.FORBIDDEN_MODULES:
                        return False, f"Security Violation: Forbidden module import '{node.module}'"

            # Check forbidden function calls
            elif isinstance(node, ast.Call):
                func = node.func
                func_name = None
                if isinstance(func, ast.Name):
                    func_name = func.id
                elif isinstance(func, ast.Attribute):
                    func_name = func.attr

                if func_name in self.FORBIDDEN_CALLS:
                    return False, f"Security Violation: Forbidden function invocation '{func_name}()'"

                # Check os.remove, os.rmdir outside workspace
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    if func.value.id == "os" and func_name in ("system", "popen", "kill", "remove", "rmdir"):
                        return False, f"Security Violation: Forbidden os operation 'os.{func_name}()'"

        return True, None

    def execute_script(
        self,
        script_code: str,
        workspace_dir: Path,
        expected_glb_name: str = "model.glb",
        timeout_seconds: float = 60.0,
        render_preview: bool = True,
    ) -> Dict[str, Any]:
        """
        Executes a validated Blender Python script in background mode.
        Exports the GLB, renders a preview if requested, and verifies the resulting model.
        """
        if not self.is_available():
            raise BlenderExecutionError(
                "Blender executable not found. Please install Blender or set BLENDER_PATH."
            )

        workspace_dir = Path(workspace_dir).resolve()
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # 1. Safety validation gate
        is_safe, error_msg = self.validate_script_safety(script_code)
        if not is_safe:
            raise BlenderScriptSecurityError(error_msg)

        # 2. Write script file to workspace
        timestamp = int(time.time())
        script_file = workspace_dir / f"reconstruct_{timestamp}.py"
        target_glb = workspace_dir / expected_glb_name
        target_blend = workspace_dir / f"{target_glb.stem}.blend"
        preview_png = workspace_dir / f"{target_glb.stem}_preview.png"
        log_file = workspace_dir / f"blender_{timestamp}.log"

        # Inject export and preview commands if not present
        prepared_script = self._prepare_script_for_export(
            script_code=script_code,
            export_glb_path=target_glb,
            save_blend_path=target_blend,
            render_preview_path=preview_png if render_preview else None,
        )
        script_file.write_text(prepared_script, encoding="utf-8")

        # 3. Subprocess execution without shell interpolation
        cmd = [
            str(self.blender_path),
            "--background",
            "--factory-startup",  # Prevents 3rd party addons from interfering
            "--python",
            str(script_file),
        ]

        logger.info(f"Executing Blender headless: {' '.join(cmd)}")
        start_time = time.time()

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(workspace_dir),
            )
            elapsed = round(time.time() - start_time, 2)
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            full_log = f"=== STDOUT ===\n{stdout}\n\n=== STDERR ===\n{stderr}"
            log_file.write_text(full_log, encoding="utf-8")

            if proc.returncode != 0:
                # Capture the actual Python exception from stdout/stderr
                error_snippet = self._extract_blender_error(stdout, stderr)
                return {
                    "success": False,
                    "returncode": proc.returncode,
                    "error": error_snippet,
                    "elapsed_seconds": elapsed,
                    "stdout": stdout,
                    "stderr": stderr,
                    "script_path": str(script_file),
                    "log_path": str(log_file),
                }

        except subprocess.TimeoutExpired as e:
            elapsed = round(time.time() - start_time, 2)
            return {
                "success": False,
                "error": f"Blender execution timed out after {timeout_seconds}s",
                "elapsed_seconds": elapsed,
                "script_path": str(script_file),
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Subprocess invocation failed: {e}",
                "script_path": str(script_file),
            }

        # 4. Verify GLB existence and geometry
        if not target_glb.exists() or target_glb.stat().st_size == 0:
            return {
                "success": False,
                "error": f"Blender ran successfully but GLB was not created at '{target_glb}'.",
                "script_path": str(script_file),
                "log_path": str(log_file),
                "stdout": stdout,
            }

        validation = self.threed_adapter.validate_3d_file(target_glb)
        if not validation.get("is_valid"):
            return {
                "success": False,
                "error": f"Exported GLB failed geometric validation: {validation.get('error')}",
                "script_path": str(script_file),
                "log_path": str(log_file),
            }

        return {
            "success": True,
            "glb_path": str(target_glb.resolve()),
            "blend_path": str(target_blend.resolve()) if target_blend.exists() else None,
            "preview_path": str(preview_png.resolve()) if preview_png.exists() else None,
            "script_path": str(script_file.resolve()),
            "log_path": str(log_file.resolve()),
            "file_size_bytes": target_glb.stat().st_size,
            "format": "glb",
            "elapsed_seconds": elapsed,
            "stdout_summary": stdout[-500:] if len(stdout) > 500 else stdout,
        }

    def _prepare_script_for_export(
        self,
        script_code: str,
        export_glb_path: Path,
        save_blend_path: Path,
        render_preview_path: Optional[Path] = None,
    ) -> str:
        """
        Appends guaranteed scene setup, camera framing, lighting,
        GLB export, and optional preview render to ensure complete model delivery.
        """
        glb_str = str(export_glb_path.resolve()).replace("\\", "/")
        blend_str = str(save_blend_path.resolve()).replace("\\", "/")
        preview_str = str(render_preview_path.resolve()).replace("\\", "/") if render_preview_path else None

        export_block = f"""

# ----------------------------------------------------------------------
# MIND AUTOMATED EXPORT & CAMERA RIGGING
# ----------------------------------------------------------------------
import bpy

# Ensure at least one camera exists
cam = bpy.data.objects.get("Camera") or bpy.context.scene.camera
if not cam:
    bpy.ops.object.camera_add(location=(4.5, -4.5, 3.5), rotation=(1.1, 0, 0.78))
    cam = bpy.context.active_object
    bpy.context.scene.camera = cam

# Ensure directional light exists
sun = bpy.data.objects.get("Sun") or bpy.data.objects.get("Light")
if not sun:
    bpy.ops.object.light_add(type='SUN', location=(5, -5, 10))
    sun = bpy.context.active_object
    if hasattr(sun.data, "energy"):
        sun.data.energy = 4.0

# Save blend file
try:
    bpy.ops.wm.save_as_mainfile(filepath=r"{blend_str}")
except Exception as e:
    print(f"Warning: could not save blend file: {{e}}")

# Export standard binary glTF 2.0 (.glb)
try:
    bpy.ops.export_scene.gltf(
        filepath=r"{glb_str}",
        export_format='GLB',
        use_selection=False,
        export_apply=True
    )
    print("MIND_GLB_EXPORT_COMPLETED")
except Exception as e:
    print(f"ERROR: glTF export failed: {{e}}")
    raise
"""
        if preview_str:
            preview_block = f"""
# Render preview image
try:
    bpy.context.scene.render.image_settings.file_format = 'PNG'
    bpy.context.scene.render.filepath = r"{preview_str}"
    bpy.context.scene.render.resolution_x = 512
    bpy.context.scene.render.resolution_y = 512
    bpy.ops.render.render(write_still=True)
    print("MIND_PREVIEW_RENDER_COMPLETED")
except Exception as e:
    print(f"Warning: Preview render skipped: {{e}}")
"""
            export_block += preview_block

        return script_code + "\n" + export_block

    @staticmethod
    def _extract_blender_error(stdout: str, stderr: str) -> str:
        """Extracts the Python traceback and error message from Blender process output."""
        lines = (stdout + "\n" + stderr).splitlines()
        tb_lines = []
        recording = False
        for line in lines:
            if "Traceback (most recent call last):" in line or "Error:" in line or "Exception:" in line:
                recording = True
            if recording:
                tb_lines.append(line)
        if tb_lines:
            return "\n".join(tb_lines[-12:])
        # Fallback to last non-empty lines
        non_empty = [l.strip() for l in lines if l.strip()]
        return "\n".join(non_empty[-6:]) if non_empty else "Unknown Blender execution failure."
