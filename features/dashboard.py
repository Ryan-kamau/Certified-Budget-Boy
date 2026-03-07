# features/Dashboard.py
"""
CLI Dashboard  —  Rich + Matplotlib hybrid
-------------------------------------------
Rich handles all tabular/panel display in the terminal.
Matplotlib handles detailed graphs via plt.show() on explicit request.

Rich sections  (always available)
----------------------------------
  render()            – full dashboard
  render_summary()    – net-worth + cash-flow panels
  render_trends()     – monthly trend table
  render_categories() – category spending table

Matplotlib charts  (pop-up, only when requested)
-------------------------------------------------
  show_chart(name)    – single chart by name
  show_all_charts()   – all four charts sequentially
  charts_menu()       – interactive CLI menu to pick charts

Chart names
-----------
  "monthly"    – all transaction types as lines across 12 months
  "donut"      – spending by category donut chart
  "heatmap"    – daily spending calendar heatmap
  "networth"   – net worth over time line chart
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import mysql.connector

# ── Rich imports ──────────────────────────────────────────────────────────────
from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# ── Project imports ───────────────────────────────────────────────────────────
from models.analytics_model import AnalyticsModel
from features.balance import BalanceService
from models.transactions_model import TransactionModel
from core.scheduler import Scheduler
from features.charts import FinanceCharts

console = Console()


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_currency(amount: float, currency: str = "KES") -> str:
    sign   = "+" if amount > 0 else ""
    colour = "green" if amount >= 0 else "red"
    return f"[{colour}]{sign}{currency} {amount:,.2f}[/{colour}]"


def _fmt_date(d: Any) -> str:
    if isinstance(d, (datetime, date)):
        return d.strftime("%d %b %Y")
    if isinstance(d, str):
        return d[:10]
    return str(d)


def _bar_ascii(pct: float, width: int = 20) -> str:
    filled = int(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


_TX_COLOR: Dict[str, str] = {
    "income":               "green",
    "expense":              "red",
    "transfer":             "cyan",
    "debt_borrowed":        "yellow",
    "debt_repaid":          "blue",
    "investment_deposit":   "magenta",
    "investment_withdraw":  "dark_orange",
}

_CATEGORY_PALETTE = [
    "bold red", "bold dark_orange", "bold yellow",
    "bold green", "bold cyan", "bold blue",
    "bold magenta", "bold white",
]

_CHARTS = {
    "monthly":  ("📈 Monthly Transaction Types",    "monthly_transactions"),
    "donut":    ("🍩 Spending by Category (Donut)", "category_donut"),
    "heatmap":  ("🗓  Daily Spending Heatmap",       "daily_heatmap"),
    "networth": ("💎 Net Worth Over Time",           "net_worth_over_time"),
}


# ════════════════════════════════════════════════════════════════════════════
# Dashboard
# ════════════════════════════════════════════════════════════════════════════

class Dashboard:
    """
    Rich + Matplotlib hybrid dashboard.

    Parameters
    ----------
    conn         : live MySQL connection
    current_user : authenticated user dict
    currency     : currency label (default "KES")
    """

    def __init__(
        self,
        conn: mysql.connector.MySQLConnection,
        current_user: Dict[str, Any],
        currency: str = "KES",
    ) -> None:
        self.conn     = conn
        self.user     = current_user
        self.currency = currency

        self._analytics = AnalyticsModel(conn, current_user)
        self._balance   = BalanceService(conn, current_user)
        self._tx        = TransactionModel(conn, current_user)
        self._scheduler = Scheduler(conn, current_user)
        self._charts: Optional[FinanceCharts] = None   # lazy-init

    # ── helpers ──────────────────────────────────────────────────────────────

    def _c(self, amount: float) -> str:
        return _fmt_currency(amount, self.currency)

    def _get_charts(self) -> FinanceCharts:
        """Lazy-init FinanceCharts — matplotlib only imported when a chart is needed."""
        if self._charts is None:
            self._charts = FinanceCharts(self.conn, self.user, currency=self.currency)
        return self._charts

    def _load_snapshot(
        self,
        top_n: int = 10,
        recent_limit: int = 20,
        upcoming_days: int = 7,
    ) -> Dict[str, Any]:
        today = date.today()
        return {
            "net_worth":        self._balance.get_net_worth(),
            "account_balances": self._balance.get_all_balances(include_deleted=False),
            "cashflow":         self._analytics.summary(
                                    start_date=today.replace(day=1),
                                    end_date=today,
                                ),
            "top_categories":   self._analytics.top_categories(
                                    transaction_type="expense",
                                    limit=top_n,
                                    start_date=today.replace(day=1),
                                    end_date=today,
                                ),
            "monthly_trends":   self._analytics.monthly_comparison(year=today.year),
            "recent_txs":       self._tx.list_transactions(
                                    limit=recent_limit,
                                    include_deleted=False,
                                ).get("transactions", []),
            "upcoming":         self._scheduler.get_upcoming_due(days_ahead=upcoming_days),
            "generated_at":     datetime.now().isoformat(timespec="seconds"),
        }
    
    # ────────────────────────────────────────────────────────────────────────
    # Rich render helpers
    # ────────────────────────────────────────────────────────────────────────

    def _render_header(self) -> None:
        username = self.user.get("username", "User")
        ts       = datetime.now().strftime("%A, %d %b %Y  %H:%M")
        console.print(Rule(
            f"[bold cyan]💰 Finance Dashboard[/bold cyan]  "
            f"[dim]│  {username}  │  {ts}[/dim]",
            style="cyan",
        ))

    def _render_net_worth(self, net_worth: Dict[str, Any]) -> None:
        total  = net_worth.get("total_net_worth", 0.0)
        active = net_worth.get("active_accounts",  0)

        nw_text = Text()
        nw_text.append("Net Worth\n", style="bold dim")
        nw_text.append(f"{self.currency} {total:,.2f}",
                       style="bold green" if total >= 0 else "bold red")
        nw_text.append(f"\n{active} active account(s)", style="dim")

        breakdown = net_worth.get("breakdown_by_type", {})
        bd_table  = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        bd_table.add_column("Type",    style="bold cyan",  no_wrap=True)
        bd_table.add_column("Balance", style="bold white", justify="right")
        for acc_type, bal in sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True):
            bd_table.add_row(acc_type.replace("_", " ").title(), self._c(float(bal)))

        console.print(Columns([
            Panel(Align.center(nw_text), title="[bold]💎 Net Worth[/bold]",
                  border_style="green" if total >= 0 else "red", padding=(1, 4)),
            Panel(bd_table, title="[bold]🏦 By Account Type[/bold]", border_style="cyan"),
        ], equal=False, expand=True))

    def _render_cashflow(self, cf: Dict[str, Any]) -> None:
        console.print(Rule("[bold]📊 This Month's Cash Flow[/bold]", style="blue"))

        income  = cf.get("total_income",    0.0)
        expense = cf.get("total_expenses",  0.0)
        net     = cf.get("net_cash_flow",   income - expense)
        rate    = cf.get("savings_rate",    (net / income * 100) if income else 0.0)
        tx_cnt  = cf.get("transaction_count", 0)

        def _card(title: str, value: str, sub: str, colour: str) -> Panel:
            body = Text()
            body.append(value + "\n", style=f"bold {colour}")
            body.append(sub, style="dim")
            return Panel(Align.center(body), title=f"[bold]{title}[/bold]",
                         border_style=colour, padding=(1, 2))

        net_col  = "green"  if net  >= 0 else "red"
        rate_col = "green"  if rate >= 20 else ("yellow" if rate >= 0 else "red")

        console.print(Columns([
            _card("💵 Income",       self._c(income),  f"{tx_cnt} txns", "green"),
            _card("💸 Expenses",     self._c(expense), f"{tx_cnt} txns", "red"),
            _card("💰 Net Savings",  self._c(net),     "this month",     net_col),
            _card("📈 Savings Rate", f"{rate:.1f}%",   "of income",      rate_col),
        ], equal=True, expand=True))

        debt_in  = cf.get("total_debt_in",  0.0)
        debt_out = cf.get("total_debt_out", 0.0)
        invested = cf.get("total_invested", cf.get("total_investment_deposit", 0.0))
        if any([debt_in, debt_out, invested]):
            side = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
            side.add_column("Label",  style="bold dim")
            side.add_column("Amount", justify="right")
            if debt_in:  side.add_row("Debt Borrowed", self._c(debt_in))
            if debt_out: side.add_row("Debt Repaid",   self._c(-debt_out))
            if invested: side.add_row("Invested",      self._c(-invested))
            console.print(Panel(side, title="[bold]📋 Other Flows[/bold]",
                                border_style="yellow"))

    def _render_category_chart(self, categories: List[Dict[str, Any]]) -> None:
        if not categories:
            console.print(Panel("[dim]No expense data for this period.[/dim]",
                                title="[bold]🗂 Spending by Category[/bold]"))
            return

        console.print(Rule("[bold]🗂 Spending by Category[/bold]", style="magenta"))
        table = Table(box=box.ROUNDED, show_header=True,
                      header_style="bold magenta", expand=True)
        table.add_column("#",        width=3,      justify="right", style="dim")
        table.add_column("Category", min_width=16)
        table.add_column("Amount",   justify="right", style="bold white")
        table.add_column("%",        justify="right",  style="cyan",  width=6)
        table.add_column("Bar",      min_width=22, no_wrap=True)
        table.add_column("Txns",     justify="right",  style="dim",   width=5)

        for i, row in enumerate(categories):
            colour = _CATEGORY_PALETTE[i % len(_CATEGORY_PALETTE)]
            table.add_row(
                str(i + 1),
                row["category_name"],
                f"{self.currency} {row['total']:,.2f}",
                f"{row['percentage']:.1f}%",
                Text(_bar_ascii(row["percentage"], 22), style=colour),
                str(row["count"]),
            )
        console.print(table)

    def _render_monthly_trends(self, trends: List[Dict[str, Any]]) -> None:
        active = [r for r in trends if r["total_income"] or r["total_expenses"]]
        if not active:
            return

        console.print(Rule("[bold]📅 Monthly Trends[/bold]", style="blue"))
        table = Table(box=box.SIMPLE_HEAD, show_header=True,
                      header_style="bold blue", expand=True)
        table.add_column("Month",    width=6)
        table.add_column("Income",   justify="right")
        table.add_column("Expenses", justify="right")
        table.add_column("Net",      justify="right")
        table.add_column("Rate",     justify="right", width=7)
        table.add_column("Trend",    min_width=20, no_wrap=True)

        scale = max(
            max((r["total_income"]   for r in active), default=1),
            max((r["total_expenses"] for r in active), default=1),
        ) or 1

        for row in active:
            inc  = row["total_income"]
            exp  = row["total_expenses"]
            net  = row["net"]
            rate = (net / inc * 100) if inc > 0 else 0.0
            nc   = "green"  if net  >= 0 else "red"
            rc   = "green"  if rate >= 20 else ("yellow" if rate >= 0 else "red")
            bar  = (
                Text("▐", style="dim")
                + Text("█" * int(inc / scale * 14), style="green")
                + Text("│", style="dim white")
                + Text("█" * int(exp / scale * 14), style="red")
                + Text("▌", style="dim")
            )
            table.add_row(
                row["month_label"],
                f"[green]{self.currency} {inc:,.0f}[/green]",
                f"[red]{self.currency} {exp:,.0f}[/red]",
                f"[{nc}]{self.currency} {net:,.0f}[/{nc}]",
                f"[{rc}]{rate:.1f}%[/{rc}]",
                bar,
            )
        console.print(table)

    def _render_account_balances(self, balances: List[Dict[str, Any]]) -> None:
        if not balances:
            return
        console.print(Rule("[bold]🏦 Account Balances[/bold]", style="cyan"))
        table = Table(box=box.SIMPLE_HEAD, show_header=True,
                      header_style="bold cyan", expand=True)
        table.add_column("Account", min_width=18)
        table.add_column("Type",    width=16)
        table.add_column("Balance", justify="right")
        table.add_column("Opening", justify="right", style="dim")
        table.add_column("Δ",       justify="right", width=14)

        for acc in balances:
            if not acc.get("is_active"):
                continue
            current = float(acc.get("current_balance", 0))
            opening = float(acc.get("opening_balance", 0))
            delta   = current - opening
            d_col   = "green" if delta >= 0 else "red"
            table.add_row(
                acc.get("account_name", "—"),
                acc.get("account_type", "—").replace("_", " ").title(),
                f"[bold]{self.currency} {current:,.2f}[/bold]",
                f"{self.currency} {opening:,.2f}",
                f"[{d_col}]{'+' if delta >= 0 else ''}{self.currency} {delta:,.2f}[/{d_col}]",
            )
        console.print(table)

    def _render_recent_transactions(self, txs: List[Dict[str, Any]]) -> None:
        if not txs:
            return
        console.print(Rule("[bold]🕐 Recent Transactions[/bold]", style="white"))
        table = Table(box=box.SIMPLE_HEAD, show_header=True,
                      header_style="bold white", expand=True)
        table.add_column("Date",     width=12)
        table.add_column("Title",    min_width=20)
        table.add_column("Category", min_width=14, style="dim")
        table.add_column("Type",     width=18)
        table.add_column("Account",  min_width=14, style="dim")
        table.add_column("Amount",   justify="right")

        for tx in txs:
            tx_type = tx.get("transaction_type", "")
            colour  = _TX_COLOR.get(tx_type, "white")
            amount  = float(tx.get("amount", 0))
            sign    = "-" if tx_type in ("expense", "debt_repaid", "investment_deposit") else "+"
            account = tx.get("account_name") or tx.get("source_account_name") or "—"
            table.add_row(
                _fmt_date(tx.get("transaction_date")),
                tx.get("title", "—")[:30],
                (tx.get("category_name") or "—")[:16],
                f"[{colour}]{tx_type.replace('_', ' ').title()}[/{colour}]",
                account[:16],
                f"[{colour}]{sign}{self.currency} {amount:,.2f}[/{colour}]",
            )
        console.print(table)

    def _render_upcoming(self, upcoming: List[Dict[str, Any]]) -> None:
        if not upcoming:
            console.print(Panel(
                "[dim]No upcoming recurring transactions in the next 7 days.[/dim]",
                title="[bold]🔔 Upcoming Bills[/bold]", border_style="dim"))
            return
        console.print(Rule("[bold]🔔 Upcoming Recurring Bills[/bold]", style="yellow"))
        table = Table(box=box.SIMPLE_HEAD, show_header=True,
                      header_style="bold yellow", expand=True)
        table.add_column("Due Date",  width=18)
        table.add_column("Name",      min_width=20)
        table.add_column("Frequency", width=10, style="dim")
        table.add_column("Type",      width=16)
        table.add_column("Amount",    justify="right")

        today = date.today()
        for r in upcoming:
            due   = r.get("next_due")
            due_d = due.date() if isinstance(due, datetime) else due
            days  = (due_d - today).days if isinstance(due_d, date) else 99
            urg   = ("bold red" if days <= 1 else
                     "bold yellow" if days <= 3 else "bold green")
            tx_type = r.get("transaction_type", "")
            colour  = _TX_COLOR.get(tx_type, "white")
            table.add_row(
                f"[{urg}]{_fmt_date(due)} ({days}d)[/{urg}]",
                r.get("name", "—")[:28],
                r.get("frequency", "—"),
                f"[{colour}]{tx_type.replace('_', ' ').title()}[/{colour}]",
                f"[bold]{self.currency} {float(r.get('amount', 0)):,.2f}[/bold]",
            )
        console.print(table)

    # ────────────────────────────────────────────────────────────────────────
    # Public Rich render methods
    # ────────────────────────────────────────────────────────────────────────

    def render_summary(self) -> None:
        snap = self._load_snapshot()
        self._render_header()
        self._render_net_worth(snap["net_worth"])
        self._render_cashflow(snap["cashflow"])

    def render_trends(self) -> None:
        snap = self._load_snapshot()
        self._render_monthly_trends(snap["monthly_trends"])

    def render_categories(self) -> None:
        snap = self._load_snapshot()
        self._render_category_chart(snap["top_categories"])

    def render(
        self,
        top_categories: int = 8,
        recent_limit: int = 10,
        upcoming_days: int = 7,
    ) -> None:
        """Full Rich dashboard in one shot."""
        try:
            with console.status("[bold cyan]Loading dashboard data…[/bold cyan]",
                                spinner="dots"):
                snap = self._load_snapshot(
                    top_n=top_categories,
                    recent_limit=recent_limit,
                    upcoming_days=upcoming_days,
                )
        except Exception as e:
            console.print(f"[bold red]❌ Dashboard error:[/bold red] {e}")
            return

        self._render_header();                                     console.print()
        self._render_net_worth(snap["net_worth"]);                 console.print()
        self._render_cashflow(snap["cashflow"]);                   console.print()
        self._render_account_balances(snap["account_balances"]);   console.print()
        self._render_category_chart(snap["top_categories"]);       console.print()
        self._render_monthly_trends(snap["monthly_trends"]);       console.print()
        self._render_recent_transactions(snap["recent_txs"]);      console.print()
        self._render_upcoming(snap["upcoming"]);                   console.print()
        console.print(Rule(f"[dim]Generated at {snap['generated_at']}[/dim]",
                           style="dim"))
        console.print()
        console.print(Panel(
            "[cyan]Tip:[/cyan] Call [bold]dash.charts_menu()[/bold] or "
            "[bold]dash.show_chart(\"monthly\" | \"donut\" | \"heatmap\" | \"networth\")[/bold]"
            " to open detailed graphs.",
            border_style="dim", padding=(0, 2),
        ))

    # ────────────────────────────────────────────────────────────────────────
    # Public matplotlib chart methods
    # ────────────────────────────────────────────────────────────────────────

    def show_chart(self, name: str) -> None:
        """
        Open a single matplotlib chart by name.
        Names: "monthly" | "donut" | "heatmap" | "networth"
        """
        if name not in _CHARTS:
            valid = ", ".join(f'"{k}"' for k in _CHARTS)
            console.print(f"[red]Unknown chart '{name}'. Valid: {valid}[/red]")
            return
        label, method_name = _CHARTS[name]
        console.print(f"[cyan]Opening:[/cyan] {label} …")
        getattr(self._get_charts(), method_name)()

    def show_all_charts(self) -> None:
        """Open all four matplotlib charts sequentially."""
        console.print("[cyan]Opening all charts…[/cyan] Close each window to continue.")
        self._get_charts().show_all()

    def charts_menu(self) -> None:
        """Interactive menu to pick which charts to display."""
        console.print()
        console.print(Rule("[bold yellow]📊 Charts Menu[/bold yellow]", style="yellow"))

        options = list(_CHARTS.items())
        while True:
            console.print()
            menu = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
            menu.add_column("Key",   style="bold cyan", width=4)
            menu.add_column("Chart", style="bold white")
            for i, (_, (label, _)) in enumerate(options, 1):
                menu.add_row(str(i), label)
            menu.add_row("A", "🚀 All charts")
            menu.add_row("Q", "↩  Quit")
            console.print(menu)

            choice = Prompt.ask("[cyan]Choose[/cyan]", default="Q").strip().upper()

            if choice == "Q":
                break
            elif choice == "A":
                self.show_all_charts()
            elif choice.isdigit() and 1 <= int(choice) <= len(options):
                _, (label, method_name) = options[int(choice) - 1]
                console.print(f"[cyan]Opening:[/cyan] {label} …")
                getattr(self._get_charts(), method_name)()
            else:
                console.print("[red]Invalid choice.[/red]")

        console.print(Rule("[dim]Charts menu closed[/dim]", style="dim"))


# ════════════════════════════════════════════════════════════════════════════
# Standalone entry point
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    from core.database import DatabaseConnection
    from models.user_model import UserModel

    console.print("\n[bold cyan]🔐 Finance Dashboard — Login[/bold cyan]\n")
    db   = DatabaseConnection()
    conn = db.get_connection()

    if not conn:
        console.print("[bold red]❌ Could not connect to the database.[/bold red]")
        return

    username = input("Username: ").strip()
    password = input("Password: ").strip()
    um       = UserModel(conn)
    auth     = um.authenticate(username, password)

    if not auth.get("success"):
        console.print(f"[bold red]❌ {auth.get('message')}[/bold red]")
        return

    current_user = auth["user"]
    console.print(f"\n[green]✅ Welcome, {current_user.get('username')}![/green]\n")

    dash = Dashboard(conn, current_user)
    dash.render()

    if Prompt.ask("\n[yellow]Open charts?[/yellow]", choices=["y", "n"], default="n") == "y":
        dash.charts_menu()

    conn.close()


if __name__ == "__main__":
    main()