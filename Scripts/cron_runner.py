"""
============================================================
 FinTrack Cron Runner
 ------------------------------------------------------------
 Runs all automated background jobs for every active user:

   1. Recurring Transactions  — executes any rules that are
                                now due (Scheduler.run_all_due_recurring)
   2. Goal Status Updates     — auto-transitions active goals
                                that have been completed/failed
                                (GoalService.auto_update_statuses)
   3. Balance Health Check    — detects anomalies / negative
                                balances (BalanceService.run_balance_health_check)

 Usage
 -----
   # Run everything for all users (default)
   python scripts/cron_runner.py

   # Dry-run — logs what WOULD happen, changes nothing
   python scripts/cron_runner.py --dry-run

   # Specific jobs only
   python scripts/cron_runner.py --jobs recurring
   python scripts/cron_runner.py --jobs recurring,goals
   python scripts/cron_runner.py --jobs recurring,goals,health

   # Verbose console output
   python scripts/cron_runner.py --verbose

   # Quiet — only errors go to stdout (still writes full log)
   python scripts/cron_runner.py --quiet

 Exit Codes
 ----------
   0  All jobs completed without errors
   1  One or more jobs failed for one or more users
   2  Fatal startup error (bad config, no DB connection, etc.)

 Logging
 -------
   Full structured logs → reports/logs/cron.log  (rotates at 5 MB)
   Error-only log       → reports/logs/errors.log (handled by ErrorLogger)

 Windows Task Scheduler
 ----------------------
   See scripts/setup_task_scheduler.bat to register as a
   scheduled task that fires hourly.
============================================================
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
try:
    import fcntl
except:
                    # POSIX only – handled gracefully on Windows
    fcntl = None

import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# ── Add project root to sys.path so all project imports work ─────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Project imports ───────────────────────────────────────────────────────────
from core.database import DatabaseConnection
from core.scheduler import Scheduler
from core.utils import ConfigurationError, DatabaseError, error_logger
from features.balance import BalanceService
from features.goals import GoalService


# ════════════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════════════

VALID_JOBS   = {"recurring", "goals", "health"}
LOG_DIR      = PROJECT_ROOT / "reports" / "logs"
CRON_LOG     = LOG_DIR / "cron.log"
LOCK_FILE    = LOG_DIR / "cron.lock"   # prevents overlapping runs

JOB_RECURRING = "recurring"
JOB_GOALS     = "goals"
JOB_HEALTH    = "health"


# ════════════════════════════════════════════════════════════════════════════
# Logging Setup
# ════════════════════════════════════════════════════════════════════════════

def _build_cron_logger(verbose: bool, quiet: bool) -> logging.Logger:
    """
    Build a dedicated logger for the cron runner.

    File handler  → reports/logs/cron.log   (always, DEBUG level)
    Stream handler → stdout                  (INFO unless --quiet)
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("fintrack.cron")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.handlers:
        return logger   # already configured (e.g. in tests)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler — full detail
    fh = RotatingFileHandler(
        CRON_LOG, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console handler
    if not quiet:
        # Force UTF-8 for Windows console
        try:
            sh = logging.StreamHandler(sys.stdout)
        except Exception:
            sh = logging.StreamHandler(sys.stdout.buffer)

        sh.setLevel(logging.DEBUG if verbose else logging.INFO)
        sh.setFormatter(fmt)
        logger.addHandler(sh)

    return logger


# ════════════════════════════════════════════════════════════════════════════
# Lock File (prevent overlapping runs)
# ════════════════════════════════════════════════════════════════════════════

class CronLock:
    """
    Simple cross-platform lock file.

    On POSIX we use fcntl for a non-blocking exclusive lock.
    On Windows we fall back to a PID-file approach (checking if the PID
    listed in the file is still alive).
    """

    def __init__(self, lock_path: Path) -> None:
        self._path  = lock_path
        self._fh    = None
        self._posix = (os.name != "nt")

    def acquire(self) -> bool:
        """Return True if the lock was acquired; False if another instance is running."""
        if self._posix:
            return self._acquire_posix()
        return self._acquire_windows()

    def release(self) -> None:
        if self._fh:
            if self._posix:
                try:
                    fcntl.flock(self._fh, fcntl.LOCK_UN)
                except Exception:
                    pass
            try:
                self._fh.close()
            except Exception:
                pass
            try:
                self._path.unlink(missing_ok=True)
            except Exception:
                pass
            self._fh = None

    # ── POSIX ─────────────────────────────────────────────────────
    def _acquire_posix(self) -> bool:
        try:
            self._fh = open(self._path, "w")
            if fcntl:
                fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fh.write(str(os.getpid()))
            self._fh.flush()
            return True
        except (IOError, OSError):
            if self._fh:
                self._fh.close()
                self._fh = None
            return False

    # ── Windows (PID file) ────────────────────────────────────────
    def _acquire_windows(self) -> bool:
        if self._path.exists():
            try:
                pid = int(self._path.read_text().strip())
                # Check if that PID is still alive
                import ctypes
                handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
                if handle:
                    ctypes.windll.kernel32.CloseHandle(handle)
                    return False           # another instance running
            except Exception:
                pass   # stale lock — go ahead

        try:
            self._path.write_text(str(os.getpid()))
            return True
        except Exception:
            return False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.release()


# ════════════════════════════════════════════════════════════════════════════
# Individual Job Runners
# ════════════════════════════════════════════════════════════════════════════

def run_recurring(
    conn,
    user: Dict[str, Any],
    *,
    dry_run: bool,
    log: logging.Logger,
) -> Tuple[bool, str]:
    """
    Execute all due recurring transactions for `user`.

    Returns (success, summary_message).
    """
    username = user.get("username", "?")
    try:
        if dry_run:
            scheduler = Scheduler(conn, user)
            upcoming  = scheduler.get_upcoming_due(days_ahead=0)   # overdue only
            msg = f"[DRY-RUN] user={username}: {len(upcoming)} transaction(s) would be created"
            log.info(msg)
            return True, msg

        scheduler = Scheduler(conn, user)
        result    = scheduler.run_all_due_recurring()

        if result["success"]:
            msg = (
                f"user={username}: created {result['created_count']} "
                f"transaction(s). IDs={result['transaction_ids']}"
            )
            log.info(f"[RECURRING] OK {msg}")
            return True, msg
        else:
            msg = f"user={username}: run_all_due_recurring reported failure — {result.get('message')}"
            log.warning(f"[RECURRING] WARN {msg}")
            return False, msg

    except Exception as exc:
        msg = f"user={username}: unexpected error — {exc}"
        log.error(f"[RECURRING] ERROR {msg}", exc_info=True)
        error_logger.log_error(
            exc,
            location="cron_runner.run_recurring",
            user_id=user.get("user_id"),
            extra=f"username={username}",
        )
        return False, msg


def run_goals(
    conn,
    user: Dict[str, Any],
    *,
    dry_run: bool,
    log: logging.Logger,
) -> Tuple[bool, str]:
    """
    Auto-update goal statuses (completed / failed) for `user`.
    """
    username = user.get("username", "?")
    try:
        svc    = GoalService(conn, user)
        result = svc.list_goals(status="active", with_progress=True)
        active = result.get("goals", [])

        if dry_run:
            would_change = [
                g for g in active
                if g.get("inferred_status") != "active"
            ]
            msg = (
                f"[DRY-RUN] user={username}: {len(would_change)} goal(s) "
                f"would change status out of {len(active)} active"
            )
            log.info(msg)
            return True, msg

        result = svc.auto_update_statuses()
        changed = result.get("total_changed", 0)
        changes = result.get("updated", [])

        details = ", ".join(
            f"{c['name']}: {c['old_status']} → {c['new_status']}"
            for c in changes
        ) or "none"

        msg = f"user={username}: {changed} goal status change(s) — {details}"
        log.info(f"[GOALS] OK {msg}")
        return True, msg

    except Exception as exc:
        msg = f"user={username}: unexpected error — {exc}"
        log.error(f"[GOALS] ERROR {msg}", exc_info=True)
        error_logger.log_error(
            exc,
            location="cron_runner.run_goals",
            user_id=user.get("user_id"),
            extra=f"username={username}",
        )
        return False, msg


def run_health(
    conn,
    user: Dict[str, Any],
    *,
    dry_run: bool,
    log: logging.Logger,
) -> Tuple[bool, str]:
    """
    Run a balance health check for `user` and log any anomalies found.
    Health checks are read-only so dry_run has no special behaviour.
    """
    username = user.get("username", "?")
    try:
        svc    = BalanceService(conn, user)
        result = svc.run_balance_health_check()
        issues = result.get("total_issues", 0)

        if issues == 0:
            msg = f"user={username}: all balances healthy"
            log.info(f"[HEALTH] OK {msg}")
        else:
            bad_accounts = [
                f"{c['account_name']} ({', '.join(c['issues'])})"
                for c in result.get("checks", [])
            ]
            msg = f"user={username}: {issues} issue(s) — {'; '.join(bad_accounts)}"
            log.warning(f"[HEALTH] WARN  {msg}")

        return True, msg

    except Exception as exc:
        msg = f"user={username}: unexpected error — {exc}"
        log.error(f"[HEALTH] ERROR {msg}", exc_info=True)
        error_logger.log_error(
            exc,
            location="cron_runner.run_health",
            user_id=user.get("user_id"),
            extra=f"username={username}",
        )
        return False, msg


# ════════════════════════════════════════════════════════════════════════════
# User Fetcher
# ════════════════════════════════════════════════════════════════════════════

def fetch_all_active_users(conn) -> List[Dict[str, Any]]:
    """
    Return every active (non-deleted) user as a minimal current_user dict.
    This lets each job run with proper tenant isolation per user.
    """
    with conn.cursor(dictionary=True) as cur:
        cur.execute(
            """
            SELECT user_id, username, role
            FROM users
            WHERE is_active = 1
            ORDER BY user_id
            """
        )
        rows = cur.fetchall()

    return [
        {
            "user_id":  row["user_id"],
            "username": row["username"],
            "role":     row["role"],
        }
        for row in rows
    ]


# ════════════════════════════════════════════════════════════════════════════
# Argument Parser
# ════════════════════════════════════════════════════════════════════════════

def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="cron_runner.py",
        description="FinTrack automated background job runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples
--------
  Run all jobs for every user:
    python scripts/cron_runner.py

  Dry-run (no DB writes):
    python scripts/cron_runner.py --dry-run

  Run only recurring + goals:
    python scripts/cron_runner.py --jobs recurring,goals

  Verbose output:
    python scripts/cron_runner.py --verbose
        """,
    )

    p.add_argument(
        "--jobs",
        default="recurring,goals,health",
        help=(
            "Comma-separated list of jobs to run. "
            "Valid values: recurring, goals, health  (default: all three)"
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Simulate jobs without writing anything to the database",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Show DEBUG-level output on stdout",
    )
    p.add_argument(
        "--quiet", "-q",
        action="store_true",
        default=False,
        help="Suppress all stdout output (errors still go to log file)",
    )
    p.add_argument(
        "--no-lock",
        action="store_true",
        default=False,
        help="Skip the lock-file check (useful for testing)",
    )

    return p.parse_args(argv)


# ════════════════════════════════════════════════════════════════════════════
# Main Runner
# ════════════════════════════════════════════════════════════════════════════

def main(argv: Optional[List[str]] = None) -> int:
    """
    Entry point. Returns an exit code.
    """
    args = _parse_args(argv)

    log = _build_cron_logger(args.verbose, args.quiet)

    # ── Validate job list ─────────────────────────────────────────────────
    requested_jobs = {j.strip().lower() for j in args.jobs.split(",") if j.strip()}
    invalid = requested_jobs - VALID_JOBS
    if invalid:
        log.error(f"Unknown job(s): {invalid}. Valid options: {VALID_JOBS}")
        return 2

    # ── Header ────────────────────────────────────────────────────────────
    dry_label = "  [DRY-RUN]" if args.dry_run else ""
    log.info("=" * 70)
    log.info(f"FinTrack Cron Runner started{dry_label}")
    log.info(f"Jobs: {sorted(requested_jobs)}")
    log.info("=" * 70)

    start_ts = datetime.now()

    # ── Lock file ─────────────────────────────────────────────────────────
    lock = CronLock(LOCK_FILE)
    if not args.no_lock:
        if not lock.acquire():
            log.warning("Another cron instance is already running — exiting.")
            return 0   # Not a failure — just skip this run

    try:
        # ── Database connection ───────────────────────────────────────────
        try:
            db   = DatabaseConnection()
            conn = db.get_connection()
        except ConfigurationError as exc:
            log.error(f"Configuration error: {exc}")
            return 2
        except Exception as exc:
            log.error(f"Could not connect to the database: {exc}")
            return 2

        if not conn:
            log.error("DB connection returned None — check config/config.ini")
            return 2

        # ── Fetch users ───────────────────────────────────────────────────
        try:
            users = fetch_all_active_users(conn)
        except Exception as exc:
            log.error(f"Failed to fetch user list: {exc}")
            conn.close()
            return 2

        if not users:
            log.warning("No active users found — nothing to process.")
            conn.close()
            return 0

        log.info(f"Processing {len(users)} active user(s) …")

        # ── JOB DISPATCH MAP ──────────────────────────────────────────────
        job_runners = {
            JOB_RECURRING: run_recurring,
            JOB_GOALS:     run_goals,
            JOB_HEALTH:    run_health,
        }

        # ── Run jobs for every user ───────────────────────────────────────
        total_failures = 0

        for user in users:
            username = user["username"]
            log.info(f"--- User: {username} (id={user['user_id']}, role={user['role']}) ---")

            for job_name in (JOB_RECURRING, JOB_GOALS, JOB_HEALTH):
                if job_name not in requested_jobs:
                    continue
                success, _ = job_runners[job_name](
                    conn, user, dry_run=args.dry_run, log=log
                )
                if not success:
                    total_failures += 1

        # ── Summary ───────────────────────────────────────────────────────
        elapsed = (datetime.now() - start_ts).total_seconds()
        log.info("=" * 70)
        if total_failures == 0:
            log.info(
                f"Cron run COMPLETED successfully in {elapsed:.1f}s  "
                f"({len(users)} user(s), {len(requested_jobs)} job(s) each)"
            )
        else:
            log.warning(
                f"Cron run FINISHED WITH {total_failures} FAILURE(S) in {elapsed:.1f}s"
            )
        log.info("=" * 70)

        conn.close()
        return 0 if total_failures == 0 else 1

    finally:
        if not args.no_lock:
            lock.release()


# ════════════════════════════════════════════════════════════════════════════
# Entry
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    sys.exit(main())