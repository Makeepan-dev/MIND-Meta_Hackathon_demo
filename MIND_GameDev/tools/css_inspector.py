"""
MIND CSS Inspector & Safe Improver.

Inspects an existing website's stylesheet(s) for real, checkable defects:
  - unbalanced braces / truncated declarations
  - conflicting duplicate selectors (same selector + property, different values)
  - url(...) references to files that do not exist
  - HTML classes that have no CSS rule, and CSS classes absent from every page
  - stylesheet links in HTML that point at missing files

Improvement is non-destructive:
  1. The original stylesheet is backed up next to itself before any write.
  2. A candidate stylesheet is produced (AI provider when available, otherwise a
     deterministic additive "polish layer" that never removes existing rules).
  3. The candidate is accepted only if braces are balanced, class coverage does not
     drop, and every selector from the original that was styled remains styled.
     Otherwise the original file is left untouched and the reason is reported.
"""

from __future__ import annotations

import re
import shutil
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .component_contract import ComponentContractExtractor
from ..adapters.code_extractor import RobustCodeExtractor

_COMMENT_RE = re.compile(r"/\*[\s\S]*?\*/")
_RULE_RE = re.compile(r"([^{}@]+)\{([^{}]*)\}")
_URL_RE = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)")
_CLASS_RE = re.compile(r"\.(-?[_a-zA-Z][_a-zA-Z0-9\-]*)")

POLISH_MARKER = "/* === MIND polish layer (additive, safe to remove) === */"

POLISH_LAYER = POLISH_MARKER + """
*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; scroll-behavior: smooth; }
body { margin: 0; line-height: 1.6; text-rendering: optimizeLegibility; }
img, video, svg, canvas { max-width: 100%; height: auto; }
a:focus-visible, button:focus-visible, input:focus-visible,
select:focus-visible, textarea:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; }
button, input, select, textarea { font: inherit; }
@media (max-width: 768px) {
  table { display: block; overflow-x: auto; }
  pre { white-space: pre-wrap; word-break: break-word; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; scroll-behavior: auto !important; }
}
/* === end MIND polish layer === */
"""


@dataclass
class CSSIssue:
    severity: str  # "error" | "warning" | "info"
    kind: str
    message: str
    file: str = ""


@dataclass
class CSSInspectionReport:
    project_dir: str
    stylesheets: List[str] = field(default_factory=list)
    issues: List[CSSIssue] = field(default_factory=list)
    html_classes: int = 0
    styled_classes: int = 0
    coverage_pct: float = 100.0

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["error_count"] = self.error_count
        return d


def _strip_comments(css: str) -> str:
    return _COMMENT_RE.sub("", css)


def _css_classes(css: str) -> Set[str]:
    out: Set[str] = set()
    for sel, _ in _RULE_RE.findall(_strip_comments(css)):
        out.update(_CLASS_RE.findall(sel))
    return out


def _brace_balance(css: str) -> int:
    clean = _strip_comments(css)
    clean = re.sub(r"(['\"])(?:\\.|(?!\1).)*\1", "", clean)
    return clean.count("{") - clean.count("}")


