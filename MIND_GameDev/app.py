"""
MIND Universal Development Studio — Command-Line Interface and Interactive Application.
Allows users to create, verify, modify, test, and serve software projects
(websites, web applications, backend APIs, mobile, desktop, games, automations) via voice or text.
"""

import sys
import argparse
from typing import Optional

from .config import GameDevConfig
from .models import ProjectType
from .orchestrator import GameDevOrchestrator


def parse_args():
    parser = argparse.ArgumentParser(
        description="MIND Universal Development Studio — Autonomous Cross-Domain Software Creation",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--create",
        type=str,
        nargs="?",
        const="Create 3D endless runner",
        help="Create a software project based on description",
    )
    parser.add_argument(
        "--type",
        type=str,
        choices=["website", "web_app", "backend_api", "mobile_app", "desktop_app", "game", "automation", "custom"],
        default=None,
        help="Explicit project workflow type (if omitted, type is inferred from description)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run static verification and automated tests on current project",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Host web-capable project on local HTTP server and open browser",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for local HTTP server",
    )
    parser.add_argument(
        "--no-voice",
        action="store_true",
        help="Disable spoken voice output synthesis",
    )
    parser.add_argument(
        "--providers",
        "--diagnostics",
        action="store_true",
        help="Inspect live operational readiness of all free AI providers without spending credits",
    )
    parser.add_argument(
        "--dest",
        "--destination",
        type=str,
        default=None,
        help="Explicit destination directory for project creation or file operations",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Explicit project name",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force overwrite existing destination or confirm destructive operations",
    )
    parser.add_argument(
        "--listen",
        action="store_true",
        help="Use microphone voice intake for commands",
    )
    parser.add_argument(
        "--gui",
        "--desktop",
        action="store_true",
        help="Launch the complete JARVIS-inspired desktop application GUI",
    )
    return parser.parse_args()


def interactive_session(orchestrator: GameDevOrchestrator, listen_mic: bool = False):
    print("\n" + "=" * 65)
    print("      MIND UNIVERSAL STUDIO — AUTONOMOUS SOFTWARE BUILDER        ")
    print("=" * 65)
    print("Supported Project Domains:")
    print("  • Websites (responsive multi-page HTML5/CSS3/JS)")
    print("  • Web Applications (interactive single-page dashboards)")
    print("  • Backend APIs (FastAPI microservices with automated tests)")
    print("  • Desktop Utilities (Python Tkinter system diagnostic tools)")
    print("  • 3D Games (Three.js WebGL playable runners)")
    print("  • Automations & CLI Processors")
    print("  • Mobile Apps (Android Gradle / Kotlin architectures)")
    print("-" * 65)
    print("Commands:")
    print("  'create <description>' -> Generate new project & assets")
    print("  'verify'               -> Run verification & unit tests")
    print("  'serve' / 'play'       -> Start local server & launch browser")
    print("  'quit' / 'exit'        -> Exit application")
    print("-" * 65)

    while True:
        try:
            if listen_mic:
                cmd = orchestrator.voice_in.listen_or_input(
                    prompt="\n[Voice/Text Command] > "
                )
            else:
                cmd = input("\n[Universal Studio] > ").strip()

            if not cmd:
                continue

            if cmd.lower() in ("quit", "exit", "q"):
                print("Exiting MIND Universal Studio. Goodbye.")
                break

            result = orchestrator.execute_command(cmd, auto_open_browser=True)
            status = result.get('status')
            if status == "CLARIFY":
                print(f"\n[MIND Clarification Needed]: {result.get('message')}")
            elif status == "CONFIRMATION_REQUIRED":
                print(f"\n[MIND Confirmation Required]: {result.get('message')}")
            else:
                print(f"Status: {status} [{result.get('project_type', '').upper()}]")
                if "entry_point" in result:
                    print(f"Entry Point: {result.get('entry_point')}")
                if "url" in result:
                    print(f"Active URL: {result.get('url')}")
                if "run_command" in result and result.get("run_command"):
                    print(f"Run Command: {result.get('run_command')}")

        except (KeyboardInterrupt, EOFError):
            print("\nExiting MIND Universal Studio.")
            break


def main():
    args = parse_args()
    config = GameDevConfig.load()

    if args.providers:
        from .providers import ProviderDiagnostics
        diag = ProviderDiagnostics(config)
        diag.print_diagnostics()
        return

    orchestrator = GameDevOrchestrator(config=config, enable_voice=not args.no_voice)

    if args.create:
        create_cmd = args.create
        if args.dest and "save" not in create_cmd and "in " not in create_cmd:
            create_cmd += f", save the project to {args.dest}"
        if args.name and "name it" not in create_cmd and "call it" not in create_cmd:
            create_cmd += f", and name it {args.name}"
        if args.force and "--force" not in create_cmd and "confirm" not in create_cmd:
            create_cmd += " --force"

        print(f"\n[MIND Studio] Creating project from command: '{create_cmd}'")
        res = orchestrator.execute_command(
            create_cmd,
            project_type=args.type,
            auto_open_browser=False,
        )
        if res.get("status") == "CLARIFY":
            print(f"\n[MIND Clarification Needed]: {res.get('message')}")
            return
        if res.get("status") == "CONFIRMATION_REQUIRED":
            print(f"\n[MIND Confirmation Required]: {res.get('message')}")
            return

        if args.serve and res.get("status") == "SUCCESS":
            orchestrator.serve_project(port=args.port, open_browser=True)
            print("Press Ctrl+C to stop local server.")
            try:
                import time
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nServer stopped.")
        return

    if args.verify:
        res = orchestrator.execute_command("verify")
        print("\nVerification Results:")
        import pprint
        pprint.pprint(res)
        return

    if args.serve:
        res = orchestrator.serve_project(port=args.port, open_browser=True)
        print(f"\nProject server online: {res.get('url')}")
        print("Press Ctrl+C to stop local server.")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nServer stopped.")
        return

    if getattr(args, "gui", False):
        try:
            from PyQt6.QtWidgets import QApplication
            from .ui.main_window import MINDMainWindow
            app = QApplication.instance() or QApplication(sys.argv)
            win = MINDMainWindow()
            win.show()
            sys.exit(app.exec())
        except Exception as e:
            print(f"[ERROR] Failed to start GUI: {e}")
            return

    # Interactive loop
    interactive_session(orchestrator, listen_mic=args.listen)


if __name__ == "__main__":
    main()
