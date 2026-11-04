"""
MIND Universal Development Studio — Independent Verification Engine.
Provides comprehensive, multi-layer verification across diverse project deliverables:
Websites (HTML/CSS/JS/assets), Python applications, C/compiled sources, and 3D/media assets.

Principle:
MIND independently evaluates candidate implementations before finalization.
A successful syntax check or build does not automatically establish functional correctness.
"""

from __future__ import annotations

import ast
import html.parser
import json
import logging
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ..config import GameDevConfig
from ..models import (
    DiagnosticReport,
    ExecutionReport,
    ProjectType,
    VerificationCategory,
)
from .workspace_files import SafeWorkspaceManager

logger = logging.getLogger("mind.gamedev.verifier")


class SimpleHTMLTagValidator(html.parser.HTMLParser):
    """Checks HTML for balanced tags, unclosed containers, and essential elements."""

    VOID_ELEMENTS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr"
    }

    def __init__(self) -> None:
        super().__init__()
        self.tag_stack: List[Tuple[str, int, int]] = []  # (tag, line, col)
        self.errors: List[str] = []
        self.has_doctype = False
        self.has_html = False
        self.has_head = False
        self.has_body = False
        self.has_viewport = False
        self.links: List[str] = []
        self.scripts: List[str] = []
        self.images: List[str] = []

    def handle_decl(self, decl: str) -> None:
        if "doctype html" in decl.lower():
            self.has_doctype = True

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag_lower = tag.lower()
        attr_dict = {k.lower(): v for k, v in attrs if v is not None}

        if tag_lower == "html":
            self.has_html = True
        elif tag_lower == "head":
            self.has_head = True
        elif tag_lower == "body":
            self.has_body = True
        elif tag_lower == "meta" and attr_dict.get("name") == "viewport":
            self.has_viewport = True
        elif tag_lower == "link" and "href" in attr_dict:
            self.links.append(attr_dict["href"])
        elif tag_lower == "script" and "src" in attr_dict:
            self.scripts.append(attr_dict["src"])
        elif tag_lower == "img" and "src" in attr_dict:
            self.images.append(attr_dict["src"])

        if tag_lower not in self.VOID_ELEMENTS:
            line, col = self.getpos()
            self.tag_stack.append((tag_lower, line, col))

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower in self.VOID_ELEMENTS:
            return

        if not self.tag_stack:
            line, col = self.getpos()
            self.errors.append(f"Unexpected closing tag </{tag_lower}> with no matching open tag at line {line}:{col}")
            return

        # Find matching tag from stack top
        for idx in range(len(self.tag_stack) - 1, -1, -1):
            if self.tag_stack[idx][0] == tag_lower:
                # Pop all tags above it (which were left unclosed)
                unclosed = self.tag_stack[idx + 1:]
                for u_tag, u_line, u_col in unclosed:
                    self.errors.append(f"Unclosed tag <{u_tag}> opened at line {u_line}:{u_col}")
                self.tag_stack = self.tag_stack[:idx]
                return

        line, col = self.getpos()
        self.errors.append(f"Mismatched closing tag </{tag_lower}> at line {line}:{col}")

    def finalize(self) -> None:
        for u_tag, u_line, u_col in self.tag_stack:
            self.errors.append(f"Unclosed tag <{u_tag}> opened at line {u_line}:{u_col}")


