"""Cross-file component contract extractor and integrity validator.

Binds HTML, CSS, and JavaScript synthesis together by extracting structural contracts
from generated HTML and validating that CSS and JS adhere strictly to the actual
classes, IDs, and elements present in the document.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any


@dataclass
class ComponentContract:
    """Structural component contract extracted from HTML."""
    classes: List[str] = field(default_factory=list)
    ids: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    form_names: List[str] = field(default_factory=list)
    interactive_elements: List[Dict[str, str]] = field(default_factory=list)

    def to_css_contract_prompt(self) -> str:
        """Constructs a binding prompt contract for CSS synthesis."""
        lines = [
            "CRITICAL COMPONENT CONTRACT (BINDING REQUIREMENT):",
            "You MUST style the exact classes and IDs present in the HTML document.",
            "Do NOT use alternative BEM names or invented classes not present in the HTML.",
            f"HTML Classes to style ({len(self.classes)} found):",
            "  " + ", ".join(f".{c}" for c in self.classes[:40]),
        ]
        if self.ids:
            lines.append("HTML Element IDs to style:")
            lines.append("  " + ", ".join(f"#{i}" for i in self.ids[:20]))
        lines.append("Ensure full responsive layout, theme colors, hover effects, and typography for these exact elements.")
        return "\n".join(lines)

    def to_js_contract_prompt(self) -> str:
        """Constructs a binding prompt contract for JavaScript synthesis."""
        lines = [
            "CRITICAL INTERACTIVE CONTRACT (BINDING REQUIREMENT):",
            "You MUST bind event listeners to the exact IDs and classes present in the HTML.",
        ]
        if self.ids:
            lines.append(f"Available Element IDs: {', '.join(f'#{i}' for i in self.ids)}")
        if self.interactive_elements:
            inter_desc = [f"<{el.get('tag')} id='{el.get('id', '')}' class='{el.get('class', '')}'>" for el in self.interactive_elements[:15]]
            lines.append(f"Interactive Targets: {', '.join(inter_desc)}")
        lines.append("Implement functioning event handlers (e.g. mobile navigation toggle, theme switcher, form submission).")
        return "\n".join(lines)


class _HTMLContractParser(HTMLParser):
    """Internal HTML parser extracting classes, IDs, tags, and form fields."""

    def __init__(self) -> None:
        super().__init__()
        self.classes: Set[str] = set()
        self.ids: Set[str] = set()
        self.tags: Set[str] = set()
        self.form_names: Set[str] = set()
        self.interactive: List[Dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        self.tags.add(tag.lower())
        attr_dict = {k.lower(): v for k, v in attrs if v is not None}

        if "class" in attr_dict:
            for cls_token in attr_dict["class"].split():
                if cls_token.strip():
                    self.classes.add(cls_token.strip())

        if "id" in attr_dict:
            id_val = attr_dict["id"].strip()
            if id_val:
                self.ids.add(id_val)

        if "name" in attr_dict and tag.lower() in ("input", "select", "textarea", "form"):
            name_val = attr_dict["name"].strip()
            if name_val:
                self.form_names.add(name_val)

        if tag.lower() in ("button", "a", "input", "form", "select", "dialog"):
            self.interactive.append({
                "tag": tag.lower(),
                "id": attr_dict.get("id", ""),
                "class": attr_dict.get("class", ""),
                "type": attr_dict.get("type", ""),
            })


class ComponentContractExtractor:
    """Extracts component contracts from HTML markup."""

    @classmethod
    def extract(cls, html_text: str) -> ComponentContract:
        """Parses HTML and returns the structural component contract."""
        if not html_text:
            return ComponentContract()

        parser = _HTMLContractParser()
        try:
            parser.feed(html_text)
        except Exception:
            # Fallback regex extraction if HTML is malformed
            classes = set(re.findall(r'class=["\']([^"\']+)["\']', html_text))
            flattened_classes = set()
            for c in classes:
                flattened_classes.update(c.split())
            ids = set(re.findall(r'id=["\']([^"\']+)["\']', html_text))
            return ComponentContract(
                classes=sorted(list(flattened_classes)),
                ids=sorted(list(ids)),
                tags=[],
                form_names=[],
                interactive_elements=[],
            )

        return ComponentContract(
            classes=sorted(list(parser.classes)),
            ids=sorted(list(parser.ids)),
            tags=sorted(list(parser.tags)),
            form_names=sorted(list(parser.form_names)),
            interactive_elements=parser.interactive,
        )


@dataclass
class ValidationReport:
    """Cross-file validation result."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    coverage_pct: float = 100.0
    covered_classes: List[str] = field(default_factory=list)
    missing_classes: List[str] = field(default_factory=list)
    unclosed_braces: int = 0
    preamble_detected: bool = False


