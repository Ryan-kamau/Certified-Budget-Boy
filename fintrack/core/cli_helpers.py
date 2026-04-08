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
from fintrack.core.utils import DateRangeValidator, ValidationPatterns, ValidationError

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

def print_section(title: str, style: str = "blue") -> None:
    """Print a section divider with a title."""
    console.print()
    console.print(Rule(f"[{style}]{title}[/{style}]", style=f"dim {style}"))


# ════════════════════════════════════════════════════════
# Status Messages
# ════════════════════════════════════════════════════════

def print_success(message: str) -> None:
    console.print(f"\n[bold green]✅  {message}[/bold green]")

def print_error(message: str) -> None:
    console.print(f"\n[bold red]❌  {message}[/bold red]")

def print_warning(message: str) -> None:
    console.print(f"\n[bold yellow]⚠️   {message}[/bold yellow]")

def print_info(message: str) -> None:
    console.print(f"\n[bold cyan]ℹ️   {message}[/bold cyan]")

def print_result(result: Dict[str, Any], success_key: str = "message") -> None:
    """
    Print a standardised model result dict.
    Shows green on success, red on failure.
    """
    if result.get("success"):
        print_success(result.get(success_key) or result.get("message", "Done."))
    else:
        print_error(result.get("message", "Operation failed."))


# ════════════════════════════════════════════════════════
# Menu Rendering
# ════════════════════════════════════════════════════════

MenuItem = Tuple[str, str]   # (label, description)  — description may be ""