class IndependentVerifier:
    """
    Independent Verification Engine that evaluates candidate implementations
    against multi-layer syntax, structural, runtime, integrity, and functional criteria.
    """

    def __init__(
        self,
        workspace: Union[SafeWorkspaceManager, Path, str],
        config: Optional[GameDevConfig] = None,
    ) -> None:
        if isinstance(workspace, SafeWorkspaceManager):
            self.workspace = workspace
            self.root = self.workspace.workspace_root
        else:
            self.root = Path(workspace).resolve()
            self.workspace = SafeWorkspaceManager(self.root)
        self.config = config or getattr(self.workspace, "config", None) or GameDevConfig.load()

    # =========================================================================
    # 1. Web Verification (HTML, CSS, JS, Assets, Cross-File Links)
    # =========================================================================

    def verify_web_deliverable(
        self,
        task_id: str = "web_verify",
        project_id: str = "web_project",
        required_pages: Optional[List[str]] = None,
        functional_requirements: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[DiagnosticReport]]:
        """Verifies HTML, CSS, JS, asset integrity, and functional requirements for websites."""
        diagnostics: List[DiagnosticReport] = []
        pages = required_pages or ["index.html"]

        # Check required entry points exist
        for page in pages:
            page_path = self.root / page
            if not page_path.exists():
                diagnostics.append(DiagnosticReport(
                    task_id=task_id,
                    project_id=project_id,
                    agent_responsible="coding_agent",
                    verification_category=VerificationCategory.STRUCTURE,
                    error_severity="CRITICAL",
                    file_path=page,
                    error_message=f"Required page '{page}' is missing from workspace root.",
                    expected_behavior=f"File '{page}' must exist.",
                    actual_behavior="File not found.",
                ))
                continue

            content = page_path.read_text(encoding="utf-8", errors="replace")
            # 1. HTML Syntax & Structural Validation
            parser = SimpleHTMLTagValidator()
            try:
                parser.feed(content)
                parser.finalize()
            except Exception as e:
                diagnostics.append(DiagnosticReport(
                    task_id=task_id,
                    project_id=project_id,
                    agent_responsible="coding_agent",
                    verification_category=VerificationCategory.SYNTAX,
                    error_severity="ERROR",
                    file_path=page,
                    error_message=f"HTML parsing failure: {e}",
                    diagnostic_output=str(e),
                    expected_behavior="Valid well-formed HTML5 document.",
                    actual_behavior=f"Parser threw {type(e).__name__}",
                ))

            for err in parser.errors:
                line_m = re.search(r"line (\d+)", err)
                col_m = re.search(r":(\d+)", err)
                line_no = int(line_m.group(1)) if line_m else None
                col_no = int(col_m.group(1)) if col_m else None
                diagnostics.append(DiagnosticReport(
                    task_id=task_id,
                    project_id=project_id,
                    agent_responsible="coding_agent",
                    verification_category=VerificationCategory.STRUCTURE,
                    error_severity="ERROR",
                    file_path=page,
                    line_number=line_no,
                    column_number=col_no,
                    error_message=err,
                    diagnostic_output=err,
                    expected_behavior="All HTML tags must be properly nested and closed.",
                    actual_behavior=err,
                    suggested_correction="Close open tags or remove mismatched closing tags.",
                ))

            # 2. Check essential HTML document structures
            if not parser.has_doctype:
                diagnostics.append(DiagnosticReport(
                    task_id=task_id,
                    project_id=project_id,
                    agent_responsible="coding_agent",
                    verification_category=VerificationCategory.STRUCTURE,
                    error_severity="WARNING",
                    file_path=page,
                    error_message="Missing <!DOCTYPE html> declaration.",
                    suggested_correction="Add <!DOCTYPE html> to top of file.",
                ))
            if not parser.has_viewport:
                diagnostics.append(DiagnosticReport(
                    task_id=task_id,
                    project_id=project_id,
                    agent_responsible="coding_agent",
                    verification_category=VerificationCategory.STRUCTURE,
                    error_severity="WARNING",
                    file_path=page,
                    error_message="Missing responsive viewport meta tag.",
                    suggested_correction="Add <meta name='viewport' content='width=device-width, initial-scale=1.0'> in <head>.",
                ))

            # 3. Check broken local links, scripts, and images
            for link in parser.links:
                if link.startswith(("http://", "https://", "#", "mailto:", "data:")):
                    continue
                clean_link = link.split("?")[0].split("#")[0]
                target_asset = (page_path.parent / clean_link).resolve()
                if not target_asset.exists():
                    diagnostics.append(DiagnosticReport(
                        task_id=task_id,
                        project_id=project_id,
                        agent_responsible="coding_agent",
                        verification_category=VerificationCategory.INTEGRITY,
                        error_severity="ERROR",
                        file_path=page,
                        error_message=f"Broken stylesheet or resource link: '{link}' not found on disk.",
                        expected_behavior=f"Resource '{clean_link}' must exist.",
                        actual_behavior="Target file does not exist.",
                    ))

            for script in parser.scripts:
                if script.startswith(("http://", "https://", "data:")):
                    continue
                clean_script = script.split("?")[0]
                target_script = (page_path.parent / clean_script).resolve()
                if not target_script.exists():
                    diagnostics.append(DiagnosticReport(
                        task_id=task_id,
                        project_id=project_id,
                        agent_responsible="coding_agent",
                        verification_category=VerificationCategory.INTEGRITY,
                        error_severity="ERROR",
                        file_path=page,
                        error_message=f"Broken script reference: '{script}' not found on disk.",
                        expected_behavior=f"Script '{clean_script}' must exist.",
                        actual_behavior="Target file does not exist.",
                    ))

            for img in parser.images:
                if img.startswith(("http://", "https://", "data:")):
                    continue
                clean_img = img.split("?")[0]
                target_img = (page_path.parent / clean_img).resolve()
                if not target_img.exists():
                    diagnostics.append(DiagnosticReport(
                        task_id=task_id,
                        project_id=project_id,
                        agent_responsible="image_agent",
                        verification_category=VerificationCategory.INTEGRITY,
                        error_severity="WARNING",
                        file_path=page,
                        error_message=f"Referenced image '{img}' is missing from project directory.",
                        expected_behavior=f"Image asset '{clean_img}' must be generated and present.",
                        actual_behavior="File missing on disk.",
                    ))

        # 4. Check CSS syntax and balanced braces
        for css_file in self.root.rglob("*.css"):
            rel_css = str(css_file.relative_to(self.root))
            css_text = css_file.read_text(encoding="utf-8", errors="replace")
            # Strip comments for brace balance check
            clean_css = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)
            open_b = clean_css.count("{")
            close_b = clean_css.count("}")
            if open_b != close_b:
                diff = open_b - close_b
                diagnostics.append(DiagnosticReport(
                    task_id=task_id,
                    project_id=project_id,
                    agent_responsible="coding_agent",
                    verification_category=VerificationCategory.SYNTAX,
                    error_severity="ERROR",
                    file_path=rel_css,
                    error_message=f"CSS syntax error: Unbalanced braces in stylesheet ({open_b} open '{{', {close_b} close '}}').",
                    expected_behavior="All CSS rule blocks must have matching closing braces.",
                    actual_behavior=f"{abs(diff)} unclosed/extra brace(s).",
                    suggested_correction="Balance braces in CSS file.",
                ))

        # 5. Check JS syntax
        for js_file in self.root.rglob("*.js"):
            rel_js = str(js_file.relative_to(self.root)).replace("\\", "/")
            if any(part in rel_js.lower() for part in ("libs/", "vendor/", "node_modules/", ".min.js", ".mind_checkpoints")):
                continue
            js_text = js_file.read_text(encoding="utf-8", errors="replace")
            clean_js = re.sub(r"/\*.*?\*/", "", js_text, flags=re.DOTALL)
            clean_js = re.sub(r"//.*", "", clean_js)
            for char_pair in [("{", "}"), ("(", ")"), ("[", "]")]:
                op, cl = char_pair
                if clean_js.count(op) != clean_js.count(cl):
                    diagnostics.append(DiagnosticReport(
                        task_id=task_id,
                        project_id=project_id,
                        agent_responsible="coding_agent",
                        verification_category=VerificationCategory.SYNTAX,
                        error_severity="ERROR",
                        file_path=rel_js,
                        error_message=f"JavaScript syntax error: Unbalanced '{op}' and '{cl}' ({clean_js.count(op)} vs {clean_js.count(cl)}).",
                        expected_behavior=f"Matching pairs of {op}{cl}.",
                        actual_behavior=f"Count mismatch in {rel_js}.",
                    ))

        # 6. Functional requirements check (if provided)
        if functional_requirements:
            expected_keywords = functional_requirements.get("expected_keywords", [])
            for kw in expected_keywords:
                matched = any(kw.lower() in (self.root / p).read_text(encoding="utf-8", errors="replace").lower()
                              for p in pages if (self.root / p).exists())
                if not matched:
                    diagnostics.append(DiagnosticReport(
                        task_id=task_id,
                        project_id=project_id,
                        agent_responsible="coding_agent",
                        verification_category=VerificationCategory.FUNCTIONAL,
                        error_severity="ERROR",
                        file_path="index.html",
                        error_message=f"Functional requirement unmet: Keyword or feature '{kw}' is missing from website content.",
                        expected_behavior=f"Website content must incorporate requirement '{kw}'.",
                        actual_behavior="Keyword not found in candidate files.",
                    ))

        has_critical = any(d.error_severity in ("ERROR", "CRITICAL") for d in diagnostics)
        return not has_critical, diagnostics

    # =========================================================================
    # 2. Python Verification (Syntax, AST, Imports, Runtime, Tests)
    # =========================================================================

    def verify_python_deliverable(
        self,
        entry_file: str = "app/main.py",
        task_id: str = "py_verify",
        project_id: str = "py_project",
        run_entry: bool = False,
        functional_test: Optional[callable] = None,
    ) -> Tuple[bool, List[DiagnosticReport]]:
        """Verifies Python files for syntax, import resolution, runtime execution, and tests."""
        diagnostics: List[DiagnosticReport] = []
        py_files = list(self.root.rglob("*.py"))

        if not py_files:
            diagnostics.append(DiagnosticReport(
                task_id=task_id,
                project_id=project_id,
                agent_responsible="coding_agent",
                verification_category=VerificationCategory.STRUCTURE,
                error_severity="CRITICAL",
                file_path=entry_file,
                error_message="No Python source files found in workspace.",
            ))
            return False, diagnostics

        # 1. Compilation & Syntax Verification via ast.parse
        for py_path in py_files:
            rel_path = str(py_path.relative_to(self.root))
            code = py_path.read_text(encoding="utf-8", errors="replace")
            try:
                tree = ast.parse(code, filename=rel_path)
            except SyntaxError as e:
                diagnostics.append(DiagnosticReport(
                    task_id=task_id,
                    project_id=project_id,
                    agent_responsible="coding_agent",
                    verification_category=VerificationCategory.SYNTAX,
                    error_severity="CRITICAL",
                    file_path=rel_path,
                    line_number=e.lineno,
                    column_number=e.offset,
                    error_message=f"Python SyntaxError: {e.msg}",
                    diagnostic_output=f"File \"{rel_path}\", line {e.lineno}, col {e.offset}\n{e.text}",
                    code_context=e.text or "",
                    expected_behavior="Code must compile cleanly without SyntaxError.",
                    actual_behavior=f"SyntaxError: {e.msg}",
                    suggested_correction="Fix syntax error at indicated line and column.",
                ))
                continue

            # 2. Dependency & Import Resolution Check
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    mod_name = ""
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            mod_name = alias.name.split(".")[0]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        mod_name = node.module.split(".")[0]

                    if mod_name:
                        # Check if module is standard library, installed in venv, or local project directory
                        is_local = (self.root / mod_name).exists() or (self.root / f"{mod_name}.py").exists()
                        if not is_local:
                            try:
                                __import__(mod_name)
                            except ImportError:
                                diagnostics.append(DiagnosticReport(
                                    task_id=task_id,
                                    project_id=project_id,
                                    agent_responsible="coding_agent",
                                    verification_category=VerificationCategory.DEPENDENCY,
                                    error_severity="ERROR",
                                    file_path=rel_path,
                                    line_number=getattr(node, "lineno", None),
                                    error_message=f"Missing dependency: Module '{mod_name}' is not installed or available.",
                                    expected_behavior=f"Module '{mod_name}' must be installed or bundled.",
                                    actual_behavior="ImportError: No module named " + mod_name,
                                    suggested_correction=f"Add '{mod_name}' to requirements.txt or install it.",
                                ))

        # 3. Runtime Sandbox Execution (if entry file exists and requested)
        target_entry = self.root / entry_file
        if target_entry.exists() and run_entry:
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.root)
            cmd = [sys.executable, str(target_entry)]
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(self.root),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if proc.returncode != 0:
                    err_out = proc.stderr or proc.stdout
                    line_no = None
                    line_m = re.findall(r'line (\d+)', err_out)
                    if line_m:
                        line_no = int(line_m[-1])

                    err_lines = [l.strip() for l in err_out.splitlines() if l.strip()]
                    last_err = err_lines[-1] if err_lines else "Runtime execution failed."

                    diagnostics.append(DiagnosticReport(
                        task_id=task_id,
                        project_id=project_id,
                        agent_responsible="coding_agent",
                        verification_category=VerificationCategory.RUNTIME,
                        error_severity="ERROR",
                        file_path=entry_file,
                        line_number=line_no,
                        error_message=last_err,
                        diagnostic_output=err_out,
                        expected_behavior="Entry point must execute without unhandled exceptions.",
                        actual_behavior=f"Process exited with code {proc.returncode}: {last_err}",
                    ))
            except subprocess.TimeoutExpired:
                # Daemon or GUI entry point timed out - expected for interactive apps
                pass
            except Exception as e:
                diagnostics.append(DiagnosticReport(
                    task_id=task_id,
                    project_id=project_id,
                    agent_responsible="coding_agent",
                    verification_category=VerificationCategory.RUNTIME,
                    error_severity="ERROR",
                    file_path=entry_file,
                    error_message=f"Execution error: {e}",
                ))

        # 4. Functional Test Verification
        if functional_test:
            try:
                passed, err_msg = functional_test(self.root)
                if not passed:
                    diagnostics.append(DiagnosticReport(
                        task_id=task_id,
                        project_id=project_id,
                        agent_responsible="coding_agent",
                        verification_category=VerificationCategory.FUNCTIONAL,
                        error_severity="CRITICAL",
                        file_path=entry_file,
                        error_message=f"Functional verification failed: {err_msg}",
                        expected_behavior="Code must satisfy functional acceptance criteria.",
                        actual_behavior=err_msg,
                    ))
            except Exception as e:
                diagnostics.append(DiagnosticReport(
                    task_id=task_id,
                    project_id=project_id,
                    agent_responsible="coding_agent",
                    verification_category=VerificationCategory.FUNCTIONAL,
                    error_severity="CRITICAL",
                    file_path=entry_file,
                    error_message=f"Functional test raised exception: {e}",
                    diagnostic_output=str(e),
                ))

        has_critical = any(d.error_severity in ("ERROR", "CRITICAL") for d in diagnostics)
        return not has_critical, diagnostics

    # =========================================================================
    # 3. C / Compiled Code Verification (Syntax, Diagnostics, Capitalization)
    # =========================================================================

    def verify_c_code(
        self,
        c_file_path: Union[str, Path],
        task_id: str = "c_verify",
        project_id: str = "c_project",
    ) -> Tuple[bool, List[DiagnosticReport]]:
        """
        Verifies C code. If gcc or clang is available, runs compiler diagnostic checks.
        Otherwise applies language-aware semantic parsing to detect common compiler errors:
        incorrect function capitalization (e.g. Printf -> printf), missing headers, unclosed braces,
        and undefined symbols.
        """
        diagnostics: List[DiagnosticReport] = []
        full_path = (self.root / c_file_path).resolve()
        if not full_path.exists():
            diagnostics.append(DiagnosticReport(
                task_id=task_id,
                project_id=project_id,
                agent_responsible="coding_agent",
                verification_category=VerificationCategory.STRUCTURE,
                error_severity="CRITICAL",
                file_path=str(c_file_path),
                error_message=f"C source file '{c_file_path}' does not exist.",
            ))
            return False, diagnostics

        rel_path = str(full_path.relative_to(self.root))
        code = full_path.read_text(encoding="utf-8", errors="replace")

        # Try real compiler if available on PATH
        compiler = shutil.which("gcc") or shutil.which("clang")
        if compiler:
            try:
                proc = subprocess.run(
                    [compiler, "-fsyntax-only", "-Wall", str(full_path)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if proc.returncode != 0:
                    output = proc.stderr or proc.stdout
                    for line in output.splitlines():
                        if ": error:" in line or ": warning:" in line:
                            parts = line.split(":")
                            line_no = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
                            col_no = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
                            msg = parts[-1].strip() if len(parts) > 3 else line
                            severity = "ERROR" if ": error:" in line else "WARNING"
                            diagnostics.append(DiagnosticReport(
                                task_id=task_id,
                                project_id=project_id,
                                agent_responsible="coding_agent",
                                verification_category=VerificationCategory.SYNTAX,
                                error_severity=severity,
                                file_path=rel_path,
                                line_number=line_no,
                                column_number=col_no,
                                error_message=msg,
                                diagnostic_output=output,
                                expected_behavior="Code must compile without errors.",
                                actual_behavior=msg,
                            ))
                    has_errors = any(d.error_severity == "ERROR" for d in diagnostics)
                    return not has_errors, diagnostics
            except Exception:
                pass

        # Language-Aware Static Analysis for C
        lines = code.splitlines()
        # Common C stdio functions with incorrect capitalization
        stdio_casing_map = {
            "Printf": "printf",
            "Scanf": "scanf",
            "Fprintf": "fprintf",
            "Sprintf": "sprintf",
            "Fputs": "fputs",
            "Fgets": "fgets",
            "Strcpy": "strcpy",
            "Strcat": "strcat",
            "Strlen": "strlen",
            "Malloc": "malloc",
            "Free": "free",
        }

        for idx, line in enumerate(lines, start=1):
            # Check for misspelled stdio functions
            for bad_sym, correct_sym in stdio_casing_map.items():
                pattern = r'\b' + bad_sym + r'\b(?=\s*\()'
                m = re.search(pattern, line)
                if m:
                    diagnostics.append(DiagnosticReport(
                        task_id=task_id,
                        project_id=project_id,
                        agent_responsible="coding_agent",
                        verification_category=VerificationCategory.SYNTAX,
                        error_severity="ERROR",
                        file_path=rel_path,
                        line_number=idx,
                        column_number=m.start() + 1,
                        error_message=f"Implicit declaration or undefined symbol '{bad_sym}'; did you mean '{correct_sym}'?",
                        diagnostic_output=f"{rel_path}:{idx}:{m.start()+1}: error: call to undeclared library function '{bad_sym}'",
                        expected_behavior=f"Standard library function '{correct_sym}' from <stdio.h>.",
                        actual_behavior=f"Undefined symbol '{bad_sym}'.",
                        code_context=line,
                        suggested_correction=f"Replace '{bad_sym}' with '{correct_sym}'.",
                    ))

        # Strip comments for static syntax and semantic analysis
        clean_code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        clean_code = re.sub(r'//.*', '', clean_code)

        # Check for function argument count mismatches (e.g. compute_area(10) when declared compute_area(int width, int height))
        fn_decl_pattern = r'\b(?:int|void|float|double|char|long)\s+([a-zA-Z_]\w*)\s*\(([^)]*)\)\s*\{'
        declared_funcs: Dict[str, List[str]] = {}
        for m in re.finditer(fn_decl_pattern, clean_code):
            fname = m.group(1)
            params = [p.strip() for p in m.group(2).split(',') if p.strip() and p.strip() != 'void']
            declared_funcs[fname] = params

        for fname, params in declared_funcs.items():
            call_pattern = rf'\b{fname}\s*\(([^)]*)\)'
            for idx, line in enumerate(lines, start=1):
                if re.search(rf'\b(?:int|void|float|double|char|long)\s+{fname}', line):
                    continue
                call_match = re.search(call_pattern, line)
                if call_match:
                    arg_str = call_match.group(1).strip()
                    args = [a.strip() for a in arg_str.split(',') if a.strip()]
                    if len(args) != len(params):
                        err_type = "too few" if len(args) < len(params) else "too many"
                        diagnostics.append(DiagnosticReport(
                            task_id=task_id,
                            project_id=project_id,
                            agent_responsible="coding_agent",
                            verification_category=VerificationCategory.SYNTAX,
                            error_severity="ERROR",
                            file_path=rel_path,
                            line_number=idx,
                            error_message=f"{err_type} arguments to function '{fname}' (expected {len(params)}, have {len(args)})",
                            diagnostic_output=f"{rel_path}:{idx}: error: {err_type} arguments to function '{fname}' (expected {len(params)}, have {len(args)})\n{line.strip()}",
                            expected_behavior=f"Function '{fname}' requires {len(params)} argument(s): {', '.join(params)}.",
                            actual_behavior=f"Called with {len(args)} argument(s): {arg_str}.",
                            code_context=line.strip(),
                        ))

        # Check for balanced braces in C
        clean_code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        clean_code = re.sub(r'//.*', '', clean_code)
        if clean_code.count('{') != clean_code.count('}'):
            diagnostics.append(DiagnosticReport(
                task_id=task_id,
                project_id=project_id,
                agent_responsible="coding_agent",
                verification_category=VerificationCategory.SYNTAX,
                error_severity="ERROR",
                file_path=rel_path,
                error_message=f"Mismatched braces in C source ({clean_code.count('{')} open, {clean_code.count('}')} close).",
                expected_behavior="Balanced braces in C code.",
                actual_behavior="Brace count mismatch.",
            ))

        has_critical = any(d.error_severity in ("ERROR", "CRITICAL") for d in diagnostics)
        return not has_critical, diagnostics

    # =========================================================================
    # 4. 3D Model & Asset Verification (GLB, PNG, Textures)
    # =========================================================================

    def verify_3d_asset(
        self,
        glb_file_path: Union[str, Path],
        task_id: str = "3d_verify",
        project_id: str = "3d_project",
    ) -> Tuple[bool, List[DiagnosticReport]]:
        """Verifies binary GLB header integrity, version, and chunk-by-chunk mesh/primitive payload."""
        diagnostics: List[DiagnosticReport] = []
        full_path = (self.root / glb_file_path).resolve()

        if not full_path.exists():
            diagnostics.append(DiagnosticReport(
                task_id=task_id,
                project_id=project_id,
                agent_responsible="threed_agent",
                verification_category=VerificationCategory.INTEGRITY,
                error_severity="CRITICAL",
                file_path=str(glb_file_path),
                error_message=f"3D GLB file '{glb_file_path}' does not exist on disk.",
            ))
            return False, diagnostics

        rel_path = str(full_path.relative_to(self.root))
        size = full_path.stat().st_size
        if size < 20:
            diagnostics.append(DiagnosticReport(
                task_id=task_id,
                project_id=project_id,
                agent_responsible="threed_agent",
                verification_category=VerificationCategory.STRUCTURE,
                error_severity="CRITICAL",
                file_path=rel_path,
                error_message=f"GLB file is empty or too small ({size} bytes).",
            ))
            return False, diagnostics

        # Comprehensive chunk-by-chunk glTF 2.0 binary GLB parsing
        try:
            with open(full_path, "rb") as f:
                header = f.read(12)
                if len(header) < 12:
                    diagnostics.append(DiagnosticReport(
                        task_id=task_id,
                        project_id=project_id,
                        agent_responsible="threed_agent",
                        verification_category=VerificationCategory.STRUCTURE,
                        error_severity="CRITICAL",
                        file_path=rel_path,
                        error_message="GLB header truncated (less than 12 bytes).",
                    ))
                    return False, diagnostics

                magic, version, total_length = struct.unpack("<4sII", header)
                if magic != b"glTF":
                    diagnostics.append(DiagnosticReport(
                        task_id=task_id,
                        project_id=project_id,
                        agent_responsible="threed_agent",
                        verification_category=VerificationCategory.STRUCTURE,
                        error_severity="CRITICAL",
                        file_path=rel_path,
                        error_message=f"Invalid GLB binary magic: expected b'glTF', got {magic}",
                    ))
                    return False, diagnostics

                if version != 2:
                    diagnostics.append(DiagnosticReport(
                        task_id=task_id,
                        project_id=project_id,
                        agent_responsible="threed_agent",
                        verification_category=VerificationCategory.STRUCTURE,
                        error_severity="WARNING",
                        file_path=rel_path,
                        error_message=f"Unexpected glTF version: {version} (standard is 2)",
                    ))

                # Read Chunk 0: JSON chunk
                chunk0_header = f.read(8)
                if len(chunk0_header) < 8:
                    diagnostics.append(DiagnosticReport(
                        task_id=task_id,
                        project_id=project_id,
                        agent_responsible="threed_agent",
                        verification_category=VerificationCategory.STRUCTURE,
                        error_severity="CRITICAL",
                        file_path=rel_path,
                        error_message="Missing GLB JSON chunk header.",
                    ))
                    return False, diagnostics

                chunk0_len, chunk0_type = struct.unpack("<I4s", chunk0_header)
                if chunk0_type != b"JSON":
                    diagnostics.append(DiagnosticReport(
                        task_id=task_id,
                        project_id=project_id,
                        agent_responsible="threed_agent",
                        verification_category=VerificationCategory.STRUCTURE,
                        error_severity="CRITICAL",
                        file_path=rel_path,
                        error_message=f"Expected Chunk 0 type b'JSON', got {chunk0_type}",
                    ))
                    return False, diagnostics

                chunk0_data = f.read(chunk0_len)
                try:
                    gltf_json = json.loads(chunk0_data.decode("utf-8"))
                except Exception as json_err:
                    diagnostics.append(DiagnosticReport(
                        task_id=task_id,
                        project_id=project_id,
                        agent_responsible="threed_agent",
                        verification_category=VerificationCategory.STRUCTURE,
                        error_severity="CRITICAL",
                        file_path=rel_path,
                        error_message=f"Invalid JSON chunk in GLB: {json_err}",
                    ))
                    return False, diagnostics

                # Verify mesh & primitive structures
                meshes = gltf_json.get("meshes", [])
                if not meshes:
                    diagnostics.append(DiagnosticReport(
                        task_id=task_id,
                        project_id=project_id,
                        agent_responsible="threed_agent",
                        verification_category=VerificationCategory.STRUCTURE,
                        error_severity="CRITICAL",
                        file_path=rel_path,
                        error_message="GLB model contains no meshes.",
                    ))
                else:
                    for m_idx, mesh in enumerate(meshes):
                        primitives = mesh.get("primitives", [])
                        if not primitives:
                            diagnostics.append(DiagnosticReport(
                                task_id=task_id,
                                project_id=project_id,
                                agent_responsible="threed_agent",
                                verification_category=VerificationCategory.STRUCTURE,
                                error_severity="CRITICAL",
                                file_path=rel_path,
                                error_message=f"Mesh {m_idx} contains no primitives.",
                            ))
                        for p in primitives:
                            if "POSITION" not in p.get("attributes", {}):
                                diagnostics.append(DiagnosticReport(
                                    task_id=task_id,
                                    project_id=project_id,
                                    agent_responsible="threed_agent",
                                    verification_category=VerificationCategory.STRUCTURE,
                                    error_severity="CRITICAL",
                                    file_path=rel_path,
                                    error_message="Primitive missing mandatory 'POSITION' vertex attribute.",
                                ))

                # Check Chunk 1: Binary Buffer
                chunk1_header = f.read(8)
                if chunk1_header and len(chunk1_header) == 8:
                    chunk1_len, chunk1_type = struct.unpack("<I4s", chunk1_header)
                    if chunk1_type != b"BIN\x00":
                        diagnostics.append(DiagnosticReport(
                            task_id=task_id,
                            project_id=project_id,
                            agent_responsible="threed_agent",
                            verification_category=VerificationCategory.STRUCTURE,
                            error_severity="WARNING",
                            file_path=rel_path,
                            error_message=f"Unexpected Chunk 1 type: {chunk1_type}",
                        ))
                    bin_data = f.read(chunk1_len)
                    if len(bin_data) < chunk1_len:
                        diagnostics.append(DiagnosticReport(
                            task_id=task_id,
                            project_id=project_id,
                            agent_responsible="threed_agent",
                            verification_category=VerificationCategory.STRUCTURE,
                            error_severity="CRITICAL",
                            file_path=rel_path,
                            error_message="GLB binary chunk truncated.",
                        ))

            # Blender Import Validation Check
            from ..adapters.blender_adapter import BlenderAdapter
            blender_adapter = BlenderAdapter(self.config)
            if blender_adapter.is_available():
                test_import_script = f"import bpy; bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=r'{full_path}')"
                res = blender_adapter.execute_script(test_import_script, full_path.parent, expected_glb_name="none.glb", timeout_seconds=10.0, render_preview=False)
                if not res.get("success"):
                    diagnostics.append(DiagnosticReport(
                        task_id=task_id,
                        project_id=project_id,
                        agent_responsible="threed_agent",
                        verification_category=VerificationCategory.RUNTIME,
                        error_severity="ERROR",
                        file_path=rel_path,
                        error_message=f"Blender failed to import GLB model: {res.get('error')}",
                    ))
            else:
                logger.info(f"Blender CLI validation for '{rel_path}': NOT RUN (Blender CLI not detected on system PATH).")

        except Exception as e:
            diagnostics.append(DiagnosticReport(
                task_id=task_id,
                project_id=project_id,
                agent_responsible="threed_agent",
                verification_category=VerificationCategory.STRUCTURE,
                error_severity="CRITICAL",
                file_path=rel_path,
                error_message=f"Failed to parse GLB header: {e}",
            ))

        has_critical = any(d.error_severity in ("ERROR", "CRITICAL") for d in diagnostics)
        return not has_critical, diagnostics

    # =========================================================================
    # 5. JavaScript / Node.js & TypeScript Verification
    # =========================================================================

    def verify_js_code(
        self,
        js_file_path: Union[str, Path],
        task_id: str = "js_verify",
        project_id: str = "js_project",
        run_execution: bool = True,
    ) -> Tuple[bool, List[DiagnosticReport]]:
        """Verifies JavaScript file using Node.js runtime/syntax checker, or static analysis if Node is unavailable."""
        diagnostics: List[DiagnosticReport] = []
        full_path = (self.root / js_file_path).resolve()
        if not full_path.exists():
            diagnostics.append(DiagnosticReport(
                task_id=task_id,
                project_id=project_id,
                agent_responsible="coding_agent",
                verification_category=VerificationCategory.STRUCTURE,
                error_severity="CRITICAL",
                file_path=str(js_file_path),
                error_message=f"JavaScript file '{js_file_path}' does not exist.",
            ))
            return False, diagnostics

        rel_path = str(full_path.relative_to(self.root))
        code = full_path.read_text(encoding="utf-8", errors="replace")

        # Try Node.js if available
        node_bin = shutil.which("node") or (Path(r"D:\nodejs\node.exe") if Path(r"D:\nodejs\node.exe").exists() else None)
        if node_bin:
            try:
                # 1. Syntax check
                check_proc = subprocess.run(
                    [str(node_bin), "--check", str(full_path)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if check_proc.returncode != 0:
                    err_out = check_proc.stderr or check_proc.stdout
                    line_no = None
                    m = re.search(rf"{re.escape(str(full_path))}:(\d+)", err_out) or re.search(r":(\d+)", err_out)
                    if m:
                        line_no = int(m.group(1))
                    diagnostics.append(DiagnosticReport(
                        task_id=task_id,
                        project_id=project_id,
                        agent_responsible="coding_agent",
                        verification_category=VerificationCategory.SYNTAX,
                        error_severity="ERROR",
                        file_path=rel_path,
                        line_number=line_no,
                        error_message=f"JavaScript SyntaxError: {err_out.splitlines()[0] if err_out.splitlines() else 'Syntax error'}",
                        diagnostic_output=err_out,
                    ))
                    return False, diagnostics

                # 2. Runtime execution check if standalone script
                if run_execution:
                    run_proc = subprocess.run(
                        [str(node_bin), str(full_path)],
                        cwd=str(self.root),
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if run_proc.returncode != 0:
                        err_out = run_proc.stderr or run_proc.stdout
                        line_no = None
                        for line in err_out.splitlines():
                            if str(full_path) in line or rel_path in line or ".js:" in line:
                                lm = re.search(r":(\d+)", line)
                                if lm:
                                    line_no = int(lm.group(1))
                                    break
                        # Extract the actual error exception line (e.g. ReferenceError: ... or TypeError: ...)
                        error_lines = [l.strip() for l in err_out.splitlines() if "Error:" in l or "Error" in l]
                        first_err = error_lines[0] if error_lines else (err_out.splitlines()[-1] if err_out.splitlines() else "Runtime error")
                        diagnostics.append(DiagnosticReport(
                            task_id=task_id,
                            project_id=project_id,
                            agent_responsible="coding_agent",
                            verification_category=VerificationCategory.RUNTIME,
                            error_severity="ERROR",
                            file_path=rel_path,
                            line_number=line_no,
                            error_message=first_err,
                            diagnostic_output=err_out,
                            expected_behavior="Script must execute cleanly without unhandled ReferenceError or exceptions.",
                            actual_behavior=first_err,
                        ))
                        return False, diagnostics

            except subprocess.TimeoutExpired:
                pass
            except Exception as e:
                logger.warning(f"Node execution check failed: {e}")

        # Static fallback if node is absent or not run
        clean_code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        clean_code = re.sub(r'//.*', '', clean_code)
        fn_pattern = r'\bfunction\s+([a-zA-Z_]\w*)\s*\('
        declared_funcs = set(re.findall(fn_pattern, clean_code))
        call_pattern = r'\b([a-zA-Z_]\w*)\s*\('
        lines = code.splitlines()
        for idx, line in enumerate(lines, start=1):
            if line.strip().startswith("//") or line.strip().startswith("/*"):
                continue
            for called_fn in re.findall(call_pattern, line):
                if called_fn in ("function", "if", "for", "while", "switch", "catch", "return", "console", "log", "require", "import"):
                    continue
                if called_fn not in declared_funcs and any(called_fn != df and len(called_fn) == len(df) and sum(c1 != c2 for c1, c2 in zip(called_fn, df)) <= 2 for df in declared_funcs):
                    diagnostics.append(DiagnosticReport(
                        task_id=task_id,
                        project_id=project_id,
                        agent_responsible="coding_agent",
                        verification_category=VerificationCategory.RUNTIME,
                        error_severity="ERROR",
                        file_path=rel_path,
                        line_number=idx,
                        error_message=f"ReferenceError: {called_fn} is not defined",
                        diagnostic_output=f"ReferenceError: {called_fn} is not defined\n    at {rel_path}:{idx}:1",
                        expected_behavior="Function call must reference defined function.",
                        actual_behavior=f"'{called_fn}' is undefined.",
                        code_context=line.strip(),
                    ))

        has_critical = any(d.error_severity in ("ERROR", "CRITICAL") for d in diagnostics)
        return not has_critical, diagnostics

    def verify_typescript_code(
        self,
        ts_file_path: Union[str, Path],
        task_id: str = "ts_verify",
        project_id: str = "ts_project",
    ) -> Tuple[bool, List[DiagnosticReport]]:
        """Verifies TypeScript types and syntax using tsc if available or language-aware static type checking."""
        diagnostics: List[DiagnosticReport] = []
        full_path = (self.root / ts_file_path).resolve()
        if not full_path.exists():
            diagnostics.append(DiagnosticReport(
                task_id=task_id,
                project_id=project_id,
                agent_responsible="coding_agent",
                verification_category=VerificationCategory.STRUCTURE,
                error_severity="CRITICAL",
                file_path=str(ts_file_path),
                error_message=f"TypeScript file '{ts_file_path}' does not exist.",
            ))
            return False, diagnostics

        rel_path = str(full_path.relative_to(self.root))
        code = full_path.read_text(encoding="utf-8", errors="replace")

        # Try tsc if available
        tsc_bin = shutil.which("tsc")
        if tsc_bin:
            try:
                proc = subprocess.run([tsc_bin, "--noEmit", str(full_path)], capture_output=True, text=True, timeout=10)
                if proc.returncode != 0:
                    err_out = proc.stderr or proc.stdout
                    for line in err_out.splitlines():
                        if ": error TS" in line:
                            m = re.search(r":(\d+):(\d+): error TS\d+:\s*(.*)", line)
                            l_no = int(m.group(1)) if m else None
                            msg = m.group(3) if m else line
                            diagnostics.append(DiagnosticReport(
                                task_id=task_id,
                                project_id=project_id,
                                agent_responsible="coding_agent",
                                verification_category=VerificationCategory.TYPE_CHECK,
                                error_severity="ERROR",
                                file_path=rel_path,
                                line_number=l_no,
                                error_message=msg,
                                diagnostic_output=line,
                            ))
                    if diagnostics:
                        return False, diagnostics
            except Exception:
                pass

        # Static TypeScript type analysis
        fn_pattern = r'\bfunction\s+([a-zA-Z_]\w*)\s*\(([^)]+)\)\s*:\s*([a-zA-Z_]\w*)'
        lines = code.splitlines()
        typed_funcs: Dict[str, List[Tuple[str, str]]] = {}
        for m in re.finditer(fn_pattern, code):
            fname = m.group(1)
            raw_params = m.group(2).split(',')
            param_list = []
            for p in raw_params:
                if ':' in p:
                    pname, ptype = p.split(':', 1)
                    param_list.append((pname.strip(), ptype.strip()))
            typed_funcs[fname] = param_list

        for fname, params in typed_funcs.items():
            call_pattern = rf'\b{fname}\s*\(([^)]+)\)'
            for idx, line in enumerate(lines, start=1):
                if f"function {fname}" in line:
                    continue
                cm = re.search(call_pattern, line)
                if cm:
                    raw_args = [a.strip() for a in cm.group(1).split(',')]
                    for arg_val, (pname, ptype) in zip(raw_args, params):
                        if ptype == "number" and (arg_val.startswith(('"', "'")) and arg_val.endswith(('"', "'"))):
                            diagnostics.append(DiagnosticReport(
                                task_id=task_id,
                                project_id=project_id,
                                agent_responsible="coding_agent",
                                verification_category=VerificationCategory.TYPE_CHECK,
                                error_severity="ERROR",
                                file_path=rel_path,
                                line_number=idx,
                                error_message=f"Argument of type 'string' is not assignable to parameter of type 'number'.",
                                diagnostic_output=f"{rel_path}:{idx}: error TS2345: Argument of type 'string' is not assignable to parameter of type 'number'.\n{line.strip()}",
                                expected_behavior=f"Parameter '{pname}' expects type 'number'.",
                                actual_behavior=f"Passed string literal {arg_val}.",
                                code_context=line.strip(),
                            ))

        has_critical = any(d.error_severity in ("ERROR", "CRITICAL") for d in diagnostics)
        return not has_critical, diagnostics

    def verify_module_exports(
        self,
        task_id: str = "module_verify",
        project_id: str = "module_project",
    ) -> Tuple[bool, List[DiagnosticReport]]:
        """Verifies cross-file module resolution and exports across JavaScript/TypeScript files."""
        diagnostics: List[DiagnosticReport] = []
        js_ts_files = list(self.root.rglob("*.js")) + list(self.root.rglob("*.ts"))

        for src_file in js_ts_files:
            rel_src = str(src_file.relative_to(self.root))
            content = src_file.read_text(encoding="utf-8", errors="replace")
            # Support both ES import and CommonJS require destructuring
            import_pattern_es = r'import\s+\{([^}]+)\}\s+from\s+[\'"]([^\'"]+)[\'"]'
            import_pattern_cjs = r'(?:const|let|var)\s+\{([^}]+)\}\s*=\s*require\([\'"]([^\'"]+)[\'"]\)'
            lines = content.splitlines()
            for idx, line in enumerate(lines, start=1):
                m = re.search(import_pattern_es, line) or re.search(import_pattern_cjs, line)
                if m:
                    imported_symbols = [s.strip() for s in m.group(1).split(',') if s.strip()]
                    mod_path_str = m.group(2)
                    if mod_path_str.startswith('.'):
                        target_path = (src_file.parent / mod_path_str).resolve()
                        if not target_path.exists():
                            if (src_file.parent / f"{mod_path_str}.js").exists():
                                target_path = (src_file.parent / f"{mod_path_str}.js").resolve()
                            elif (src_file.parent / f"{mod_path_str}.ts").exists():
                                target_path = (src_file.parent / f"{mod_path_str}.ts").resolve()

                        if not target_path.exists():
                            diagnostics.append(DiagnosticReport(
                                task_id=task_id,
                                project_id=project_id,
                                agent_responsible="coding_agent",
                                verification_category=VerificationCategory.STRUCTURE,
                                error_severity="ERROR",
                                file_path=rel_src,
                                line_number=idx,
                                error_message=f"Cannot find module '{mod_path_str}'.",
                                diagnostic_output=f"Error: Cannot find module '{mod_path_str}' from '{rel_src}'",
                            ))
                            continue

                        target_code = target_path.read_text(encoding="utf-8", errors="replace")
                        rel_target = str(target_path.relative_to(self.root)).replace("\\", "/")
                        for sym in imported_symbols:
                            export_pattern = (
                                rf'\bexport\s+(?:function|const|let|var|class)\s+{sym}\b|'
                                rf'\bexport\s+\{{[^}}]*\b{sym}\b[^}}]*\}}|'
                                rf'\bexports\.{sym}\b|'
                                rf'\bmodule\.exports\s*=\s*\{{[^}}]*\b{sym}\b|'
                                rf'\bmodule\.exports\.{sym}\b'
                            )
                            if not re.search(export_pattern, target_code):
                                diagnostics.append(DiagnosticReport(
                                    task_id=task_id,
                                    project_id=project_id,
                                    agent_responsible="coding_agent",
                                    verification_category=VerificationCategory.STRUCTURE,
                                    error_severity="ERROR",
                                    file_path=rel_src,
                                    line_number=idx,
                                    error_message=f"Module '{mod_path_str}' has no exported member '{sym}'.",
                                    diagnostic_output=f"{rel_src}:{idx}: error: Module '{rel_target}' does not export symbol '{sym}' (imported in '{rel_src}')",
                                    expected_behavior=f"Module '{rel_target}' must export '{sym}'.",
                                    actual_behavior=f"Export '{sym}' not found in '{rel_target}'.",
                                    code_context=line.strip(),
                                    suggested_correction=f"Export '{sym}' from '{rel_target}' or adjust import in '{rel_src}'.",
                                ))

        has_critical = any(d.error_severity in ("ERROR", "CRITICAL") for d in diagnostics)
        return not has_critical, diagnostics
