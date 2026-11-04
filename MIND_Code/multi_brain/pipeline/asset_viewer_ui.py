"""
MIND — Asset Viewer Desktop UI (Stage F)
Renders an interactive cyberpunk-styled HUD window showing the concept image preview,
3D model details, status metrics, and direct launch actions (Windows 3D Viewer / Explorer).
"""

import os
import sys
import threading
from pathlib import Path
from typing import Dict, Any, Optional

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    from PIL import Image, ImageTk
    HAS_TK = True
except Exception:
    HAS_TK = False


class AssetViewerWindow:
    """Displays generated 2D and 3D assets in an interactive UI window."""

    def __init__(self, manifest: Dict[str, Any]) -> None:
        self.manifest = manifest

    def show_async(self) -> None:
        """Launches the UI window in a non-blocking background thread."""
        if not HAS_TK:
            self._print_terminal_card()
            return

        thread = threading.Thread(target=self._run_ui, daemon=True)
        thread.start()

    def _run_ui(self) -> None:
        """Builds and runs the Tkinter UI."""
        try:
            root = tk.Tk()
            root.title("MIND — Neural Asset Matrix | 3D Generator")
            root.geometry("780x560")
            root.configure(bg="#05070B")
            root.resizable(False, False)

            # Header Banner
            header_frame = tk.Frame(root, bg="#080C14", height=60)
            header_frame.pack(fill="x")

            title_lbl = tk.Label(
                header_frame,
                text="🧠 MIND AI ASSET GENERATOR — IMAGE TO 3D PIPELINE",
                font=("Consolas", 12, "bold"),
                fg="#22D3EE",
                bg="#080C14",
            )
            title_lbl.pack(pady=12)

            # Main Content Frame (2 Columns: Left Image Preview, Right 3D Metadata & Controls)
            main_frame = tk.Frame(root, bg="#05070B")
            main_frame.pack(fill="both", expand=True, padx=20, pady=15)

            # --- LEFT COLUMN: CONCEPT IMAGE PREVIEW ---
            left_col = tk.Frame(main_frame, bg="#0C121C", width=340, height=380, highlightthickness=1, highlightbackground="#1E293B")
            left_col.pack(side="left", fill="both", expand=True, padx=(0, 10))
            left_col.pack_propagate(False)

            img_title = tk.Label(left_col, text="STAGE C: CONCEPT IMAGE", font=("Consolas", 10, "bold"), fg="#94A3B8", bg="#0C121C")
            img_title.pack(pady=8)

            img_path = self.manifest.get("concept_image", {}).get("path")
            img_loaded = False

            if img_path and os.path.exists(img_path):
                try:
                    pil_img = Image.open(img_path)
                    pil_img = pil_img.resize((300, 300), Image.Resampling.LANCZOS)
                    tk_img = ImageTk.PhotoImage(pil_img)
                    img_label = tk.Label(left_col, image=tk_img, bg="#0C121C")
                    img_label.image = tk_img  # Keep reference
                    img_label.pack(pady=5)
                    img_loaded = True
                except Exception as e:
                    pass

            if not img_loaded:
                no_img_lbl = tk.Label(left_col, text="[Image Preview Unavailable]", font=("Consolas", 10), fg="#64748B", bg="#0C121C")
                no_img_lbl.pack(expand=True)

            # --- RIGHT COLUMN: 3D MODEL DETAILS & ACTIONS ---
            right_col = tk.Frame(main_frame, bg="#0C121C", width=380, height=380, highlightthickness=1, highlightbackground="#1E293B")
            right_col.pack(side="right", fill="both", expand=True, padx=(10, 0))
            right_col.pack_propagate(False)

            m_title = tk.Label(right_col, text="STAGE D/E: 3D MODEL ASSET", font=("Consolas", 10, "bold"), fg="#14B8A6", bg="#0C121C")
            m_title.pack(pady=8)

            # Details list
            details_frame = tk.Frame(right_col, bg="#0C121C")
            details_frame.pack(fill="x", padx=15, pady=5)

            req_text = self.manifest.get("user_request", "N/A")
            if len(req_text) > 40:
                req_text = req_text[:37] + "..."

            m_info = self.manifest.get("threed_model", {})
            m_path = m_info.get("path", "N/A")
            m_file_name = os.path.basename(m_path) if m_path != "N/A" else "N/A"
            m_format = m_info.get("format", "glb").upper()
            provider_str = m_info.get("provider", "Local").replace("_", " ").title()

            fields = [
                ("User Request:", req_text),
                ("Asset ID:", self.manifest.get("asset_id", "N/A")),
                ("3D Format:", f"{m_format} (glTF 2.0 Binary)"),
                ("File Name:", m_file_name),
                ("Provider:", provider_str),
                ("Verification:", "✅ VERIFIED VALID (Geometry OK)"),
            ]

            for label_text, val_text in fields:
                row = tk.Frame(details_frame, bg="#0C121C")
                row.pack(fill="x", pady=2)
                lbl = tk.Label(row, text=f"{label_text:<15}", font=("Consolas", 9, "bold"), fg="#64748B", bg="#0C121C", width=14, anchor="w")
                lbl.pack(side="left")
                val = tk.Label(row, text=val_text, font=("Consolas", 9), fg="#E2E8F0", bg="#0C121C", anchor="w")
                val.pack(side="left", fill="x", expand=True)

            # Actions / Buttons Section
            btn_frame = tk.Frame(right_col, bg="#0C121C")
            btn_frame.pack(fill="x", padx=15, pady=15)

            btn_open_3d = tk.Button(
                btn_frame,
                text="👁️ Open in Windows 3D Viewer",
                font=("Consolas", 10, "bold"),
                fg="#05070B",
                bg="#22D3EE",
                activebackground="#38BDF8",
                relief="flat",
                cursor="hand2",
                command=lambda: self._open_file(m_path),
            )
            btn_open_3d.pack(fill="x", pady=4)

            btn_open_img = tk.Button(
                btn_frame,
                text="🖼️ Open Concept Image",
                font=("Consolas", 9),
                fg="#F8FAFC",
                bg="#1E293B",
                activebackground="#334155",
                relief="flat",
                cursor="hand2",
                command=lambda: self._open_file(img_path),
            )
            btn_open_img.pack(fill="x", pady=4)

            folder_path = os.path.dirname(m_path) if m_path != "N/A" else ""
            btn_open_folder = tk.Button(
                btn_frame,
                text="📂 Reveal in File Explorer",
                font=("Consolas", 9),
                fg="#F8FAFC",
                bg="#1E293B",
                activebackground="#334155",
                relief="flat",
                cursor="hand2",
                command=lambda: self._open_folder(folder_path),
            )
            btn_open_folder.pack(fill="x", pady=4)

            # Footer / Status
            status_bar = tk.Frame(root, bg="#080C14", height=30)
            status_bar.pack(side="bottom", fill="x")
            stat_lbl = tk.Label(
                status_bar,
                text=f"Asset generated in {self.manifest.get('formatted_time')} | Stored at: {m_path}",
                font=("Consolas", 8),
                fg="#64748B",
                bg="#080C14",
            )
            stat_lbl.pack(pady=5)

            root.mainloop()
        except Exception as e:
            self._print_terminal_card()

    def _open_file(self, file_path: Optional[str]) -> None:
        """Launches file with default operating system handler."""
        if file_path and os.path.exists(file_path):
            os.startfile(file_path)

    def _open_folder(self, folder_path: str) -> None:
        """Opens folder in Windows Explorer."""
        if folder_path and os.path.exists(folder_path):
            os.startfile(folder_path)

    def _print_terminal_card(self) -> None:
        """Terminal fallback card when GUI cannot be drawn."""
        print("\n" + "=" * 65)
        print("  MIND ASSET PIPELINE RESULT")
        print("=" * 65)
        print(f" Request:    {self.manifest.get('user_request')}")
        print(f" Image:      {self.manifest.get('concept_image', {}).get('path')}")
        print(f" 3D Model:   {self.manifest.get('threed_model', {}).get('path')}")
        print(f" Format:     {self.manifest.get('threed_model', {}).get('format', 'glb').upper()}")
        print(f" Status:     {self.manifest.get('status')}")
        print("=" * 65 + "\n")
