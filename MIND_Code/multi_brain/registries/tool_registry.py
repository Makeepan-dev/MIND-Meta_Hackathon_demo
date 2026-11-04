"""Tool and Service Registry for MIND Multi-Brain Architecture."""

from __future__ import annotations

import ast
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from multi_brain.contracts import PermissionTier
from multi_brain.providers.local_document_provider import LocalDocumentProviderAdapter
from multi_brain.providers.local_media_provider import LocalMediaProviderAdapter
from multi_brain.security.gateway import ExecutionGateway

logger = logging.getLogger("mind.multi_brain.tool_registry")


@dataclass
class ToolDefinition:
    """Declared schema and execution metadata for a registered tool."""
    name: str
    description: str
    handler: Callable[[Dict[str, Any]], Any]
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    permission_tier: PermissionTier = PermissionTier.SAFE
    is_available: bool = True
    requires_network: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "permission_tier": self.permission_tier.value,
            "is_available": self.is_available,
            "requires_network": self.requires_network,
        }


class ToolRegistry:
    """Manages tool registration, discovery, and gateway-enforced execution."""

    def __init__(self, gateway: Optional[ExecutionGateway] = None) -> None:
        self.gateway = gateway or ExecutionGateway()
        self._tools: Dict[str, ToolDefinition] = {}
        self._media_provider = LocalMediaProviderAdapter()
        self._doc_provider = LocalDocumentProviderAdapter()
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Registers foundational tools for coding, verification, math, media, and workspace operations."""

        # 1. Deterministic Python Syntax Checker (SAFE)
        def _check_python_syntax(params: Dict[str, Any]) -> Dict[str, Any]:
            code = params.get("code", "")
            try:
                ast.parse(code)
                return {"valid": True, "error": None}
            except SyntaxError as e:
                return {"valid": False, "error": f"SyntaxError at line {e.lineno}: {e.msg}"}

        self.register(
            ToolDefinition(
                name="python_syntax_check",
                description="Performs deterministic AST parse validation of Python code.",
                handler=_check_python_syntax,
                input_schema={"code": "str"},
                output_schema={"valid": "bool", "error": "Optional[str]"},
                permission_tier=PermissionTier.SAFE,
                is_available=True,
            )
        )

        # 2. Math Calculator (SAFE)
        def _calculate(params: Dict[str, Any]) -> Dict[str, Any]:
            expression = params.get("expression", "")
            allowed_chars = set("0123456789+-*/()., %^")
            if not all(c in allowed_chars for c in expression):
                raise ValueError("Expression contains unauthorized characters.")
            safe_expr = expression.replace("^", "**")
            val = eval(safe_expr, {"__builtins__": {}}, {})
            return {"result": val}

        self.register(
            ToolDefinition(
                name="math_calculator",
                description="Performs safe mathematical calculations.",
                handler=_calculate,
                input_schema={"expression": "str"},
                output_schema={"result": "float|int"},
                permission_tier=PermissionTier.SAFE,
                is_available=True,
            )
        )

        # 3. Workspace File Reader (LOW_RISK)
        def _read_file(params: Dict[str, Any]) -> Dict[str, Any]:
            file_path = params.get("file_path", "")
            if not self.gateway.validate_path_safety(file_path):
                raise PermissionError(f"Access to path '{file_path}' is outside workspace boundaries.")
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return {"content": content, "size_bytes": len(content)}

        self.register(
            ToolDefinition(
                name="workspace_file_read",
                description="Reads a file within the designated workspace.",
                handler=_read_file,
                input_schema={"file_path": "str"},
                output_schema={"content": "str", "size_bytes": "int"},
                permission_tier=PermissionTier.LOW_RISK,
                is_available=True,
            )
        )

        # 4. Workspace File Writer (REQUIRES_APPROVAL)
        def _write_file(params: Dict[str, Any]) -> Dict[str, Any]:
            file_path = params.get("file_path", "")
            content = params.get("content", "")
            if not self.gateway.validate_path_safety(file_path):
                raise PermissionError(f"Access to path '{file_path}' is outside workspace boundaries.")
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return {"written": True, "path": file_path, "bytes": len(content)}

        self.register(
            ToolDefinition(
                name="workspace_file_write",
                description="Writes text or code content to a file inside the workspace. Requires approval.",
                handler=_write_file,
                input_schema={"file_path": "str", "content": "str"},
                output_schema={"written": "bool", "path": "str"},
                permission_tier=PermissionTier.REQUIRES_APPROVAL,
                is_available=True,
            )
        )

        # 5. Repository Inspector (LOW_RISK)
        def _repo_inspect(params: Dict[str, Any]) -> Dict[str, Any]:
            target_dir = params.get("directory", self.gateway.workspace_root)
            if not self.gateway.validate_path_safety(target_dir):
                raise PermissionError("Path outside workspace.")
            items = []
            for root, dirs, files in os.walk(target_dir):
                # Skip heavy caches
                dirs[:] = [d for d in dirs if d not in (".git", "venv", "__pycache__", "node_modules")]
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, self.gateway.workspace_root)
                    items.append({"file": rel, "size": os.path.getsize(full)})
                if len(items) > 50:  # Bound inspection
                    break
            return {"total_files_scanned": len(items), "sample_files": items[:20]}

        self.register(
            ToolDefinition(
                name="repo_inspect",
                description="Safely inspects file structure and contents within workspace boundary.",
                handler=_repo_inspect,
                input_schema={"directory": "Optional[str]"},
                output_schema={"total_files_scanned": "int", "sample_files": "list"},
                permission_tier=PermissionTier.LOW_RISK,
                is_available=True,
            )
        )

        # 6. Test Runner (REQUIRES_APPROVAL)
        def _run_test(params: Dict[str, Any]) -> Dict[str, Any]:
            test_file = params.get("test_file", "")
            if not self.gateway.validate_path_safety(test_file):
                raise PermissionError(f"Test file '{test_file}' outside workspace.")
            # Run pytest in isolated subprocess using current interpreter
            cmd = [sys.executable, "-m", "pytest", test_file, "-q"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30.0)
            return {
                "exit_code": res.returncode,
                "passed": res.returncode == 0,
                "stdout": res.stdout[:2000],
                "stderr": res.stderr[:1000],
            }

        self.register(
            ToolDefinition(
                name="test_runner",
                description="Executes a pytest test file within workspace boundary.",
                handler=_run_test,
                input_schema={"test_file": "str"},
                output_schema={"passed": "bool", "exit_code": "int", "stdout": "str"},
                permission_tier=PermissionTier.REQUIRES_APPROVAL,
                is_available=True,
            )
        )

        # 7. Document Reader Tool (LOW_RISK)
        def _read_document(params: Dict[str, Any]) -> Dict[str, Any]:
            file_path = params.get("file_path", "")
            if not self.gateway.validate_path_safety(file_path):
                raise PermissionError(f"Document '{file_path}' outside workspace.")
            prepared = self._doc_provider.prepare_input(params)
            return self._doc_provider.execute(prepared)

        self.register(
            ToolDefinition(
                name="document_read",
                description="Reads and extracts text from PDF, DOCX, and text files.",
                handler=_read_document,
                input_schema={"file_path": "str", "max_chars": "Optional[int]"},
                output_schema={"extracted_text": "str", "char_count": "int"},
                permission_tier=PermissionTier.LOW_RISK,
                is_available=True,
            )
        )

        # 8. Local 2D Image Generator (LOW_RISK)
        def _render_image(params: Dict[str, Any]) -> Dict[str, Any]:
            prepared = self._media_provider.prepare_input({**params, "media_type": "image"})
            return self._media_provider.execute(prepared)

        self.register(
            ToolDefinition(
                name="render_local_image",
                description="Renders a valid 2D image (PNG/JPG) using local Pillow engine.",
                handler=_render_image,
                input_schema={"prompt": "str", "width": "Optional[int]", "height": "Optional[int]"},
                output_schema={"artifact": "dict", "file_path": "str", "dimensions": "str"},
                permission_tier=PermissionTier.LOW_RISK,
                is_available=True,
            )
        )

        # 9. Local 3D Mesh Generator (LOW_RISK)
        def _render_3d_mesh(params: Dict[str, Any]) -> Dict[str, Any]:
            prepared = self._media_provider.prepare_input({**params, "media_type": "3d"})
            return self._media_provider.execute(prepared)

        self.register(
            ToolDefinition(
                name="generate_3d_obj",
                description="Generates a valid 3D Wavefront OBJ mesh file locally.",
                handler=_render_3d_mesh,
                input_schema={"prompt": "str", "mesh_type": "Optional[str]"},
                output_schema={"artifact": "dict", "file_path": "str", "vertex_count": "int", "face_count": "int"},
                permission_tier=PermissionTier.LOW_RISK,
                is_available=True,
            )
        )

        # 10. Cloud Image Generator Hook (Reports unconfigured honestly)
        def _image_generator(params: Dict[str, Any]) -> Dict[str, Any]:
            stability_key = os.getenv("STABILITY_API_KEY")
            openai_key = os.getenv("OPENAI_API_KEY")
            if not stability_key and not openai_key:
                raise RuntimeError(
                    "No image-generation provider is configured. "
                    "Configure STABILITY_API_KEY or OPENAI_API_KEY to enable cloud rendering."
                )
            return {"generated": False, "message": "Provider key present but cloud API call requires explicit approval."}

        has_image_provider = bool(os.getenv("STABILITY_API_KEY") or os.getenv("OPENAI_API_KEY"))
        self.register(
            ToolDefinition(
                name="image_generator",
                description="Generates visual assets via configured cloud image backend.",
                handler=_image_generator,
                input_schema={"prompt": "str"},
                output_schema={"image_url": "str"},
                permission_tier=PermissionTier.REQUIRES_APPROVAL,
                is_available=has_image_provider,
                requires_network=True,
            )
        )

    def register(self, tool: ToolDefinition, allow_overwrite: bool = True) -> None:
        if not tool.name or not tool.name.strip():
            raise ValueError("Tool name cannot be empty.")
        if tool.name in self._tools and not allow_overwrite:
            raise ValueError(f"Tool '{tool.name}' is already registered.")
        self._tools[tool.name] = tool

    def unregister(self, tool_name: str) -> bool:
        if tool_name in self._tools:
            del self._tools[tool_name]
            return True
        return False

    def get(self, tool_name: str) -> Optional[ToolDefinition]:
        return self._tools.get(tool_name)

    def list_all(self, only_available: bool = False) -> List[Dict[str, Any]]:
        results = []
        for t in self._tools.values():
            if not only_available or t.is_available:
                results.append(t.to_dict())
        return results

    def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        requester: str = "orchestrator",
        bypass_approval_for_tests: bool = False,
    ) -> Any:
        tool = self.get(tool_name)
        if not tool:
            raise KeyError(f"Tool '{tool_name}' is not registered.")

        if not tool.is_available:
            raise RuntimeError(f"Tool '{tool_name}' is currently unavailable.")

        def _action() -> Any:
            return tool.handler(parameters)

        return self.gateway.authorize_and_execute(
            requester=requester,
            action_name=f"tool:{tool.name}",
            permission_tier=tool.permission_tier,
            func=_action,
            details=parameters,
            bypass_approval_for_tests=bypass_approval_for_tests,
        )