class CrossFileIntegrityValidator:
    """Validates structural integrity, selector coverage, and syntax purity across HTML/CSS/JS."""

    # English phrases indicating prose leakage in CSS
    PROSE_LEAK_PHRASES = (
        "here is", "below is", "certainly", "i will", "we will",
        "design plan", "to style", "color palette", "in this section",
        "let me know", "i hope this", "this css provides"
    )

    @classmethod
    def validate(
        cls,
        html_code: str,
        css_code: str,
        js_code: Optional[str] = None,
        min_coverage: float = 40.0,
    ) -> ValidationReport:
        """Validates cross-file selector alignment and code purity."""
        errors: List[str] = []
        warnings: List[str] = []

        # 1. Purity check for CSS: Detect prose / reasoning leakage
        preamble_detected = False
        css_lines = css_code.splitlines()
        for i, line in enumerate(css_lines[:150]):
            clean = line.strip().lower()
            if not clean or clean.startswith("/*") or clean.startswith("*"):
                continue
            if any(clean.startswith(phrase) for phrase in cls.PROSE_LEAK_PHRASES):
                preamble_detected = True
                errors.append(f"Conversational prose detected in CSS at line {i+1}: '{line.strip()[:50]}'")
                break

        # 2. Syntax check: Balanced braces and incomplete declarations
        open_curlies = css_code.count("{")
        close_curlies = css_code.count("}")
        unclosed_braces = open_curlies - close_curlies
        if unclosed_braces != 0:
            errors.append(f"CSS brace mismatch: {open_curlies} opened vs {close_curlies} closed ({unclosed_braces} unclosed).")

        # Check for incomplete declaration at end of CSS
        non_empty = [l.strip() for l in css_lines if l.strip()]
        if non_empty:
            last = non_empty[-1]
            if ":" in last and not last.endswith(";") and not last.endswith("}"):
                errors.append(f"CSS truncated mid-declaration at EOF: '{last}'")

        # 3. Contract extraction and Selector Coverage
        contract = ComponentContractExtractor.extract(html_code)
        
        # Extract CSS selectors from CSS code
        # Strip comments first
        css_no_comments = re.sub(r"/\*[\s\S]*?\*/", "", css_code)
        # Find class selectors: e.g. .navbar, .cta-button
        css_classes = set(re.findall(r"\.([a-zA-Z0-9_\-]+)", css_no_comments))

        covered: List[str] = []
        missing: List[str] = []

        for c in contract.classes:
            if c in css_classes:
                covered.append(c)
            else:
                missing.append(c)

        total_classes = len(contract.classes)
        coverage_pct = round((len(covered) / total_classes * 100.0), 1) if total_classes > 0 else 100.0

        # Check critical layout elements (nav, hero, card, button)
        critical_keywords = ("nav", "hero", "card", "btn", "button", "header", "footer", "form")
        critical_missing = [c for c in missing if any(kw in c.lower() for kw in critical_keywords)]

        if total_classes > 5 and coverage_pct < min_coverage:
            errors.append(
                f"HTML/CSS class coverage too low: {coverage_pct}% ({len(covered)}/{total_classes} styled). "
                f"Critical missing classes: {critical_missing[:5]}"
            )
        elif critical_missing and len(critical_missing) > 5:
            warnings.append(f"High number of critical HTML classes unstyled in CSS: {critical_missing[:5]}")

        # 4. JavaScript ID check
        if js_code:
            js_no_comments = re.sub(r"/\*[\s\S]*?\*/|//.*", "", js_code)
            # Find getElementById calls
            get_id_calls = re.findall(r"getElementById\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", js_no_comments)
            html_ids = set(contract.ids)
            for req_id in get_id_calls:
                if req_id not in html_ids:
                    warnings.append(f"JavaScript targets ID '#{req_id}' which is not defined in HTML.")

        is_valid = len(errors) == 0

        return ValidationReport(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            coverage_pct=coverage_pct,
            covered_classes=covered,
            missing_classes=missing,
            unclosed_braces=unclosed_braces,
            preamble_detected=preamble_detected,
        )
