"""Robust Code Extractor for MIND Universal Studio.

Provides resilient, provider-agnostic extraction of code from LLM responses.
Handles:
- Markdown fenced code blocks (with language tags, unlabelled, or multiple blocks)
- Truncated code blocks (unclosed markdown fences)
- Conversational preambles, reasoning/thinking text, and design plans preceding code
- Trailing conversational postambles
- Syntactic truncation detection (mid-declaration cutoffs like 'border-top: 1px')
- Safe delimiter closure and heuristic repairs
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class ExtractionResult:
    """Detailed result of code extraction."""
    code: str
    is_truncated: bool = False
    stripped_preamble_lines: int = 0
    stripped_postamble_lines: int = 0
    detected_language: str = ""
    repair_notes: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        return self.code


class RobustCodeExtractor:
    """Provider-agnostic code extractor with language-aware preamble stripping and repair."""

    # Common English words/phrases typical in model conversational preambles
    _PROSE_PHRASES = (
        "here is", "here's", "below is", "certainly", "sure", "i have", "i will",
        "to achieve", "let's", "as requested", "this code", "this stylesheet",
        "design plan", "color palette", "we will", "in this section", "okay,",
        "summary of", "step 1", "step 2", "key features", "overview:", "note that",
        "we need", "we can", "we'll", "now let's", "we must", "thus we", "also include",
        "layout utilities", "feature grid", "hero layout", "mobile drawer"
    )

    @classmethod
    def extract(cls, raw_text: Optional[str], language: str = "javascript") -> ExtractionResult:
        """Extracts clean source code from raw model output for a specified target language."""
        if not raw_text or not raw_text.strip():
            return ExtractionResult(code="", detected_language=language)

        text = raw_text.strip()
        lang_lower = language.lower()

        # Step 1: Markdown code block extraction
        fenced_code, fence_truncated, detected_lang = cls._extract_fenced_block(text, lang_lower)
        working_code = fenced_code if fenced_code is not None else text

        repair_notes: List[str] = []
        is_truncated = fence_truncated
        if fence_truncated:
            repair_notes.append("Detected unclosed markdown code fence (token limit termination).")

        # Step 2: Language-aware extraction, preamble stripping, and truncation repair
        if lang_lower in ("css", "stylesheet"):
            result = cls._process_css(working_code)
        elif lang_lower in ("html", "htm", "html5"):
            result = cls._process_html(working_code)
        elif lang_lower in ("javascript", "js", "ts", "typescript"):
            result = cls._process_javascript(working_code)
        elif lang_lower == "json":
            result = cls._process_json(working_code)
        else:
            result = cls._process_generic(working_code)

        result.detected_language = detected_lang or lang_lower
        if is_truncated:
            result.is_truncated = True
        result.repair_notes.extend(repair_notes)

        return result

    @classmethod
    def _extract_fenced_block(cls, text: str, target_lang: str) -> Tuple[Optional[str], bool, str]:
        """Finds the best matching fenced code block, handling closed or unclosed fences."""
        # 1. Look for fully closed codeblocks: ```lang ... ```
        pattern = re.compile(r"```([a-zA-Z0-9_\-\+]*)\s*\n([\s\S]*?)```", re.MULTILINE)
        matches = list(pattern.finditer(text))

        lang_aliases = {
            "javascript": {"js", "javascript", "ts", "typescript"},
            "css": {"css", "stylesheet", "style"},
            "html": {"html", "htm", "html5"},
            "json": {"json"},
            "python": {"py", "python"},
        }
        target_aliases = lang_aliases.get(target_lang, {target_lang})

        # If matching language tag found among closed blocks
        for match in matches:
            block_lang = (match.group(1) or "").strip().lower()
            if block_lang in target_aliases:
                return match.group(2).strip(), False, block_lang

        # 2. Check for unclosed codeblock at the end of text (truncated by token limit)
        unclosed_match = re.search(r"```([a-zA-Z0-9_\-\+]*)\s*\n([\s\S]*)$", text)
        if unclosed_match and not matches:
            block_lang = (unclosed_match.group(1) or "").strip().lower()
            content_after = unclosed_match.group(2).strip()
            content_before = text[:unclosed_match.start()].strip()

            # Check if this single ``` was actually a closing fence for code preceding it
            if target_lang in ("css", "stylesheet"):
                before_has_code = "{" in content_before and "}" in content_before
                after_has_code = "{" in content_after
                if before_has_code and not after_has_code:
                    return content_before, False, ""
            elif target_lang in ("html", "htm", "html5"):
                before_has_code = "<" in content_before and ">" in content_before
                after_has_code = "<" in content_after
                if before_has_code and not after_has_code:
                    return content_before, False, ""
            elif target_lang in ("javascript", "js"):
                before_has_code = ("{" in content_before or ";" in content_before)
                after_has_code = ("{" in content_after or ";" in content_after)
                if before_has_code and not after_has_code:
                    return content_before, False, ""

            # Truly unclosed opening fence
            if block_lang in target_aliases or not block_lang:
                return content_after, True, block_lang

        # 3. If closed blocks exist but no language match, pick the largest block
        if matches:
            largest = max(matches, key=lambda m: len(m.group(2)))
            return largest.group(2).strip(), False, (largest.group(1) or "").strip().lower()

        # No fenced block found
        return None, False, ""

    @classmethod
    def _process_css(cls, text: str) -> ExtractionResult:
        """Preamble stripping, selector detection, and truncation repair for CSS."""
        lines = text.splitlines()
        code_start_idx = -1
        stripped_preamble_lines = 0

        css_selector_start = re.compile(
            r"^(\s*(:root|html|body|\*|@media|@keyframes|@import|@font-face|@layer|[.#a-zA-Z0-9_\-\*\[\]=\"':,\s]+)\s*\{)",
            re.IGNORECASE
        )

        # First priority: check for explicit global root selector (:root {)
        root_pattern = re.compile(r"^\s*:root\s*\{", re.MULTILINE)
        root_match = root_pattern.search(text)
        if root_match:
            char_idx = root_match.start()
            code_start_idx = text[:char_idx].count("\n")
            stripped_preamble_lines = code_start_idx
            lines = lines[code_start_idx:]
        else:
            for i, line in enumerate(lines):
                stripped = line.strip()
                if not stripped:
                    continue

                # Skip bullet points or numbered list items (e.g. "1. :root", "7. Hero layout:")
                if re.match(r"^(\d+[\.\)]|\-|\*)\s+", stripped):
                    continue

                # Verify it's not conversational prose
                lower = stripped.lower()
                if any(lower.startswith(phrase) for phrase in cls._PROSE_PHRASES):
                    continue

                # Words like "We", "I", "Let's" indicate reasoning prose
                first_word = re.split(r"[\s\:\,\.]+", lower)[0]
                if first_word in ("we", "i", "you", "let's", "now", "here", "below", "also", "then", "thus"):
                    continue

                # Check if line looks like pure CSS start
                if (
                    stripped.startswith("/*")
                    or stripped.startswith("@media")
                    or stripped.startswith("@keyframes")
                    or stripped.startswith("@import")
                    or stripped.startswith("@font-face")
                    or stripped.startswith("*")
                    or css_selector_start.match(stripped)
                ):
                    code_start_idx = i
                    break

            if code_start_idx > 0:
                stripped_preamble_lines = code_start_idx
                lines = lines[code_start_idx:]
            elif code_start_idx == -1:
                # Fallback: find first occurrence of '{'
                for i, line in enumerate(lines):
                    if "{" in line:
                        stripped_preamble_lines = i
                        lines = lines[i:]
                        break

        clean_text = "\n".join(lines).strip()
        repair_notes: List[str] = []
        is_truncated = False

        # Detect and repair postambles and incomplete trailing declarations
        # e.g., line ending with "border-top: 1px" without semicolon, value, or closing brace
        lines = clean_text.splitlines()
        while lines:
            last_line = lines[-1].strip()
            if not last_line:
                lines.pop()
                continue

            # If last line contains prose / conversation
            last_lower = last_line.lower()
            if any(last_lower.startswith(p) for p in cls._PROSE_PHRASES) or "```" in last_line:
                lines.pop()
                repair_notes.append(f"Stripped conversational postamble: '{last_line[:30]}...'")
                continue

            # Check for incomplete CSS declaration
            # Matches: "prop: value" without ';' or '}' or trailing incomplete like "border-top: 1px"
            if ":" in last_line and not last_line.endswith(";") and not last_line.endswith("}") and not "{" in last_line:
                is_truncated = True
                repair_notes.append(f"Removed truncated declaration: '{last_line}'")
                lines.pop()
                continue
            # Matches trailing property name without colon e.g. "border-"
            if re.match(r"^[a-zA-Z\-]+\s*$", last_line):
                is_truncated = True
                repair_notes.append(f"Removed truncated property name: '{last_line}'")
                lines.pop()
                continue

            break

        repaired_text = "\n".join(lines)

        # Brace balancing check & repair
        open_curlies = repaired_text.count("{")
        close_curlies = repaired_text.count("}")

        if open_curlies > close_curlies:
            is_truncated = True
            missing = open_curlies - close_curlies
            repaired_text = repaired_text.rstrip() + ("\n}" * missing)
            repair_notes.append(f"Balanced {missing} unclosed CSS ruleset brace(s).")

        return ExtractionResult(
            code=repaired_text.strip(),
            is_truncated=is_truncated,
            stripped_preamble_lines=stripped_preamble_lines,
            detected_language="css",
            repair_notes=repair_notes,
        )

    @classmethod
    def _process_html(cls, text: str) -> ExtractionResult:
        """Preamble stripping, structural boundary detection, and repair for HTML."""
        repair_notes: List[str] = []
        stripped_preamble_lines = 0
        is_truncated = False

        # Locate beginning of HTML document
        doctype_idx = text.lower().find("<!doctype html")
        html_idx = text.lower().find("<html")

        start_idx = doctype_idx if doctype_idx != -1 else html_idx
        if start_idx == -1:
            # Look for head or body
            start_idx = text.lower().find("<body")

        if start_idx > 0:
            preamble = text[:start_idx]
            stripped_preamble_lines = len(preamble.splitlines())
            text = text[start_idx:]
            repair_notes.append(f"Stripped {stripped_preamble_lines} lines of HTML preamble.")

        # Locate end of HTML document
        close_html_idx = text.lower().rfind("</html>")
        if close_html_idx != -1:
            text = text[: close_html_idx + len("</html>")]
        else:
            # Document truncated before </html>
            is_truncated = True
            repair_notes.append("Missing </html> tag. Appended closing tags.")
            if "</body>" not in text.lower():
                text = text.rstrip() + "\n</body>\n</html>"
            else:
                text = text.rstrip() + "\n</html>"

        return ExtractionResult(
            code=text.strip(),
            is_truncated=is_truncated,
            stripped_preamble_lines=stripped_preamble_lines,
            detected_language="html",
            repair_notes=repair_notes,
        )

    @classmethod
    def _process_javascript(cls, text: str) -> ExtractionResult:
        """Preamble stripping and syntax balancing for JavaScript."""
        lines = text.splitlines()
        code_start_idx = -1
        stripped_preamble_lines = 0

        js_lead_keywords = (
            "import ", "export ", "const ", "let ", "var ", "function ", "class ",
            "document.", "window.", "console.", "(function", "$(document", "addEventListener",
            "//", "/*", "\"use strict\";", "'use strict';"
        )

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if any(stripped.startswith(kw) for kw in js_lead_keywords):
                code_start_idx = i
                break

        if code_start_idx > 0:
            stripped_preamble_lines = code_start_idx
            lines = lines[code_start_idx:]

        clean_text = "\n".join(lines).strip()
        repair_notes: List[str] = []
        is_truncated = False

        # Detect unclosed braces or parentheses
        open_curlies = clean_text.count("{")
        close_curlies = clean_text.count("}")
        open_parens = clean_text.count("(")
        close_parens = clean_text.count(")")

        if open_curlies > close_curlies or open_parens > close_parens:
            is_truncated = True
            if open_parens > close_parens:
                clean_text = clean_text.rstrip() + (")" * (open_parens - close_parens))
                repair_notes.append(f"Balanced {open_parens - close_parens} unclosed parenthesis.")
            if open_curlies > close_curlies:
                clean_text = clean_text.rstrip() + ("\n}" * (open_curlies - close_curlies))
                repair_notes.append(f"Balanced {open_curlies - close_curlies} unclosed curly brace(s).")

        return ExtractionResult(
            code=clean_text.strip(),
            is_truncated=is_truncated,
            stripped_preamble_lines=stripped_preamble_lines,
            detected_language="javascript",
            repair_notes=repair_notes,
        )

    @classmethod
    def _process_json(cls, text: str) -> ExtractionResult:
        """Extracts JSON object or array."""
        start_obj = text.find("{")
        start_arr = text.find("[")

        if start_obj == -1 and start_arr == -1:
            return ExtractionResult(code=text.strip(), detected_language="json")

        if start_arr != -1 and (start_obj == -1 or start_arr < start_obj):
            start = start_arr
            end = text.rfind("]")
            end = end + 1 if end != -1 else len(text)
        else:
            start = start_obj
            end = text.rfind("}")
            end = end + 1 if end != -1 else len(text)

        code = text[start:end].strip()
        return ExtractionResult(
            code=code,
            is_truncated=(end == len(text)),
            detected_language="json"
        )

    @classmethod
    def _process_generic(cls, text: str) -> ExtractionResult:
        return ExtractionResult(code=text.strip())
