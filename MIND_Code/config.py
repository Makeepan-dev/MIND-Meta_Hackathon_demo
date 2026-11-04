import os
import warnings
import queue
import threading

# --- 1. SYSTEM SETTINGS ---
warnings.filterwarnings("ignore")
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

# --- 2. PATHS (THE NERVOUS SYSTEM) ---
# Main Directory (dynamically resolved to repository root)
MIND_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_PATH = MIND_PATH # Alias for compatibility
ROOT_DIR = MIND_PATH # Alias for Sentinel compatibility

# Sub-directories
WORKSPACE = os.path.join(MIND_PATH, "Workspace")
ASSETS_DIR = os.path.join(MIND_PATH, "assets")
OSINT_DIR = os.path.join(MIND_PATH, "osint_reports")

# Specific Files
LOG_FILE = os.path.join(MIND_PATH, "session_log.json")
CORE_VOICE_FILE = os.path.join(ASSETS_DIR, "system_core.wav")
OUTPUT_AUDIO_FILE = os.path.join(ASSETS_DIR, "mind_response.wav")
TEMP_INPUT_AUDIO = os.path.join(MIND_PATH, "temp_input.wav")

# External Storage
DEFAULT_PROJECTS_DIR = WORKSPACE
PROJECTS_ROOT = DEFAULT_PROJECTS_DIR # Alias

# --- 3. GO / TOOLS CONFIGURATION ---
os.environ["GOROOT"] = os.path.join(MIND_PATH, "Go")
os.environ["GOPATH"] = os.path.join(MIND_PATH, "go-workspace")
# Add Go to PATH so subprocess can find 'nmap' without full paths if needed
os.environ["PATH"] += os.pathsep + os.path.join(os.environ["GOROOT"], "bin")

# --- 4. APP REGISTRY (THE HANDS) ---
APP_LIBRARY = {
    "notepad": "notepad.exe",
    "chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "vs code": "code",
    "calc": "calc.exe",
    "cmd": "cmd.exe",
}

# --- 5. GLOBAL NERVOUS SYSTEM (THE SIGNALS) ---
# These allow modules to talk to the Main Loop without circular imports
exit_event = threading.Event()       # Signals shutdown
is_speaking = threading.Event()      # Prevents listening while talking
speech_queue = queue.Queue()         # Agents put text here -> Main speaks it
hud_queue = queue.Queue()            # Agents put text here -> HUD displays it
last_spoken_phrase = ""              

# --- 6. AUTO-INITIALIZATION ---
def verify_system_paths():
    """Creates necessary folders if they don't exist."""
    required_folders = [ASSETS_DIR, WORKSPACE]
    for folder in required_folders:
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)

# Run verification immediately on import
verify_system_paths()