class CSSInspector:
    """Static inspection of a website project's CSS against its HTML."""

    @classmethod
    def inspect(cls, project_dir: Path) -> CSSInspectionReport:
        project_dir = Path(project_dir)
        report = CSSInspectionReport(project_dir=str(project_dir))
        html_files = sorted(project_dir.glob("*.html"))
        css_files = sorted(p for p in project_dir.rglob("*.css") if "__mind_backup" not in p.name and ".bak" not in p.name)
        report.stylesheets = [str(p.relative_to(project_dir)) for p in css_files]

        html_classes: Set[str] = set()
        for h in html_files:
            text = h.read_text(encoding="utf-8", errors="replace")
            html_classes.update(ComponentContractExtractor.extract(text).classes)
            for href in re.findall(r"<link[^>]+href=[\"']([^\"']+\.css)[\"']", text, re.I):
                if href.startswith(("http://", "https://", "//")):
                    continue
                if not (h.parent / href).exists():
                    report.issues.append(CSSIssue("error", "missing_stylesheet", f"{h.name} links '{href}' which does not exist.", h.name))

        all_css_classes: Set[str] = set()
        for css_path in css_files:
            rel = str(css_path.relative_to(project_dir))
            css = css_path.read_text(encoding="utf-8", errors="replace")
            all_css_classes |= _css_classes(css)

            bal = _brace_balance(css)
            if bal != 0:
                report.issues.append(CSSIssue("error", "unbalanced_braces", f"{abs(bal)} {'unclosed' if bal > 0 else 'extra closing'} brace(s).", rel))

            # Conflicting duplicate declarations for the same selector at top level (outside @media)
            top_level = re.sub(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", _strip_comments(css))
            seen: Dict[tuple, str] = {}
            conflicts: Set[str] = set()
            for sel, body in _RULE_RE.findall(top_level):
                sel_norm = " ".join(sel.split())
                for decl in body.split(";"):
                    if ":" not in decl:
                        continue
                    prop, val = decl.split(":", 1)
                    key = (sel_norm, prop.strip().lower())
                    v = " ".join(val.split())
                    if key in seen and seen[key] != v and key not in conflicts:
                        conflicts.add(key)
                        report.issues.append(CSSIssue(
                            "warning", "conflicting_selector",
                            f"'{sel_norm}' sets '{key[1]}' to both '{seen[key]}' and '{v}'.", rel))
                    seen[key] = v

            for ref in _URL_RE.findall(css):
                if ref.startswith(("data:", "http://", "https://", "//", "#")):
                    continue
                if not (css_path.parent / ref.split("?")[0].split("#")[0]).exists():
                    report.issues.append(CSSIssue("error", "broken_url", f"url('{ref}') does not resolve to a file.", rel))

        if not css_files and html_files:
            report.issues.append(CSSIssue("error", "no_stylesheet", "Project has HTML pages but no CSS files."))

        unstyled = sorted(html_classes - all_css_classes)
        report.html_classes = len(html_classes)
        report.styled_classes = len(html_classes & all_css_classes)
        report.coverage_pct = round(100.0 * report.styled_classes / len(html_classes), 1) if html_classes else 100.0
        if unstyled:
            report.issues.append(CSSIssue(
                "warning" if report.coverage_pct >= 40 else "error", "unstyled_classes",
                f"{len(unstyled)} HTML class(es) have no CSS rule: {', '.join(unstyled[:12])}{' ...' if len(unstyled) > 12 else ''}"))
        unused = sorted(all_css_classes - html_classes)
        if unused and html_files:
            report.issues.append(CSSIssue("info", "unused_css_classes", f"{len(unused)} CSS class(es) not used by any page."))
        return report


class SafeCSSImprover:
    """Improves a stylesheet without removing working rules; backs up before writing."""

    def __init__(self, coding_adapter: Optional[Any] = None) -> None:
        self.coding_adapter = coding_adapter

    def improve(self, project_dir: Path, stylesheet: str = "style.css", request: str = "") -> Dict[str, Any]:
        project_dir = Path(project_dir)
        css_path = project_dir / stylesheet
        if not css_path.exists():
            return {"status": "FILE_NOT_FOUND", "message": f"Stylesheet '{stylesheet}' not found in {project_dir}."}

        before = CSSInspector.inspect(project_dir)
        original = css_path.read_text(encoding="utf-8", errors="replace")
        html_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(project_dir.glob("*.html")))
        original_classes = _css_classes(original)

        provider = "deterministic_polish_layer"
        candidate: Optional[str] = None
        rejected_reason: Optional[str] = None

        if self.coding_adapter is not None and not getattr(getattr(self.coding_adapter, "config", None), "test_mode", False):
            contract = ComponentContractExtractor.extract(html_text)
            prompt = (
                "Improve the visual quality and responsiveness of this existing stylesheet WITHOUT changing functionality.\n"
                f"User request: {request or 'Improve the CSS.'}\n"
                "Rules: keep every existing selector (you may refine its declarations), keep all CSS custom property names, "
                "fix conflicting duplicate declarations, add mobile breakpoints, and output the COMPLETE stylesheet.\n"
                f"{contract.to_css_contract_prompt()}\n"
                f"Detected issues: {[i.message for i in before.issues][:10]}\n"
                f"```css\n{original}\n```\nOutput ONLY the full CSS in a css codeblock."
            )
            try:
                res = self.coding_adapter.generate(prompt=prompt, system_prompt="You are a senior CSS engineer.", language="css")
                prov = res.get("provider", "")
                if res.get("success") and prov in ("openrouter", "ollama_local"):
                    cand = RobustCodeExtractor.extract(res.get("code", ""), language="css").code
                    missing = original_classes - _css_classes(cand)
                    if _brace_balance(cand) != 0:
                        rejected_reason = "AI stylesheet had unbalanced braces"
                    elif missing:
                        rejected_reason = f"AI stylesheet dropped {len(missing)} existing selector class(es) e.g. {sorted(missing)[:5]}"
                    else:
                        candidate, provider = cand, f"{prov} ({res.get('model', '')})"
                else:
                    rejected_reason = f"No AI provider available ({prov or res.get('error', 'unknown')})"
            except Exception as e:  # provider failure must not touch files
                rejected_reason = f"AI provider error: {e}"

        if candidate is None:
            if POLISH_MARKER in original:
                return {
                    "status": "NO_CHANGE",
                    "message": "Polish layer already present; no AI provider produced an acceptable improvement."
                               + (f" ({rejected_reason})" if rejected_reason else ""),
                    "inspection": before.to_dict(),
                }
            candidate = original.rstrip() + "\n\n" + POLISH_LAYER

        if _brace_balance(candidate) != 0:
            return {"status": "REJECTED", "message": "Candidate stylesheet failed brace validation; original kept.", "inspection": before.to_dict()}

        backup = css_path.with_name(f"{css_path.stem}.__mind_backup_{time.strftime('%Y%m%d_%H%M%S')}{css_path.suffix}")
        shutil.copy2(css_path, backup)
        css_path.write_text(candidate, encoding="utf-8")

        after = CSSInspector.inspect(project_dir)
        if after.coverage_pct < before.coverage_pct or after.error_count > before.error_count:
            shutil.copy2(backup, css_path)  # roll back
            return {
                "status": "ROLLED_BACK",
                "message": f"Improvement reduced quality (coverage {before.coverage_pct}%→{after.coverage_pct}%, "
                           f"errors {before.error_count}→{after.error_count}); original restored.",
                "backup_path": str(backup),
                "inspection": before.to_dict(),
            }

        return {
            "status": "SUCCESS",
            "file_path": stylesheet,
            "project_path": str(project_dir),
            "backup_path": str(backup),
            "provider": provider,
            "ai_rejected_reason": rejected_reason,
            "inspection_before": before.to_dict(),
            "inspection_after": after.to_dict(),
            "message": f"Improved {stylesheet} via {provider}. Backup saved to {backup.name}.",
        }