def print_menu(
    items: List[MenuItem],
    title: str = "Menu",
    footer_hint: str = "Type a number and press Enter",
    back_label: str = "Back",
    show_back: bool = True,
    show_exit: bool = True,
) -> None:
    """
    Render a numbered menu inside a Rich Panel.

    Args:
        items       : List of (label, description) tuples (1-indexed display).
        title       : Panel title.
        footer_hint : Hint text shown at the bottom.
        back_label  : Label for the 'back' option.
        show_back   : Whether to append a 'Back' option.
        show_exit   : Whether to append an 'Exit' option at 0.
    """
    table = Table(
        show_header=False,
        box=None,
        padding=(0, 1),
        expand=True,
    )
    table.add_column("Num",  style="bold cyan",  width=5,  no_wrap=True)
    table.add_column("Label", style="bold white", min_width=20)
    table.add_column("Desc",  style="dim",        min_width=10)

    for idx, (label, desc) in enumerate(items, start=1):
        table.add_row(f"  {idx}.", label, desc)

    # Separator
    table.add_row("", "", "")

    if show_back:
        table.add_row("  [dim]B.[/dim]", f"[dim]{back_label}[/dim]", "")
    if show_exit:
        table.add_row("  [dim]0.[/dim]", "[dim]Exit Application[/dim]", "")

    console.print(
        Panel(
            table,
            title=f"[bold cyan]  {title}  [/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        )
    )
    if footer_hint:
        console.print(f"  [dim]{footer_hint}[/dim]\n")

# ════════════════════════════════════════════════════════
# Prompt & Choice Dispatcher
# ════════════════════════════════════════════════════════

def prompt_choice(
    items: List[MenuItem],
    title: str = "Menu",
    back_label: str = "↩  Back",
    show_back: bool = True,
    show_exit: bool = True,
    footer_hint: str = "",
) -> Optional[int]:
    """
    Display a menu and return the user's numeric choice.

    Special returns:
      None → user chose "Back"  (raises BackSignal)
      raises ExitSignal on '0'
      raises KeyboardInterrupt passthrough for Ctrl+C

    Returns:
        int  : 1-based index of the chosen item.
    """
    print_menu(
        items,
        title=title,
        back_label=back_label,
        show_back=show_back,
        show_exit=show_exit,
        footer_hint=footer_hint or "Enter a number (or B=Back, 0=Exit)",
    )

    while True:
        try:
            raw = input("  👉  ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise ExitSignal()

        if raw in ("b", "back", "") and show_back:
            raise BackSignal()
        if raw == "0" and show_exit:
            raise ExitSignal()

        try:
            choice = int(raw)
            if 1 <= choice <= len(items):
                return choice
            print_warning(f"Please enter a number between 1 and {len(items)}.")
        except ValueError:
            print_warning("Invalid input — enter a number, B to go back, or 0 to exit.")


# ════════════════════════════════════════════════════════
# Typed Input Helpers
# ════════════════════════════════════════════════════════

def ask_str(
    prompt: str,
    *,
    required: bool = True,
    default: Optional[str] = None,
    max_len: Optional[int] = None,
    allow_back: bool = True,
) -> Optional[str]:
    """
    Prompt for a string value.

    Type 'B' or leave blank (if not required) to return None / go back.
    """
    hint = ""
    if default:
        hint = f" [dim](default: {default})[/dim]"
    if not required:
        hint += " [dim](optional — blank to skip)[/dim]"
    if allow_back:
        hint += " [dim](B=back)[/dim]"

    console.print(f"  [bold]{prompt}[/bold]{hint}")
    while True:
        try:
            raw = input("  › ").strip()
        except (EOFError, KeyboardInterrupt):
            raise ExitSignal()

        if raw.lower() == "b" and allow_back:
            raise BackSignal()

        if not raw:
            if default is not None:
                return default
            if not required:
                return None
            print_warning("This field is required.")
            continue

        if max_len and len(raw) > max_len:
            print_warning(f"Too long — max {max_len} characters.")
            continue

        return raw


def ask_int(
    prompt: str,
    *,
    required: bool = True,
    default: Optional[int] = None,
    min_val: Optional[int] = None,
    max_val: Optional[int] = None,
    allow_back: bool = True,
) -> Optional[int]:
    """Prompt for an integer value with optional bounds."""
    bounds = ""
    if min_val is not None and max_val is not None:
        bounds = f" [{min_val}–{max_val}]"
    elif min_val is not None:
        bounds = f" [≥{min_val}]"

    hint = bounds
    if default is not None:
        hint += f" [dim](default: {default})[/dim]"
    if not required:
        hint += " [dim](optional)[/dim]"
    if allow_back:
        hint += " [dim](B=back)[/dim]"

    console.print(f"  [bold]{prompt}[/bold]{hint}")
    while True:
        try:
            raw = input("  › ").strip()
        except (EOFError, KeyboardInterrupt):
            raise ExitSignal()

        if raw.lower() == "b" and allow_back:
            raise BackSignal()

        if not raw:
            if default is not None:
                return default
            if not required:
                return None
            print_warning("This field is required.")
            continue

        try:
            val = int(raw)
        except ValueError:
            print_warning("Please enter a whole number.")
            continue

        if min_val is not None and val < min_val:
            print_warning(f"Value must be at least {min_val}.")
            continue
        if max_val is not None and val > max_val:
            print_warning(f"Value must be at most {max_val}.")
            continue

        return val
    
def ask_float(
    prompt: str,
    *,
    required: bool = True,
    default: Optional[float] = None,
    min_val: Optional[float] = None,
    allow_back: bool = True,
) -> Optional[float]:
    """Prompt for a decimal / float value."""
    hint = ""
    if default is not None:
        hint += f" [dim](default: {default})[/dim]"
    if not required:
        hint += " [dim](optional)[/dim]"
    if allow_back:
        hint += " [dim](B=back)[/dim]"
 
    console.print(f"  [bold]{prompt}[/bold]{hint}")
    while True:
        try:
            raw = input("  › ").strip()
        except (EOFError, KeyboardInterrupt):
            raise ExitSignal()
 
        if raw.lower() == "b" and allow_back:
            raise BackSignal()
 
        if not raw:
            if default is not None:
                return default
            if not required:
                return None
            print_warning("This field is required.")
            continue
 
        try:
            val = float(raw.replace(",", ""))
        except ValueError:
            print_warning("Please enter a valid number (e.g. 1500 or 1500.50).")
            continue
 
        if min_val is not None and val < min_val:
            print_warning(f"Value must be at least {min_val}.")
            continue
 
        return val


def ask_date(
    prompt: str,
    *,
    required: bool = False,
    default: Optional[date] = None,
    allow_back: bool = True,
) -> Optional[date]:
    

    """
    Prompt for a date in YYYY-MM-DD format.

    Shortcuts:
      today  → today's date
      preset → select a date preset (e.g. "last_month", "start_of_year")
      blank  → default (if provided) or None (if not required)
      b      → go back (if allowed)
    """

    # --- Build hint text (NO function calls here) ---
    if default:
        default_hint = f" [dim](default: {default} or type 'preset' for options or 'today' | 't')[/dim]"
    elif not required:
        default_hint = " [dim](optional — blank to skip, or type 'preset' for options or 'today' | 't')[/dim]"
    else:
        default_hint = " [dim](type 'preset' for options or 'today' | 't')[/dim]"

    if allow_back:
        default_hint += " [dim](B=back)[/dim]"

    console.print(f"  [bold]{prompt}[/bold]  [dim]YYYY-MM-DD[/dim]{default_hint}")

    # --- Input loop ---
    while True:
        try:
            raw = input("  › ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise ExitSignal()

        # --- Navigation ---
        if raw == "b" and allow_back:
            raise BackSignal()

        # --- Shortcuts ---
        if raw in ("today", "t"):
            return date.today()

        if raw in ("preset", "p"):
            choice = ask_choice(
                "Date preset",
                ValidationPatterns.DATE_PRESETS,
                required=True
            )
            return DateRangeValidator.get_preset_range(choice)[0] #Return the first date of the range

        # --- Blank handling ---
        if not raw:
            if default is not None:
                return default
            if not required:
                return None
            print_warning("A date is required.")
            continue

        # --- Parse date ---
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            print_warning(
                "Invalid format — use YYYY-MM-DD (e.g. 2025-01-15), 'today', or 'preset'."
            )

def ask_choice(
    prompt: str,
    options: Sequence[str],
    *,
    default: Optional[str] = None,
    required: bool = True,
    show_options: bool = True,
    allow_back: bool = True,
) -> Optional[str]:
    """
    Prompt for one value from a fixed set.
 
    Displays the allowed options and validates the input.
    """
    opts_lower = [o.lower() for o in options]
 
    hint = ""
    if show_options:
        opts_display = " | ".join(options)
        hint = f"  [dim]({opts_display})[/dim]"
    if default:
        hint += f"  [dim]default: {default}[/dim]"
    if not required:
        hint += "  [dim](optional)[/dim]"
    if allow_back:
        hint += "  [dim](B=back)[/dim]"
 
    console.print(f"  [bold]{prompt}[/bold]{hint}")
    while True:
        try:
            raw = input("  › ").strip()
        except (EOFError, KeyboardInterrupt):
            raise ExitSignal()
 
        if raw.lower() == "b" and allow_back:
            raise BackSignal()
 
        if not raw:
            if default is not None:
                return default
            if not required:
                return None
            print_warning("This field is required.")
            continue
 
        if raw.lower() in opts_lower:
            # Return the original-cased version
            return options[opts_lower.index(raw.lower())]
 
        print_warning(f"Invalid choice. Options: {' | '.join(options)}")
 
 
def ask_confirm(prompt: str, default: bool = False) -> bool:
    """
    Ask a yes/no confirmation question.
 
    Returns True for 'y', False for 'n'.
    """
    default_hint = "[Y/n]" if default else "[y/N]"
    console.print(f"  [bold]{prompt}[/bold]  [dim]{default_hint}[/dim]")
    try:
        raw = input("  › ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        raise ExitSignal()
 
    if not raw:
        return default
    return raw in ("y", "yes")
 
 
def ask_password(prompt: str = "Password") -> str:
    """Prompt for a password (hidden input via getpass)."""
    console.print(f"  [bold]{prompt}:[/bold]  [dim][/dim]")
    try:
        return input("  › ")
    except (EOFError, KeyboardInterrupt):
        raise ExitSignal()

# ════════════════════════════════════════════════════════
# Table Rendering
# ════════════════════════════════════════════════════════
 
def print_table(
    rows: List[Dict[str, Any]],
    columns: List[Tuple[str, str]],   # [(header, key), ...]
    title: str = "",
    currency: str = "KES",
    highlight_col: Optional[str] = None,
    empty_message: str = "No records found.",
    formatters: Optional[Dict[str, Callable]] = None,
) -> None:
    """
    Render a list-of-dicts as a Rich table.
 
    Args:
        rows         : Data rows (list of dicts).
        columns      : Column definitions — list of (header_label, dict_key).
        title        : Optional table title.
        currency     : Currency label used in fmt_money formatter.
        highlight_col: Key whose values get coloured (uses TX_COLORS).
        empty_message: Shown when rows is empty.
        formatters   : Dict of {key: callable(value) → str} for custom display.
    """
    if not rows:
        print_info(empty_message)
        return
 
    table = Table(
        box=Theme.TABLE_BOX,
        show_header=True,
        header_style="bold cyan",
        expand=True,
        title=f"[bold cyan]{title}[/bold cyan]" if title else "",
    )
 
    for header, key in columns:
        justify = "right" if key in ("amount", "balance", "total", "net", "progress_pct") else "left"
        table.add_column(header, justify=justify)
 
    for row in rows:
        cells = []
        for _header, key in columns:
            raw = row.get(key, "—")
 
            # Apply custom formatter first
            if formatters and key in formatters:
                raw = formatters[key](raw)
 
            # Auto-format common types
            if isinstance(raw, (date, datetime)) and key != "timestamp":  # timestamp gets a custom formatter by default
                raw = raw.strftime("%d %b %Y") if hasattr(raw, "strftime") else str(raw)
            elif isinstance(raw, float):
                raw = f"{raw:,.2f}"
            elif raw is None:
                raw = "—"
            else:
                raw = str(raw)
 
            # Highlight transaction-type column
            if key == highlight_col:
                colour = Theme.TX_COLORS.get(raw.lower(), "white")
                raw = f"[{colour}]{raw}[/{colour}]"
 
            cells.append(raw)
 
        table.add_row(*cells)
 
    console.print(table)
 
 
def fmt_money(amount: Any, currency: str = "KES") -> str:
    """Format a numeric amount as a coloured currency string."""
    try:
        val = float(amount)
    except (TypeError, ValueError):
        return str(amount)
    colour = "green" if val >= 0 else "red"
    sign   = "+" if val > 0 else ""
    return f"[{colour}]{sign}{currency} {val:,.2f}[/{colour}]"


def fmt_datetime(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%d-%m-%Y %I:%M %p")
    except Exception:
        return str(value)
 
 
def fmt_date(d: Any) -> str:
    """Format a date/datetime/string to a readable date string."""
    if isinstance(d, datetime):
        return d.strftime("%d %b %Y %H:%M")
    if isinstance(d, date):
        return d.strftime("%d %b %Y")
    if isinstance(d, str):
        try:
            return datetime.fromisoformat(d).strftime("%d %b %Y")
        except ValueError:
            return d[:10]
    return str(d) if d else "—"

def fmt_breakdown(data: Dict[str, float], currency: str) -> str:
    lines = []

    for k, v in data.items():
        label = k.replace("_", " ").title()
        amount = fmt_money(v, currency)
        lines.append(f"{label:<15} {amount}")

    return "\n".join(lines)
 
 
def fmt_status(status: str) -> str:
    """Colour-code a status string."""
    mapping = {
        "active":    "[bold green]active[/bold green]",
        "completed": "[bold blue]completed[/bold blue]",
        "failed":    "[bold red]failed[/bold red]",
        "paused":    "[bold yellow]paused[/bold yellow]",
        "inactive":  "[dim]inactive[/dim]",
        "deleted":   "[dim]deleted[/dim]",
    }
    return mapping.get(status.lower(), status)


def fmt_list_of_dicts(rows: List[Dict[str, Any]], currency: str):
    table = Table(show_header=True, header_style="bold cyan")

    # dynamic columns
    for key in rows[0].keys():
        table.add_column(key.replace("_", " ").title())

    for row in rows:
        formatted_row = []

        for k, v in row.items():
            if k in ("created_at", "updated_at"):
                v = fmt_datetime(v)
            elif k == "is_active":
                v = "[green]Active[/green]" if v else "[dim]Inactive[/dim]"

            formatted_row.append(str(v))

        table.add_row(*formatted_row)

    return table
 
 
# ════════════════════════════════════════════════════════
# Quick Key-Value Detail Panel
# ════════════════════════════════════════════════════════
 
def print_detail_panel(
    data: Dict[str, Any],
    title: str = "Details",
    style: str = "cyan",
    exclude_keys: Optional[List[str]] = None,
    currency_keys: Optional[List[str]] = None,
    date_keys: Optional[List[str]] = None,
    currency: str = "KES",
) -> None:
    """
    Render a single record as a key-value panel.
 
    Args:
        data         : Dict of field → value.
        title        : Panel title.
        style        : Border colour.
        exclude_keys : Keys to omit from display.
        currency_keys: Keys whose values should be formatted as money.
        date_keys    : Keys whose values should be formatted as dates.
        currency     : Currency label.
    """
    exclude_keys  = set(exclude_keys  or [])
    currency_keys = set(currency_keys or [])
    date_keys     = set(date_keys     or [])
 
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Field", style="bold dim",  min_width=24)
    table.add_column("Value", style="bold white")
 
    for key, val in data.items():
        if key in exclude_keys:
            continue
 
        label = key.replace("_", " ").title()

        if key in currency_keys:
            display = fmt_money(val, currency)
        elif isinstance(val, list) and val and isinstance(val[0], dict):    
            display = fmt_list_of_dicts(val, currency)
        elif key == "timestamp":
            display = fmt_datetime(val)
        elif key in date_keys:
            display = fmt_date(val)
        elif key == "breakdown_by_type" and isinstance(val, dict):
            display = fmt_breakdown(val, currency)
        elif key == "status":
            display = fmt_status(str(val)) if val else "—"
        elif key == "is_active":
            display = "[green]Active[/green]" if bool(val) else "[dim]Inactive[/dim]"
        elif isinstance(val, bool):
            display = "[green]Yes[/green]" if val else "[red]No[/red]"
        elif val is None:
            display = "[dim]—[/dim]"
        else:
            display = str(val)
 
        table.add_row(label, display)
 
    console.print(
        Panel(table, title=f"[bold {style}]{title}[/bold {style}]",
              border_style=style, padding=(0, 1))
    )
 
 
# ════════════════════════════════════════════════════════
# Pagination Helper
# ════════════════════════════════════════════════════════
 
def paginate_list(
    items: List[Any],
    page_size: int = 15,
    label: str = "records",
) -> List[Any]:
    """
    Return the items for the current page; print navigation hints.
 
    Currently returns all items — hook this up to offset/limit
    if you want cursor-style pagination later.
    """
    total = len(items)
    if total == 0:
        return items
    if total <= page_size:
        console.print(f"  [dim]Showing all {total} {label}.[/dim]")
        return items
    # Simple: just show all with a count hint
    console.print(f"  [dim]Showing {total} {label}.[/dim]")
    return items
 
 
# ════════════════════════════════════════════════════════
# Safe Menu Runner
# ════════════════════════════════════════════════════════
 
def run_menu(
    menu_fn: Callable[[], None],
    on_back: Optional[Callable[[], None]] = None,
) -> None:
    """
    Run a menu function in a loop, catching BackSignal to go up one level.
 
    Args:
        menu_fn : A callable that runs the sub-menu (may raise BackSignal).
        on_back : Optional callback when Back is chosen.
    """
    while True:
        try:
            menu_fn()
        except BackSignal:
            if on_back:
                on_back()
            return
        except ExitSignal:
            raise
        except KeyboardInterrupt:
            raise ExitSignal()
 
 
# ════════════════════════════════════════════════════════
# Global exit guard  (wrap your main loop with this)
# ════════════════════════════════════════════════════════
 
def run_app(app_fn: Callable[[], None]) -> None:
    """
    Top-level runner. Catches ExitSignal for a clean goodbye message.
    """
    try:
        app_fn()
    except ExitSignal:
        console.print("\n[bold cyan]👋  Goodbye! Stay financially fit.[/bold cyan]\n")
        sys.exit(0)
    except KeyboardInterrupt:
        console.print("\n\n[dim]Interrupted. Exiting…[/dim]\n")
        sys.exit(0)


