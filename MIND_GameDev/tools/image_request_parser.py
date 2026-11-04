"""
MIND Structured Image Request Parser
Robust natural-language extraction of visual image prompts, destination paths,
and custom filenames across all entry points (modal, chat, compound).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class StructuredImageRequest:
    raw_input: str
    image_prompt: str
    destination_path: Optional[str] = None
    filename: Optional[str] = None
    format: str = "png"
    drive_letter: Optional[str] = None
    folder_name: Optional[str] = None


def sanitize_filename(filename: Optional[str]) -> Optional[str]:
    """Ensures filename is a secure base filename, preventing directory traversal."""
    if not filename:
        return None
    clean = os.path.basename(filename.strip().replace("/", "\\"))
    clean = re.sub(r'[<>:"/\\|?*]', '', clean)
    clean = clean.strip(". ")
    if not clean:
        return None
    if not clean.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        clean = f"{clean}.png"
    return clean


def parse_image_request(
    raw_text: str,
    explicit_dest: Optional[str] = None,
    explicit_filename: Optional[str] = None
) -> StructuredImageRequest:
    """
    Parses a user instruction into a clean visual prompt and filesystem destination.
    Preserves visual descriptions while extracting drive, folder, and filename instructions.
    """
    text_clean = (raw_text or "").strip()

    # 1. Check if an explicit destination was supplied (e.g. from UI input field)
    dest_path = os.path.normpath(explicit_dest.strip()) if explicit_dest and explicit_dest.strip() else None
    req_filename = sanitize_filename(explicit_filename)

    # 2. Identify the filesystem action clause
    fs_clause = ""
    prompt_clause = text_clean

    # Search for filesystem directives
    fs_match = re.search(
        r'(?:and\s+|,\s*|\.\s*|\n\s*)?(?:please\s+)?(?:save|store|put|export|write|create\s+(?:a\s+)?folder)\s+(?:the\s+)?(?:generated\s+)?(?:image|picture|file|it)?\s*.*$',
        text_clean,
        re.I
    )

    if fs_match:
        matched_str = fs_match.group(0)
        # Verify it contains filesystem-related keywords
        if re.search(r'(?:[A-Za-z]:|[A-Za-z]\s+drive|folder|directory|path|\.png|\.jpg)', matched_str, re.I):
            fs_clause = matched_str
            prompt_clause = text_clean[:fs_match.start()].strip()

    # 3. Clean the visual prompt
    # Strip command prefixes (including leading 'and', 'also', 'please')
    clean_prompt = re.sub(
        r'^(?:(?:and|also|please)\s+)?(?:/image\s+|(?:generate|create|draw|synthesize|make|render)\s+(?:an?\s+)?(?:matching\s+)?(?:image\s+of\s+|picture\s+of\s+|concept\s+art\s+of\s+|illustration\s+of\s+|artwork\s+of\s+)|(?:generate|create|draw|synthesize|make|render)\s+(?:an?\s+)?(?:matching\s+)?|(?:matching\s+)?(?:image|artwork|illustration|concept art)\s+(?:of\s+)?)',
        '',
        prompt_clause,
        flags=re.IGNORECASE
    ).strip()

    # Strip trailing concurrent markers like 'at the same time', 'simultaneously'
    clean_prompt = re.sub(r'\b(?:at the same time|concurrently|simultaneously)\b', '', clean_prompt, flags=re.I).strip()
    clean_prompt = re.sub(r'^(?:of\s+)', '', clean_prompt, flags=re.I).strip()
    clean_prompt = re.sub(r'[.,;]$', '', clean_prompt).strip()
    clean_prompt = re.sub(r'\s{2,}', ' ', clean_prompt).strip()

    if clean_prompt and len(clean_prompt) > 0 and clean_prompt[0].islower():
        clean_prompt = clean_prompt[0].upper() + clean_prompt[1:]

    if not clean_prompt:
        clean_prompt = "Stylized concept art"

    # 4. Extract destination from fs_clause if not explicitly provided
    drive_letter = None
    folder_name = None

    if not dest_path and fs_clause:
        # Check Pattern A: Explicit Windows path (e.g. "E:\AI images\dragon.png" or "E:\AI images")
        m_path = re.search(
            r'([A-Za-z]:\\[^"\'<>|\n\r]+?)(?=\s+(?:with|and|using|as)|[.,;]?$)',
            fs_clause,
            re.I
        )
        if m_path:
            p_val = m_path.group(1).strip().rstrip('.')
            drive_letter = p_val[:2].upper()
            if re.search(r'\.(?:png|jpg|jpeg|webp)$', p_val, re.I):
                dest_path = os.path.dirname(p_val)
                if not req_filename:
                    req_filename = sanitize_filename(os.path.basename(p_val))
            else:
                dest_path = p_val
        else:
            # Check Pattern B: Drive letter + Folder name
            m_drv = re.search(r'(?:in|on|to|inside|at)?\s*([A-Za-z])\s*(?::|:\s*\\|\s+drive)', fs_clause, re.I)
            m_fld = re.search(
                r'(?:folder\s+name|name\s+as|name|folder\s+named|folder\s+called|named\s+folder|folder)\s+[\'"]?([A-Za-z0-9_\- ]+?)[\'"]?(?:\s+(?:on|in|with|and|using|as)|[.,;]?$)',
                fs_clause,
                re.I
            )

            if m_drv:
                drive_letter = m_drv.group(1).upper()
                if m_fld:
                    folder_name = m_fld.group(1).strip().rstrip(" .")
                    dest_path = f"{drive_letter}:\\{folder_name}"
                else:
                    dest_path = f"{drive_letter}:\\"

    # 5. Extract filename if not already set
    if not req_filename and fs_clause:
        m_fn = re.search(
            r'(?:using\s+(?:the\s+)?filename|with\s+(?:the\s+)?filename|filename|name\s+the\s+file|named\s+file|as)\s+[\'"]?([A-Za-z0-9_\- \.]+?)[\'"]?(?:\s|[.,;]?$)',
            fs_clause,
            re.I
        )
        if m_fn:
            req_filename = sanitize_filename(m_fn.group(1))

    # Normalize destination path if set
    if dest_path:
        dest_path = os.path.normpath(dest_path)
        if len(dest_path) == 2 and dest_path[1] == ':':
            dest_path += "\\"

    return StructuredImageRequest(
        raw_input=raw_text,
        image_prompt=clean_prompt,
        destination_path=dest_path,
        filename=req_filename,
        format="png",
        drive_letter=drive_letter,
        folder_name=folder_name
    )
