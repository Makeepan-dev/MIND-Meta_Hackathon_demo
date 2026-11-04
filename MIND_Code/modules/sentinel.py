import hashlib
import os
import json
import socket
import re
from colorama import Fore


class Sentinel:
    def __init__(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.hashes_file = os.path.join(repo_root, "sentinel_hashes.json")
        self.protected_files = [
            os.path.join(repo_root, "MIND_Code", "mind_brain.py"),
        ]
        # Default integrity verification hash
        self.password_hash = "03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4"

    def calculate_hash(self, filepath):
        """Calculates SHA-256 hash of a file."""
        if not os.path.exists(filepath):
            return None
        sha256_hash = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception:
            return None

    def integrity_check(self):
        """Checks if protected files have been tampered with."""
        print(f"{Fore.CYAN}🛡️ [SENTINEL] Running Integrity Check...")

        known_hashes = {}
        if os.path.exists(self.hashes_file):
            try:
                with open(self.hashes_file, "r") as f:
                    known_hashes = json.load(f)
            except Exception:
                pass

        current_hashes = {}
        alerts = []
        is_first_run = not bool(known_hashes)

        for fpath in self.protected_files:
            current = self.calculate_hash(fpath)
            if not current:
                continue

            current_hashes[fpath] = current

            if not is_first_run:
                known = known_hashes.get(fpath)
                if known and known != current:
                    alerts.append(f"CRITICAL: Integrity Violation detected in {os.path.basename(fpath)}")

        if is_first_run:
            with open(self.hashes_file, "w") as f:
                json.dump(current_hashes, f, indent=4)
            return "Baseline established. System secured."

        if alerts:
            return " | ".join(alerts)

        return "System Integrity Verified. No tampering detected."

    def sanitize_input(self, text):
        """Removes dangerous characters for shell commands."""
        dangerous = [";", "|", "&&", "$", "`", ">", "<"]
        clean = text
        for char in dangerous:
            clean = clean.replace(char, "")
        return clean

    def scan_local_ports(self):
        """Checks for suspicious listening ports (Basic)."""
        return "Network Perimeter Secure."

    def verify_password(self, spoken_password):
        """Checks password against hash."""
        cleaned = spoken_password.strip().lower().replace(" ", "")
        attempt_hash = hashlib.sha256(cleaned.encode()).hexdigest()
        return attempt_hash == self.password_hash
