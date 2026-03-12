#cli helpers(promps,menus etc)
# core/cli_helpers.py
"""
============================================================
 CLI Helpers — Rich-powered UX for the Finance Tracker CLI
 -----------------------------------------------------------
 Provides a consistent, polished terminal interface:
   • Navigation signals  (Back, Exit, Logout)
   • Themed printing     (headers, menus, status messages)
   • Input helpers       (typed, validated prompts)
   • Table rendering     (Rich-backed data tables)
   • Menu dispatcher     (numbered choice loop)

 Usage pattern
 -----------------------------------------------------------
   from core.cli_helpers import (
       BackSignal, ExitSignal, LogoutSignal,
       print_header, print_menu, prompt_choice,
       ask_str, ask_int, ask_float, ask_date, ask_confirm,
       print_success, print_error, print_warning, print_info,
       print_table, clear_screen, print_section,
   )
============================================================
"""

from __future__ import annotations

import os
import time
import sys
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from rich import box
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt


# ════════════════════════════════════════════════════════
# Console singleton — import this anywhere for consistency
# ════════════════════════════════════════════════════════

console = Console()


# ════════════════════════════════════════════════════════
# Navigation Signals
# ════════════════════════════════════════════════════════

class BackSignal(Exception):
    """Raised to navigate one level up in the menu tree."""


class ExitSignal(Exception):
    """Raised to quit the application cleanly."""


class LogoutSignal(Exception):
    """Raised to logout and return to the auth screen."""


# ════════════════════════════════════════════════════════
# Theme Constants
# ════════════════════════════════════════════════════════

class Theme:
    # Brand colours
    PRIMARY   = "bold cyan"
    SECONDARY = "bold blue"
    ACCENT    = "bold magenta"
    DIM       = "dim white"

    # Status
    SUCCESS = "bold green"
    ERROR   = "bold red"
    WARNING = "bold yellow"
    INFO    = "bold cyan"

    # Transaction types
    TX_COLORS: Dict[str, str] = {
        "income":               "green",
        "expense":              "red",
        "transfer":             "cyan",
        "debt_borrowed":        "yellow",
        "debt_repaid":          "blue",
        "investment_deposit":   "magenta",
        "investment_withdraw":  "dark_orange",
    }

    # Category colour palette (cycles)
    CATEGORY_PALETTE = [
        "bold red", "bold dark_orange", "bold yellow",
        "bold green", "bold cyan", "bold blue",
        "bold magenta", "bold white",
    ]

    # Box style for menus
    MENU_BOX  = box.ROUNDED
    TABLE_BOX = box.SIMPLE_HEAD


# ════════════════════════════════════════════════════════
# Screen Utilities
# ════════════════════════════════════════════════════════

def clear_screen() -> None:
    """Clear the terminal screen cross-platform."""
    os.system("cls" if os.name == "nt" else "clear")


def pause(prompt: str = "Press [Enter] to continue…") -> None:
    """Pause execution until the user presses Enter."""
    console.print(f"\n[dim]{prompt}[/dim]")
    try:
        input()
    except (KeyboardInterrupt, EOFError):
        pass

# ════════════════════════════════════════════════════════
# Header & Branding
# ════════════════════════════════════════════════════════

APP_BANNER = r"""
  ███████╗██╗███╗   ██╗████████╗██████╗  █████╗  ██████╗██╗  ██╗
  ██╔════╝██║████╗  ██║╚══██╔══╝██╔══██╗██╔══██╗██╔════╝██║ ██╔╝
  █████╗  ██║██╔██╗ ██║   ██║   ██████╔╝███████║██║     █████╔╝
  ██╔══╝  ██║██║╚██╗██║   ██║   ██╔══██╗██╔══██║██║     ██╔═██╗
  ██║     ██║██║ ╚████║   ██║   ██║  ██║██║  ██║╚██████╗██║  ██╗ 
  ╚═╝     ╚═╝╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝
"""

def startup_banner_animation() -> None:
    """Animate banner glow on program startup."""

    styles = [
        "dim cyan",
        "cyan",
        "bold cyan",
        "bold bright_cyan",
    ]

    for style in styles:
        console.clear()

        console.print(f"[{style}]{APP_BANNER}[/{style}]")
        console.print(
            Align.center("[dim]Personal Finance Tracker  •  v1.0[/dim]\n")
        )

        time.sleep(0.2)

def print_app_banner() -> None:
    """Print the ASCII art application banner."""
    console.print(f"[bold cyan]{APP_BANNER}[/bold cyan]")
    console.print(
        Align.center("[dim]Personal Finance Tracker  •  v1.0[/dim]\n")
    )

def print_header(
    title: str,
    subtitle: str = "",
    username: str = "",
    role: str = "",
    style: str = "cyan",
) -> None:
    """
    Print a styled top-of-screen header.

    Args:
        title    : Main page title.
        subtitle : Optional sub-title shown below.
        username : Logged-in user (shown in top-right if provided).
        role     : User role label.
        style    : Rich colour/style for the rule.
    """
    user_info = ""
    if username:
        role_badge = f"  [{('bold yellow' if role == 'admin' else 'dim')}]({role})[/{'bold yellow' if role == 'admin' else 'dim'}]" if role else ""
        user_info = f"[dim]👤 {username}{role_badge}[/dim]"

    rule_text = f"[bold {style}]{title}[/bold {style}]"
    if user_info:
        rule_text += f"  {user_info}"

    console.print()
    console.print(Rule(rule_text, style=style))
    if subtitle:
        console.print(Align.center(f"[dim]{subtitle}[/dim]"))
        console.print()
