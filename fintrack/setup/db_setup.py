#!/usr/bin/env python3
# scripts/db_setup.py
"""
============================================================
 FinTrack — Database Setup Script
 ------------------------------------------------------------
 This script works in ALL THREE distribution scenarios:

   Scenario 1 — Source:
       python scripts/db_setup.py

   Scenario 2 — Pip package (installed):
       fintrack-setup

   Scenario 3 — Standalone executable:
       ./budget-tracker --setup        (Linux/macOS)
       budget-tracker.exe --setup      (Windows)

 What it does:
   1. Prompts for MySQL root credentials (or reads config.ini)
   2. Creates the database if it doesn't exist
   3. Finds seeds.sql — whether on disk or bundled inside the exe
   4. Runs every SQL statement from seeds.sql
   5. Creates a fresh config.ini from your inputs
   6. Confirms everything is working with a connection test

 Safe to re-run:
   Uses CREATE TABLE IF NOT EXISTS, so it won't destroy
   existing data. To reset completely, use --fresh flag.
============================================================
"""

from __future__ import annotations

import argparse
import configparser
import os
import sys
from pathlib import Path

import mysql.connector
from mysql.connector import Error

# ── Resolve paths correctly for all 3 distribution scenarios ─────────────────

def _get_project_root() -> Path:
    """
    Works whether we are:
      - Running as a plain Python script  (source / pip install)
      - Frozen inside a PyInstaller exe   (standalone)
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent

    # If running inside installed package → use CWD
    if "site-packages" in str(Path(__file__).resolve()):
        return Path.cwd()

    # Dev mode → go up OUTSIDE fintrack
    return Path(__file__).resolve().parents[2]


def _find_seeds_sql() -> Path:
    """
    Locate seeds.sql in all scenarios:
    """

    # ── 1. PyInstaller (works for BOTH onefile + onedir) ──
    if getattr(sys, "frozen", False):
        base_path = Path(sys.executable).parent
        candidate = base_path / "data" / "seeds.sql"
        if candidate.exists():
            return candidate

    # ── 2. Development / pip install ──
    candidates = [
        _get_project_root() / "fintrack" / "data" / "seeds.sql",
        _get_project_root() / "data" / "seeds.sql",
        Path("fintrack/data/seeds.sql"),
        Path("data/seeds.sql"),
    ]

    for p in candidates:
        if p.exists():
            return p

    raise FileNotFoundError(
        "seeds.sql not found. Expected it at data/seeds.sql "
        "relative to the project root."
    )

def _find_config_path() -> Path:
    """Find or create the config directory."""
    root = _get_project_root()
    cfg_dir = root / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir / "config.ini"


# ── Colours (works on all platforms in Python 3.11+) ──────────────────────────

RESET  = "\033[0m"
GREEN  = "\033[32m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"
RED    = "\033[31m"
BOLD   = "\033[1m"

def ok(msg: str)   -> None: print(f"{GREEN}✅  {msg}{RESET}")
def info(msg: str) -> None: print(f"{CYAN}ℹ️   {msg}{RESET}")
def warn(msg: str) -> None: print(f"{YELLOW}⚠️   {msg}{RESET}")
def err(msg: str)  -> None: print(f"{RED}❌  {msg}{RESET}")
def hdr(msg: str)  -> None: print(f"\n{BOLD}{CYAN}{msg}{RESET}")


# ── SQL parsing ───────────────────────────────────────────────────────────────

def _parse_sql_statements(sql_text: str) -> list[str]:
    """
    Split a SQL file into individual statements, skipping comments
    and empty lines. Handles multi-line statements correctly.
    """
    statements = []
    current    = []

    for line in sql_text.splitlines():
        stripped = line.strip()

        # Skip standalone comment lines and blank lines
        if not stripped or stripped.startswith("--") or stripped.startswith("#"):
            continue

        # Remove inline comments  (basic — good enough for DDL files)
        if "--" in stripped:
            stripped = stripped[:stripped.index("--")].strip()

        current.append(stripped)

        # A semicolon ends a statement
        if stripped.endswith(";"):
            statement = " ".join(current).strip()
            if statement and statement != ";":
                statements.append(statement)
            current = []

    return statements


# ── Core setup logic ──────────────────────────────────────────────────────────

def collect_credentials(existing_config: Path) -> dict:
    """
    Prompt the user for DB credentials.
    Pre-fills from config.ini if it already exists.
    """
    defaults = {"host": "localhost", "port": "3306",
                "user": "root", "password": "", "database": "budget_tracker"}

    if existing_config.exists():
        cfg = configparser.ConfigParser()
        cfg.read(existing_config)
        if cfg.has_section("mysql"):
            defaults.update(dict(cfg["mysql"]))
        info(f"Found existing config at {existing_config}")
        info("Press Enter to keep current values, or type a new one.")

    print()
    host     = input(f"  MySQL host     [{defaults['host']}]: ").strip() or defaults["host"]
    port     = input(f"  MySQL port     [{defaults['port']}]: ").strip() or defaults["port"]
    user     = input(f"  MySQL user     [{defaults['user']}]: ").strip() or defaults["user"]
    password = input(f"  MySQL password [{'*' * len(defaults['password']) or '(empty)'}]: ").strip()
    if not password:
        password = defaults["password"]
    database = input(f"  Database name  [{defaults['database']}]: ").strip() or defaults["database"]

    return {"host": host, "port": int(port),
            "user": user, "password": password, "database": database}


def create_database(creds: dict) -> None:
    """Connect to MySQL server (no DB selected) and create the database."""
    info(f"Connecting to MySQL at {creds['host']}:{creds['port']} ...")

    conn = mysql.connector.connect(
        host     = creds["host"],
        port     = creds["port"],
        user     = creds["user"],
        password = creds["password"],
    )
    cur = conn.cursor()
    db  = creds["database"]

    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    conn.commit()
    cur.close()
    conn.close()

    ok(f"Database `{db}` is ready.")


def run_seeds(creds: dict, seeds_path: Path, fresh: bool = False) -> None:
    """
    Execute every statement in seeds.sql against the target database.

    fresh=True  → DROP + recreate each table (destructive!)
    fresh=False → CREATE TABLE IF NOT EXISTS (safe, preserves data)
    """
    info(f"Reading schema from: {seeds_path}")
    sql_text = seeds_path.read_text(encoding="utf-8")

    if not fresh:
        # Swap DROP TABLE for a safe no-op so we don't wipe existing data
        sql_text = sql_text.replace(
            "DROP TABLE IF EXISTS",
            "-- [setup: skipped DROP] CREATE TABLE IF NOT EXISTS --\n-- DROP TABLE IF EXISTS"
        )
        # Also ensure CREATE TABLE uses IF NOT EXISTS
        sql_text = sql_text.replace("CREATE TABLE `", "CREATE TABLE IF NOT EXISTS `")
        info("Running in SAFE mode — existing tables and data are preserved.")
    else:
        warn("Running in FRESH mode — all existing data will be DELETED.")
        confirm = input("  Type YES to confirm: ").strip()
        if confirm != "YES":
            warn("Aborted.")
            return

    statements = _parse_sql_statements(sql_text)
    info(f"Executing {len(statements)} SQL statement(s)...")

    conn = mysql.connector.connect(
        host     = creds["host"],
        port     = creds["port"],
        user     = creds["user"],
        password = creds["password"],
        database = creds["database"],
    )
    cur  = conn.cursor()
    done = 0
    skipped = 0

    for stmt in statements:
        # Skip the comment lines we inserted in safe mode
        if stmt.strip().startswith("--"):
            skipped += 1
            continue
        try:
            cur.execute(stmt)
            conn.commit()
            done += 1
        except Error as exc:
            # 1050 = table already exists — fine in safe mode
            if exc.errno == 1050 and not fresh:
                skipped += 1
            else:
                warn(f"Statement failed (continuing): {exc}")
                skipped += 1

    cur.close()
    conn.close()
    ok(f"Schema applied — {done} executed, {skipped} skipped.")


def write_config(creds: dict, config_path: Path) -> None:
    """Write the DB credentials to config/config.ini."""
    cfg = configparser.ConfigParser()
    cfg["mysql"] = {
        "host"     : creds["host"],
        "user"     : creds["user"],
        "password" : creds["password"],
        "database" : creds["database"],
        "port"     : str(creds["port"]),
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        cfg.write(f)
    ok(f"Config written to {config_path}")


def test_connection(config_path: Path) -> bool:
    """Verify the final config works end-to-end."""
    cfg = configparser.ConfigParser()
    cfg.read(config_path)
    try:
        conn = mysql.connector.connect(**dict(cfg["mysql"]))
        cur  = conn.cursor()
        cur.execute("SHOW TABLES;")
        tables = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        ok(f"Connection verified! Tables found: {', '.join(tables) or '(none yet)'}")
        return True
    except Error as exc:
        err(f"Connection test failed: {exc}")
        return False


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="FinTrack — Database Setup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Drop and recreate all tables (WARNING: deletes all data)",
    )
    parser.add_argument(
        "--test-only",
        action="store_true",
        help="Only test the existing config.ini connection, skip setup",
    )
    args = parser.parse_args()

    print()
    print(f"{BOLD}{'=' * 56}{RESET}")
    print(f"{BOLD}  💰 FinTrack — Database Setup{RESET}")
    print(f"{BOLD}{'=' * 56}{RESET}")

    config_path = _find_config_path()

    # ── Test-only mode ───────────────────────────────────────
    if args.test_only:
        hdr("Testing existing connection...")
        if not config_path.exists():
            err(f"No config.ini found at {config_path}. Run setup first.")
            sys.exit(1)
        success = test_connection(config_path)
        sys.exit(0 if success else 1)

    # ── Full setup flow ──────────────────────────────────────
    hdr("Step 1 — Enter your MySQL credentials")
    creds = collect_credentials(config_path)

    hdr("Step 2 — Create database")
    try:
        create_database(creds)
    except Error as exc:
        err(f"Could not connect to MySQL: {exc}")
        err("Make sure MySQL is running and your credentials are correct.")
        sys.exit(1)

    hdr("Step 3 — Apply schema (seeds.sql)")
    try:
        seeds_path = _find_seeds_sql()
        run_seeds(creds, seeds_path, fresh=args.fresh)
    except FileNotFoundError as exc:
        err(str(exc))
        sys.exit(1)

    hdr("Step 4 — Save config")
    write_config(creds, config_path)

    hdr("Step 5 — Verify connection")
    ok_conn = test_connection(config_path)

    print()
    print(f"{BOLD}{'=' * 56}{RESET}")
    if ok_conn:
        print(f"{GREEN}{BOLD}  🎉 Setup complete! Run your app with:{RESET}")
        if getattr(sys, "frozen", False):
            exe = Path(sys.executable).name
            print(f"{CYAN}     ./{exe}{RESET}")
        else:
            print(f"{CYAN}     python main.py{RESET}")
            print(f"{CYAN}     fintrack          (if installed via pip){RESET}")
    else:
        print(f"{RED}{BOLD}  ❌ Setup finished but connection test failed.{RESET}")
        print(f"     Check your MySQL credentials and try again.")
    print(f"{BOLD}{'=' * 56}{RESET}")
    print()


if __name__ == "__main__":
    main()