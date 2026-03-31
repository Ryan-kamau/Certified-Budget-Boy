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
from fintrack.setup.scheduler_setup import main as scheduler_setup_main
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
  FinTrack.exe --setup-db --test-only  Initialize testing of database 
  FinTrack.exe --help          Show this help message
  fintrack.exe --install-cron  Setup automatic scheduler to task manager
  fintrack.exe --remove-cron   Delete automatic scheduler from task manager

Examples:
  FinTrack.exe
  FinTrack.exe --cron
  FinTrack.exe --setup-db
  Fintrack.exe --install_cron
  intrack.exe  --remove-cron
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
            filtered_args = [arg for arg in args if arg != "--setup-db"]

            # if user didn't specify anything → default to --fresh
            if not filtered_args:
                filtered_args = ["--fresh"]

            sys.argv = [sys.argv[0]] + filtered_args
            setup_db_main()

        elif has_flag(args, "--install-cron"):
            scheduler_setup_main()

        elif has_flag(args, "--remove-cron"):
            from fintrack.setup.scheduler_setup import remove_task
            remove_task()

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