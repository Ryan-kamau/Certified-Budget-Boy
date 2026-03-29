# fintrack/main.py
"""
============================================================
 FinTrack — Unified Entry Point
------------------------------------------------------------
Routes execution based on CLI arguments:

  FinTrack.exe                → Launch main app
  FinTrack.exe --cron         → Run background jobs
  FinTrack.exe --setup-db     → Initialize database
  FinTrack.exe --help         → Show usage

This design allows:
  • Single EXE for everything
  • Easy Task Scheduler integration
  • Clean separation of concerns
============================================================
"""

import sys
from typing import List

# ── Core entry points ─────────────────────────────────────────

from fintrack.app import main as app_main
from fintrack.cron.cron_runner import main as cron_main
from fintrack.setup.db_setup import main as setup_db_main


# ── CLI Helpers ──────────────────────────────────────────────

def print_help() -> None:
    print(
        """
FinTrack — Personal Finance Tracker

Usage:
  FinTrack.exe                 Run the main application
  FinTrack.exe --cron          Run scheduled background jobs
  FinTrack.exe --setup-db      Initialize database (first-time setup)
  FinTrack.exe --help          Show this help message

Examples:
  FinTrack.exe
  FinTrack.exe --cron
  FinTrack.exe --setup-db
"""
    )


def has_flag(args: List[str], flag: str) -> bool:
    return flag in args


# ── Main Router ──────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]

    try:
        if not args:
            # Default → launch main app
            app_main()

        elif has_flag(args, "--help") or has_flag(args, "-h"):
            print_help()

        elif has_flag(args, "--cron"):
            cron_main()

        elif has_flag(args, "--setup-db"):
            setup_db_main()

        else:
            print(f"[ERROR] Unknown argument(s): {' '.join(args)}")
            print("Use --help to see available options.")
            sys.exit(1)

    except Exception as e:
        # Global safety net (your custom exceptions will still bubble nicely)
        print(f"[FATAL] Unexpected error: {e}")
        sys.exit(1)


# ── Entry guard ──────────────────────────────────────────────

if __name__ == "__main__":
    main()