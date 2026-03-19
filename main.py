#entry point
"""
============================================================
 FinTrack — Personal Finance Tracker  (CLI Entry Point)
 -----------------------------------------------------------
 Wire-up:  auth → accounts → categories → transactions
           → analytics → goals → recurring → search → charts
 
 Run:  python main.py
============================================================
"""
 
from __future__ import annotations
 
import re
import sys
import traceback
from datetime import date, datetime
from typing import Any, Dict, Optional, Text
 
# ── Rich ─────────────────────────────────────────────────
from matplotlib import category
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.align import Align
 
console = Console()
 
# ── Project core ─────────────────────────────────────────
from core.database import DatabaseConnection
from core.cli_helpers import (
    # Signals
    BackSignal, ExitSignal, LogoutSignal,
    # UI
    clear_screen, fmt_datetime, pause, print_app_banner, print_header,
    print_section, print_success, print_error, print_warning,
    print_info, print_result, print_detail_panel, print_table,
    # Prompts
    prompt_choice, ask_str, ask_int, ask_float, ask_date,
    ask_choice, ask_confirm, ask_password,
    # Formatters
    fmt_money, fmt_date, fmt_status,
    # Helpers
    run_app,
)
from core.scheduler import Scheduler
from core.utils import ValidationPatterns
 
# ── Models ───────────────────────────────────────────────
from models.user_model        import UserModel
from models.account_model     import AccountModel
from models.category_model    import CategoryModel
from models.transactions_model import TransactionModel
from models.analytics_model   import AnalyticsModel
 
# ── Features ─────────────────────────────────────────────
from features.balance   import BalanceService
from features.goals     import GoalService
from features.charts    import FinanceCharts
from features.dashboard import Dashboard
from features.search    import SearchService
from features.recurring import RecurringModel
from features.export_reports import ExportService, ExportConfig, ExportMetadata
from  features.insights import InsightsEngine
from features.search import (
        TransactionSearchRequest, DateFilter, AmountFilter, TextSearchFilter,
        TransactionTypeFilter, SortOptions, CategoryFilter, CategorySearchRequest, AccountFilter, Pagination)

 
 
# ════════════════════════════════════════════════════════
# App State  (simple shared context passed around)
# ════════════════════════════════════════════════════════
 
class AppCtx:
    """Holds the live session — DB connection + authenticated user + services."""
 
    def __init__(self, conn: Any, user: Dict[str, Any]) -> None:
        self.conn = conn
        self.user = user
 
        # Initialise all services once
        self.accounts    = AccountModel(conn, user)
        self.categories  = CategoryModel(conn, user)
        self.transactions = TransactionModel(conn, user)
        self.analytics   = AnalyticsModel(conn, user)
        self.balance     = BalanceService(conn, user)
        self.goals       = GoalService(conn, user)
        self.recurring   = RecurringModel(conn, user)
        self.search_svc  = SearchService(conn, user)
        self.dashboard   = Dashboard(conn, user)
        self.charts      = FinanceCharts(conn, user)
        self.scheduler   = Scheduler(conn, user)
        self.exports     = ExportService(conn, user)
        self.insights    = InsightsEngine(conn, user)
 
    @property
    def username(self) -> str:
        return self.user.get("username", "")
 
    @property
    def role(self) -> str:
        return self.user.get("role", "user")
 
    @property
    def user_id(self) -> int:
        return self.user.get("user_id", 0)
 
    def is_admin(self) -> bool:
        return self.role == "admin"
 
 
# ════════════════════════════════════════════════════════
# ① AUTH SCREEN
# ════════════════════════════════════════════════════════
 
def auth_screen(conn: Any) -> AppCtx:
    """
    Show login / register options and return an authenticated AppCtx.
    Loops until valid credentials are provided or user exits.
    """
    um = UserModel(conn)
 
    while True:
        clear_screen()
        print_app_banner()
        print_header("Welcome — Please Sign In or Register", style="cyan")
 
        try:
            choice = prompt_choice(
                [
                    ("Login",            "Sign in with your username & password"),
                    ("Register",         "Create a new account"),
                    ("Forgot Password",  "Reset via security answer"),
                ],
                title="🔐  Authentication",
                show_back=False,
                show_exit=True,
                footer_hint="Enter 1, 2 or 3  (0 to exit)",
            )
        except ExitSignal:
            raise
 
        # ── Login ────────────────────────────────────────
        if choice == 1:
            console.print()
            username = ask_str("Username", allow_back=False)
            password = ask_password("Password")
 
            result = um.authenticate(username, password)
            if result.get("success"):
                user = result["user"]
                print_success(f"Welcome back, [bold cyan]{user['username']}[/bold cyan]!")
                pause()
                return AppCtx(conn, user)
            else:
                print_error(result.get("message", "Login failed."))
                pause()
 
        # ── Register ─────────────────────────────────────
        elif choice == 2:
            console.print()
            print_section("📝  Create Account")
            username = ask_str("Choose a username", allow_back=True)
            password = ask_password("Choose a password (min 6 chars)")
            sec_ans  = ask_str("Security answer (used for password reset)",
                               allow_back=True)
            role     = ask_choice("Role", ["user", "admin"],
                                  default="user", allow_back=True)
 
            result = um.register(username, password, sec_ans, role)
            if result.get("success"):
                print_success(f"Account created! Please log in as '[cyan]{username}[/cyan]'.")
            else:
                print_error(result.get("message", "Registration failed."))
            pause()
 
        # ── Forgot Password ───────────────────────────────
        elif choice == 3:
            console.print()
            print_section("🔑  Password Reset")
            security_question = um.get_security_question()
            # Need a temp logged-in context for change_password (it requires _require_login)
            # Workaround: direct SQL-level reset via authenticate flow
            username = ask_str("Your username", allow_back=True)
            sec_ans  = ask_str(f"Security answer: {security_question}", allow_back=True)
            new_pass = ask_password("New password (min 6 chars)")
 
            # Authenticate with security answer path
            user_row = um._get_user_by_username(username)
            if not user_row:
                print_error("Username not found.")
                pause()
                continue
 
            import bcrypt
            if not bcrypt.checkpw(
                sec_ans.encode("utf-8"),
                user_row["security_answer_hash"].encode("utf-8"),
            ):
                print_error("Incorrect security answer.")
                pause()
                continue
 
            # Temporarily log in to allow change_password
            um.current_user = {"user_id": user_row["user_id"],
                                "username": user_row["username"],
                                "role": user_row["role"]}
            result = um.change_password(username, new_pass, sec_ans)
            um.current_user = None
 
            print_result(result)
            pause()
 
 # ════════════════════════════════════════════════════════
# ② MAIN APP MENU
# ════════════════════════════════════════════════════════
 
def app_main(ctx: AppCtx) -> None:
    """
    Top-level application loop.
    Each sub-menu function is called; BackSignal brings you back here.
    """
    MAIN_MENU = [
        ("📊  Dashboard",       "Overview • net worth • cash flow • charts"),
        ("🏦  Accounts",        "Create, view and manage accounts"),
        ("🗂   Categories",      "Organise your spending categories"),
        ("💸  Transactions",    "Record income, expenses & transfers"),
        ("📈  Analytics",       "Reports, trends & insights"),
        ("🎯  Goals",           "Track savings and spending goals"),
        ("🔁  Recurring",       "Scheduled & recurring transactions"),
        ("🔍  Search",          "Filter and find any transaction"),
        ("🗓️   Scheduler",          "Run, monitor & control recurring rules"),
        ("💡  Insights",           "Smart tips, anomaly alerts & spending analysis"),
        ("📤  Export / Reports",   "CSV, PDF & Excel exports"),
        ("👤  Account Settings","Change password, user management"),
    ]
 
    HANDLERS = [
        menu_dashboard,
        menu_accounts,
        menu_categories,
        menu_transactions,
        menu_analytics,
        menu_goals,
        menu_recurring,
        menu_search,
        menu_scheduler,
        menu_insights,
        menu_exports,
        menu_settings,
    ]
 
    while True:
        clear_screen()
        print_header(
            "💰  FinTrack",
            subtitle="Personal Finance Tracker",
            username=ctx.username,
            role=ctx.role,
        )
 
        try:
            choice = prompt_choice(
                MAIN_MENU,
                title="Main Menu",
                show_back=False,
                show_exit=True,
            )
        except ExitSignal:
            if ask_confirm("Exit FinTrack?", default=False):
                raise
            continue
 
        handler = HANDLERS[choice - 1]
        try:
            handler(ctx)
        except BackSignal:
            pass   # return to main menu
        except LogoutSignal:
            raise  # bubble up to restart auth screen
        except ExitSignal:
            raise
        except Exception as exc:
            print_error(f"Unexpected error: {exc}")
            if ctx.is_admin():
                traceback.print_exc()
            pause()
 
 
# ════════════════════════════════════════════════════════
# ③ DASHBOARD
# ════════════════════════════════════════════════════════
 
def menu_dashboard(ctx: AppCtx) -> None:
    ITEMS = [
        ("Full Dashboard",        "All panels + summaries"),
        ("Summary",               "Net worth + cash flow"),
        ("Monthly Trends",        "Month-by-month table"),
        ("Top Categories",        "Spending breakdown"),
        ("📈 Monthly Line Chart", "Transaction types over 12 months"),
        ("🍩 Category Donut",     "Spending by category"),
        ("🗓  Spending Heatmap",   "Daily calendar heatmap"),
        ("💎 Net Worth Chart",    "Net worth over time"),
    ]
 
    while True:
        clear_screen()
        print_header("📊  Dashboard", username=ctx.username, role=ctx.role)
 
        try:
            choice = prompt_choice(ITEMS, title="Dashboard", show_back=True)
        except BackSignal:
            return
 
        try:
            if choice == 1:
                console.print()
                ctx.dashboard.render(top_categories=10, recent_limit=10, upcoming_days=10)
                pause()
            elif choice == 2:
                console.print()
                ctx.dashboard.render_summary()
                pause()
            elif choice == 3:
                console.print()
                ctx.dashboard.render_trends()
                pause()
            elif choice == 4:
                console.print()
                ctx.dashboard.render_categories()
                pause()
            elif choice == 5:
                print_info("Opening chart window…")
                ctx.charts.monthly_transactions()
            elif choice == 6:
                print_info("Opening chart window…")
                ctx.charts.category_donut()
            elif choice == 7:
                print_info("Opening chart window…")
                ctx.charts.daily_heatmap()
            elif choice == 8:
                print_info("Opening chart window…")
                ctx.charts.net_worth_over_time()
        except Exception as exc:
            print_error(str(exc))
            pause()
 
 
# ════════════════════════════════════════════════════════
# ④ ACCOUNTS
# ════════════════════════════════════════════════════════
 
ACCOUNT_TYPES = ["cash", "bank", "mobile_money", "credit", "savings", "investments", "other"]
 
def menu_accounts(ctx: AppCtx) -> None:
    ITEMS = [
        ("List Accounts",     "See all your accounts with balances"),
        ("Create Account",    "Add a new account"),
        ("View Account",      "Get full details of one account"),
        ("Update Account",    "Rename or change account fields"),
        ("Soft-Delete",       "Hide an account (recoverable)"),
        ("Restore Account",   "Un-delete a hidden account"),
        ("Balance Health",    "Run a balance integrity check"),
        ("Net Worth",         "Total net worth across all accounts"),
        ("🗓️   Scheduler",          "Run, monitor & control recurring rules"),
        ("Audit Logs",        "View account audit history"),
    ]
 
    while True:
        clear_screen()
        print_header("🏦  Accounts", username=ctx.username, role=ctx.role)
 
        try:
            choice = prompt_choice(ITEMS, title="Accounts", show_back=True)
        except BackSignal:
            return
 
        try:
            # ── List ─────────────────────────────────
            if choice == 1:
                res = ctx.accounts.list_account()
                accs = res.get("accounts", [])
                print_table(
                    accs,
                    columns=[
                        ("ID",      "account_id"),
                        ("Name",    "name"),
                        ("Type",    "account_type"),
                        ("Balance", "balance"),
                        ("Status",  "is_active"),
                    ],
                    title=f"Your Accounts ({len(accs)})",
                    formatters={"balance": lambda v: fmt_money(v),
                                "is_active": lambda c: "Active" if bool(c) else "Inactive"},
                )
                pause()
 
            # ── Create ────────────────────────────────
            elif choice == 2:
                print_section("➕  Create Account")
                name     = ask_str("Account name")
                acc_type = ask_choice("Account type", ACCOUNT_TYPES, default="bank")
                balance  = ask_float("Opening balance", default=0.0, min_val=0)
                desc     = ask_str("Description", required=False)
                is_global = ask_str("Is global? (y/n)", default="n", required=False)
                opening_balance = ask_float("Opening balance", default=balance, min_val=0)
 
                result = ctx.accounts.create_account(
                    name=name,
                    account_type=acc_type,
                    is_global=is_global,
                    balance=balance,
                    opening_balance=opening_balance,
                    description=desc,
                )
                print_result(result)
                pause()
 
            # ── View ──────────────────────────────────
            elif choice == 3:
                acc_id = ask_int("Account ID")
                acc    = ctx.accounts.get_account(acc_id)
                print_detail_panel(
                    acc,
                    title=f"Account #{acc_id}",
                    currency_keys={"balance"},
                    date_keys={"created_at", "updated_at"},
                )
                pause()
 
            # ── Update ────────────────────────────────
            elif choice == 4:
                acc_id = ask_int("Account ID to update")
                print_info("Leave fields blank to skip.")
                updates = {}
                for field, prompt_txt in [
                    ("name",         "New name"),
                    ("account_type", f"New type ({'/'.join(ACCOUNT_TYPES)})"),
                    ("description",  "New description"),
                    ("balance",        "New balance"),
                ]:
                    val = ask_str(prompt_txt, required=False)
                    if val:
                        if field == "account_type" and val not in ACCOUNT_TYPES:
                            print_warning(f"Invalid type — skipping.")
                            continue
                        updates[field] = val
 
                if updates:
                    result = ctx.accounts.update_account(acc_id, source="cli", **updates)
                    print_result(result)
                else:
                    print_warning("No changes entered.")
                pause()
 
            # ── Soft Delete ───────────────────────────
            elif choice == 5:
                acc_id = ask_int("Account ID to delete")
                if ask_confirm(f"Soft-delete account #{acc_id}?"):
                    result = ctx.accounts.soft_delete_account(acc_id)
                    print_result(result)
                pause()
 
            # ── Restore ───────────────────────────────
            elif choice == 6:
                acc_id = ask_int("Account ID to restore")
                result = ctx.accounts.restore_account(acc_id)
                print_result(result)
                pause()
 
            # ── Balance Health ────────────────────────
            elif choice == 7:
                result = ctx.balance.run_balance_health_check()
                issues = result.get("issues", [])
                if issues:
                    print_warning(f"{len(issues)} balance discrepancy/ies found:")
                    for issue in issues:
                        console.print(f"  [red]•[/red] {issue}")
                else:
                    print_success("All account balances are healthy ✔")
                pause()
 
            # ── Net Worth ────────────────────────────
            elif choice == 8:
                nw = ctx.balance.get_net_worth()
                print_detail_panel(
                    nw,
                    title="Net Worth Summary",
                    currency_keys={"total_net_worth"},
                    style="green",
                )
                pause()
 
            # ── Audit Logs ───────────────────────────
            elif choice == 9:
                acc_id = ask_int("Account ID (blank for all)", required=False)
                logs   = ctx.accounts.view_audit_logs(account_id=acc_id)
                print_table(
                    logs,
                    columns=[
                        ("Time",     "created_at"),
                        ("Action",   "action"),
                        ("Changed",  "changed_fields"),
                    ],
                    title="Audit Logs",
                    formatters={"created_at": fmt_date},
                )
                pause()
 
        except BackSignal:
            pass
        except Exception as exc:
            print_error(str(exc))
            pause()
 
 
# ════════════════════════════════════════════════════════
# ⑤ CATEGORIES
# ════════════════════════════════════════════════════════
 
def menu_categories(ctx: AppCtx) -> None:
    ITEMS = [
        ("List Categories",   "View all your categories"),
        ("Create Category",   "Add a new category (optionally nested)"),
        ("View Category",     "Get details of one category"),
        ("Update Category",   "Rename or re-parent a category"),
        ("Delete Category",   "Soft-delete a category"),
        ("Restore Category",  "Recover a deleted category"),
        ("Category Tree",     "View full hierarchy tree"),
    ]
 
    while True:
        clear_screen()
        print_header("🗂   Categories", username=ctx.username, role=ctx.role)
 
        try:
            choice = prompt_choice(ITEMS, title="Categories", show_back=True)
        except BackSignal:
            return
 
        try:
            if choice == 1:
                res  = ctx.categories.list_categories()
                print_table(
                    res,
                    columns=[
                        ("ID",     "category_id"),
                        ("Name",   "name"),
                        ("Description", "description"),
                        ("Parent", "parent_id"),
                        ("Owner", "owned_by_username"),
                    ],
                    title="Categories",
                    empty_message="No categories yet — create one!",
                )
                pause()
 
            elif choice == 2:
                print_section("➕  Create Category")
                name      = ask_str("Category name")
                parent_id = ask_int("Parent category ID", required=False)
                desc      = ask_str("Description", required=False)
                is_global     = ask_str("Is global? (y/n)", required=False, default="n")
 
                result = ctx.categories.create_category(
                    name=name,
                    parent_id=parent_id,
                    description=desc,
                    is_global=is_global,
                )
                print_result(result)
                pause()
 
            elif choice == 3:
                cat_id = ask_int("Category ID")
                cat    = ctx.categories.get_category(cat_id)
                print_detail_panel(cat, title=f"Category #{cat_id}")
                pause()
 
            elif choice == 4:
                cat_id = ask_int("Category ID to update")
                print_info("Leave fields blank to skip.")
                updates = {}
                for field, prompt_txt in [
                    ("name",        "New name"),
                    ("description", "New description"),
                    ("parent_id",       "New parent ID"),
                    ("is_global",        "Is global? (y/n)"),
                ]:
                    val = ask_str(prompt_txt, required=False)
                    if val:
                        updates[field] = val
                new_parent = ask_int("New parent ID", required=False)
                if new_parent:
                    updates["parent_id"] = new_parent
 
                if updates:
                    result = ctx.categories.update_category(cat_id, **updates)
                    print_result(result)
                else:
                    print_warning("No changes entered.")
                pause()
 
            elif choice == 5:
                cat_id = ask_int("Category ID")
                if ask_confirm(f"Soft-delete category #{cat_id}?"):
                    result = ctx.categories.delete_category(cat_id, soft=True)
                    print_result(result)
                pause()
 
            elif choice == 6:
                cat_id = ask_int("Category ID to restore")
                result = ctx.categories.restore_category(cat_id)
                print_result(result)
                pause()
 
            elif choice == 7:
                tree = ctx.categories.list_categories(flat=False)
                _print_tree(tree)
                pause()
 
        except BackSignal:
            pass
        except Exception as exc:
            print_error(str(exc))
            pause()
 
 
def _print_tree(nodes: Any, indent: int = 0) -> None:
    """Recursively print a category tree."""
    if isinstance(nodes, dict):
        nodes = [nodes]
    if not nodes:
        print_info("No categories found.")
        return
    for node in nodes:
        prefix  = "  " * indent + ("└─ " if indent else "")
        name    = node.get("name", "?")
        cat_id  = node.get("category_id", "?")
        console.print(f"  {prefix}[cyan]{name}[/cyan]  [dim](Category ID: {cat_id})[/dim]")
        children = node.get("children", [])
        if children:
            _print_tree(children, indent + 1)
 
 
# ════════════════════════════════════════════════════════
# ⑥ TRANSACTIONS
# ════════════════════════════════════════════════════════
 
TX_TYPES    = ["income", "expense", "transfer", "debt_borrowed",
               "debt_repaid", "investment_deposit", "investment_withdraw"]
PAY_METHODS = ["cash", "bank", "mobile_money", "credit_card", "other"]
 
 
def menu_transactions(ctx: AppCtx) -> None:
    ITEMS = [
        ("Add Transaction",      "Record income, expense or transfer"),
        ("List Transactions",    "Browse recent transactions"),
        ("View Transaction",     "Full details of one transaction"),
        ("Update Transaction",   "Edit a recorded transaction"),
        ("Delete Transaction",   "Soft-delete a transaction"),
        ("Restore Transaction",  "Recover a deleted transaction"),
        ("Transaction Audit",    "View change history"),
    ]
 
    while True:
        clear_screen()
        print_header("💸  Transactions", username=ctx.username, role=ctx.role)
 
        try:
            choice = prompt_choice(ITEMS, title="Transactions", show_back=True)
        except BackSignal:
            return
 
        try:
            if choice == 1:
                _add_transaction(ctx)
 
            elif choice == 2:
                _list_transactions(ctx)
 
            elif choice == 3:
                tx_id  = ask_int("Transaction ID")
                result = ctx.transactions.get_transaction(tx_id)
                print_detail_panel(
                    result,
                    title=f"Transaction #{tx_id}",
                    currency_keys={"amount"},
                    date_keys={"transaction_date", "created_at"},
                )
                pause()
 
            elif choice == 4:
                _update_transaction(ctx)
 
            elif choice == 5:
                tx_id = ask_int("Transaction ID")
                hard  = ask_confirm("Hard delete? (cannot be undone)", default=False)
                result = ctx.transactions.delete_transaction(
                    tx_id, soft=not hard
                )
                print_result(result)
                pause()
 
            elif choice == 6:
                tx_id  = ask_int("Transaction ID")
                result = ctx.transactions.restore_transaction(tx_id)
                print_result(result)
                pause()
 
            elif choice == 7:
                tx_id = ask_int("Transaction ID (blank for all)", required=False)
                start_date = ask_date("Start date (optional)", required=False, default=date.today().replace(day=1))
                end_date   = ask_date("End date (optional)", required=False, default=date.today())
                logs  = ctx.transactions.view_audit_logs(target_id=tx_id, start_date=start_date, end_date=end_date)
                print_table(
                    logs,
                    columns=[
                        ("Time",   "timestamp"),
                        ("Action", "action"),
                        ("Changed", "changed_fields"),
                        ("User",   "performed_by"),
                    ],
                    title="Transaction Audit Logs",
                    formatters={"timestamp": lambda x: fmt_datetime(x),
                                "changed_fields": lambda c: ", ".join(c) if isinstance(c, list) else str(c)[:50]},
                )
                pause()
 
        except BackSignal:
            pass
        except Exception as exc:
            print_error(str(exc))
            pause()
 
 
def _add_transaction(ctx: AppCtx) -> None:
    """Guided wizard to create a new transaction."""
    print_section("➕  Add Transaction")
 
    title       = ask_str("Title", required=True)
    tx_type     = ask_choice("Transaction type", TX_TYPES, required=True)
    amount      = ask_float("Amount", min_val=0.01, required=True)
    pay_method  = ask_choice("Payment method", PAY_METHODS, required=True, default="bank")
    tx_date     = ask_date("Transaction date", required=False, default=date.today())
    cat_id      = ask_int("Category ID", required=False)
    desc        = ask_str("Description", required=False)
    allow_od    = ask_confirm("Allow overdraft?", default=False)
 
    account_id             = None
    source_account_id      = None
    destination_account_id = None
 
    if tx_type in {"income", "expense", "debt_borrowed", "debt_repaid"}:
        account_id = ask_int("Account ID")
    elif tx_type in {"transfer", "investment_deposit", "investment_withdraw"}:
        source_account_id      = ask_int("Source account ID")
        destination_account_id = ask_int("Destination account ID")
 
    result = ctx.transactions.create_transaction(
        title=title,
        description=desc,
        amount=amount,
        transaction_type=tx_type,
        payment_method=pay_method,
        transaction_date=tx_date,
        category_id=cat_id,
        account_id=account_id,
        source_account_id=source_account_id,
        destination_account_id=destination_account_id,
        allow_overdraft=allow_od,
        is_global=0,
    )
 
    if result.get("transaction_id") or result.get("success"):
        tx_id = result.get("transaction_id") or result.get("transaction", {}).get("transaction_id")
        print_success(f"Transaction recorded! ID: [bold cyan]#{tx_id}[/bold cyan]")
    else:
        print_result(result)
    pause()
 
 
def _list_transactions(ctx: AppCtx) -> None:
    """Display a paginated list of recent transactions."""
    print_section("📋  Recent Transactions")
    trans_type = ask_choice("Filter by type", TX_TYPES, default=None, required=False)
    payment_method = ask_choice("Filter by payment method", PAY_METHODS, default=None, required=False)
    account_id = ask_int("Filter by account ID", required=False)
    category_id = ask_int("Filter by category ID", required=False)  
    limit = ask_int("How many to show", default=20, min_val=1, max_val=200)
 
    res  = ctx.transactions.list_transactions(transaction_type=trans_type, 
                                              payment_method=payment_method, 
                                              category_id=category_id,
                                              account_id=account_id, 
                                               limit=limit, include_deleted=False)
    txns = res.get("transactions", [])
 
    print_table(
        txns,
        columns=[
            ("ID",      "transaction_id"),
            ("Date",    "transaction_date"),
            ("Title",   "title"),
            ("Type",    "transaction_type"),
            ("Amount",  "amount"),
            ("Account ID", "account_id"),
            ("Account Name", "account_name"),
            ("Category", "category_name"),
            ("Source Acc", "source_account_id"),
            ("Source Acc Name", "source_account_name"),
            ("Dest Acc", "destination_account_id"),
            ("Dest Acc Name", "destination_account_name"),
            ("Payment", "payment_method"),
        ],
        title=f"Transactions (latest {len(txns)})",
        highlight_col="transaction_type",
        formatters={
            "amount":           lambda v: fmt_money(v),
            "transaction_date": fmt_date,
        },
    )
    pause()
 
 
def _update_transaction(ctx: AppCtx) -> None:
    """Prompt for field-level updates on an existing transaction."""
    tx_id = ask_int("Transaction ID to update")
 
    # Show current state first
    current = ctx.transactions.get_transaction(tx_id)
    print_detail_panel(
        current,
        title=f"Current  —  Transaction #{tx_id}",
        currency_keys={"amount"},
        date_keys={"transaction_date"},
        style="dim",
    )
 
    print_info("Leave blank to keep current value.")
    updates = {}
 
    title = ask_str("New title", required=False)
    if title:
        updates["title"] = title
 
    amount_raw = ask_float("New amount", required=False)
    if amount_raw is not None:
        updates["amount"] = amount_raw
 
    new_type = ask_choice("New transaction type", TX_TYPES, required=False)
    if new_type:
        updates["transaction_type"] = new_type
 
    pay = ask_choice("New payment method", PAY_METHODS, required=False)
    if pay:
        updates["payment_method"] = pay
 
    new_date = ask_date("New date", required=False)
    if new_date:
        updates["transaction_date"] = new_date
 
    desc = ask_str("New notes", required=False)
    if desc:
        updates["description"] = desc
 
    cat_id = ask_int("New category ID", required=False)
    if cat_id:
        updates["category_id"] = cat_id
 
    allow_od = ask_confirm("Allow overdraft?", default=False)
    updates["allow_overdraft"] = allow_od

    if current.get("transaction_type") in {"transfer", "investment_deposit", "investment_withdraw"}:
        source_acc = ask_int("New source account ID", required=False)
        dest_acc   = ask_int("New destination account ID", required=False)
        if source_acc:
            updates["source_account_id"] = source_acc
        if dest_acc:
            updates["destination_account_id"] = dest_acc

    elif current.get("transaction_type") in {"income", "expense", "debt_borrowed", "debt_repaid"}:
        acc_id = ask_int("New account ID", required=False)
        if acc_id:
            updates["account_id"] = acc_id
 
    if not updates:
        print_warning("No changes entered.")
        pause()
        return
 
    result = ctx.transactions.update_transaction(tx_id, **updates)
    print_result(result)
    pause()
 
 
# ════════════════════════════════════════════════════════
# ⑦ ANALYTICS
# ════════════════════════════════════════════════════════
 
def menu_analytics(ctx: AppCtx) -> None:
    ITEMS = [
        ("Financial Summary",      "Income, expenses & net cash flow"),
        ("Top Categories",         "Ranked spending/income by category"),
        ("Trends Over Time",       "Period-by-period breakdown"),
        ("Payment Method Split",   "How you pay for things"),
        ("Monthly Comparison",     "Side-by-side months for a year"),
        ("Daily Spending",         "Day-by-day expense drill-down"),
    ]
 
    while True:
        clear_screen()
        print_header("📈  Analytics & Reports", username=ctx.username, role=ctx.role)
 
        try:
            choice = prompt_choice(ITEMS, title="Analytics", show_back=True)
        except BackSignal:
            return
 
        try:
            global_view = ctx.is_admin() and ask_confirm(
                "Show global data? (admin only)", default=False
            ) if ctx.is_admin() else False
 
            if choice == 1:
                print_section("💰  Financial Summary")
                start = ask_date("Start date", required=False)
                end   = ask_date("End date",   required=False)
 
                res = ctx.analytics.summary(
                    start_date=start, end_date=end, global_view=global_view
                )
                _print_analytics_summary(res)
                pause()
 
            elif choice == 2:
                print_section("🏆  Top Categories")
                tx_type = ask_choice("Transaction type", TX_TYPES, default="expense")
                limit   = ask_int("How many categories", default=100, min_val=1)
                start   = ask_date("Start date", required=False)
                end     = ask_date("End date",   required=False)
 
                rows = ctx.analytics.top_categories(
                    transaction_type=tx_type, limit=limit,
                    start_date=start, end_date=end, global_view=global_view,
                )
                print_table(
                    rows,
                    columns=[
                        ("Category",   "category_name"),
                        ("Total",      "total"),
                        ("# Txns",     "count"),
                        ("%",          "percentage"),
                    ],
                    title=f"Top {len(rows)} Categories — {tx_type}",
                    formatters={
                        "total":      lambda v: fmt_money(v),
                        "percentage": lambda v: f"{v:.1f}%",
                    },
                )
                pause()
 
            elif choice == 3:
                print_section("📅  Trends")
                period = ask_choice("Period", ["daily", "weekly", "monthly", "yearly"],
                                    default="monthly")
                start  = ask_date("Start date", required=False)
                end    = ask_date("End date",   required=False)
 
                rows = ctx.analytics.trends(
                    period=period, start_date=start,
                    end_date=end, global_view=global_view,
                )
                print_table(
                    rows,
                    columns=[
                        ("Period",   "period"),
                        ("Income",   "total_income"),
                        ("Expenses", "total_expenses"),
                        ("Net",      "net"),
                    ],
                    title=f"{period.title()} Trends",
                    formatters={
                        "total_income":   lambda v: fmt_money(v),
                        "total_expenses": lambda v: fmt_money(v),
                        "net":            lambda v: fmt_money(v),
                    },
                )
                pause()
 
            elif choice == 4:
                print_section("💳  Payment Methods")
                start = ask_date("Start date", required=False)
                end   = ask_date("End date",   required=False)
 
                rows = ctx.analytics.payment_method_breakdown(
                    start_date=start, end_date=end, global_view=global_view,
                )
                print_table(
                    rows,
                    columns=[
                        ("Payment Method", "payment_method"),
                        ("Total",          "total"),
                        ("# Txns",         "count"),
                        ("%",              "percentage"),
                    ],
                    title="Payment Method Breakdown",
                    formatters={
                        "total":      lambda v: fmt_money(v),
                        "percentage": lambda v: f"{v:.1f}%",
                    },
                )
                pause()
 
            elif choice == 5:
                print_section("📆  Monthly Comparison")
                year = ask_int("Year", default=date.today().year)
 
                rows = ctx.analytics.monthly_comparison(
                    year=year, global_view=global_view
                )
                print_table(
                    rows,
                    columns=[
                        ("Month",    "month_label"),
                        ("Income",   "total_income"),
                        ("Expenses", "total_expenses"),
                        ("Debt In",  "total_debt_in"),
                        ("Debt Out", "total_debt_out"),
                        ("Net",      "net"),
                    ],
                    title=f"Monthly Comparison — {year}",
                    formatters={
                        "total_income":   lambda v: fmt_money(v),
                        "total_expenses": lambda v: fmt_money(v),
                        "total_debt_in":  lambda v: fmt_money(v),
                        "total_debt_out": lambda v: fmt_money(v),
                        "net":            lambda v: fmt_money(v),
                    },
                )
                pause()
 
            elif choice == 6:
                print_section("📆  Daily Spending")
                start = ask_date("Start date", required=True)
                end   = ask_date("End date",   required=True)
 
                rows = ctx.analytics.daily_spending(
                    start_date=start, end_date=end, global_view=global_view
                )
                print_table(
                    rows,
                    columns=[
                        ("Date",   "date"),
                        ("Total",  "total"),
                        ("# Txns", "count"),
                    ],
                    title="Daily Spending",
                    formatters={
                        "total": lambda v: fmt_money(v),
                        "date":  fmt_date,
                    },
                )
                pause()
 
        except BackSignal:
            pass
        except Exception as exc:
            print_error(str(exc))
            pause()
 
 
def _print_analytics_summary(res: Dict[str, Any]) -> None:
    """Pretty-print a financial summary dict."""
    from rich.columns import Columns
    income   = res.get("total_income",   0.0)
    expenses = res.get("total_expenses", 0.0)
    net      = res.get("net_cash_flow",  income - expenses)
    rate     = res.get("savings_rate",   0.0)
    tx_count = res.get("transaction_count", res.get("total_transactions", "—"))
 
    console.print()
    console.print(Columns([
        Panel(f"[bold green]{fmt_money(income)}[/bold green]",
              title="💚 Total Income",     border_style="green"),
        Panel(f"[bold red]{fmt_money(expenses)}[/bold red]",
              title="❤️  Total Expenses",  border_style="red"),
        Panel(f"[bold {'green' if net >= 0 else 'red'}]{fmt_money(net)}[/bold {'green' if net >= 0 else 'red'}]",
              title="💙 Net Cash Flow",   border_style="cyan"),
        Panel(f"[bold yellow]{rate:.1f}%[/bold yellow]",
              title="💛 Savings Rate",    border_style="yellow"),
    ], expand=True))
 
 
# ════════════════════════════════════════════════════════
# ⑧ GOALS
# ════════════════════════════════════════════════════════
 
GOAL_TYPES    = ["saving", "spending", "budget_cap"]
GOAL_STATUSES = ["active", "completed", "failed", "paused"]
 
 
def menu_goals(ctx: AppCtx) -> None:
    ITEMS = [
        ("List Goals",          "See all goals with live progress"),
        ("Create Goal",         "Set a new financial goal"),
        ("Goal Progress",       "Check progress for a specific goal"),
        ("All Goals Progress",  "Progress snapshot for every active goal"),
        ("Update Goal",         "Edit goal fields"),
        ("Mark Completed",      "Finalise a goal as achieved"),
        ("Pause / Resume",      "Temporarily pause a goal"),
        ("Delete Goal",         "Soft-delete a goal"),
        ("Budget Cap Check",    "See if any spend caps are exceeded"),
        ("Goals Summary",       "Dashboard-style summary"),
        ("Audit Logs",          "Goal change history"),
    ]
 
    while True:
        clear_screen()
        print_header("🎯  Goals", username=ctx.username, role=ctx.role)
 
        try:
            choice = prompt_choice(ITEMS, title="Goals", show_back=True)
        except BackSignal:
            return
 
        try:
            if choice == 1:
                res   = ctx.goals.list_goals(with_progress=True)
                goals = res.get("goals", [])
                print_table(
                    goals,
                    columns=[
                        ("ID",       "goal_id"),
                        ("Name",     "name"),
                        ("Type",     "goal_type"),
                        ("Target",   "target_amount"),
                        ("Progress", "progress_pct"),
                        ("Status",   "status"),
                        ("Ends",     "end_date"),
                    ],
                    title=f"Your Goals ({len(goals)})",
                    formatters={
                        "target_amount": lambda v: fmt_money(v),
                        "progress_pct":  lambda v: f"{float(v or 0):.1f}%",
                        "end_date":      fmt_date,
                        "status":        fmt_status,
                    },
                )
                pause()
 
            elif choice == 2:
                _create_goal(ctx)
 
            elif choice == 3:
                goal_id  = ask_int("Goal ID")
                progress = ctx.goals.get_progress(goal_id)
                print_detail_panel(
                    progress,
                    title=f"Goal #{goal_id} Progress",
                    currency_keys={"target_amount", "current_amount"},
                )
                pause()
 
            elif choice == 4:
                all_prog = ctx.goals.get_all_progress()
                print_table(
                    all_prog,
                    columns=[
                        ("ID",       "goal_id"),
                        ("Name",     "name"),
                        ("Progress", "progress_pct"),
                        ("Current",  "current_amount"),
                        ("Target",   "target_amount"),
                        ("Days Left","days_left"),
                        ("On Track", "on_track"),
                    ],
                    title="All Active Goals Progress",
                    formatters={
                        "current_amount": lambda v: fmt_money(v),
                        "target_amount":  lambda v: fmt_money(v),
                        "progress_pct":   lambda v: f"{float(v or 0):.1f}%",
                        "on_track":       lambda v: "✅" if v else "⚠️",
                    },
                )
                pause()
 
            elif choice == 5:
                goal_id = ask_int("Goal ID")
                print_info("Leave blank to skip.")
                updates = {}
                name = ask_str("New name", required=False)
                if name:
                    updates["name"] = name
                target = ask_float("New target amount", required=False)
                if target:
                    updates["target_amount"] = target
                end = ask_date("New end date", required=False)
                if end:
                    updates["end_date"] = end
                desc = ask_str("New description", required=False)
                if desc:
                    updates["description"] = desc
                if updates:
                    result = ctx.goals.update_goal(goal_id, **updates)
                    print_result(result)
                else:
                    print_warning("No changes entered.")
                pause()
 
            elif choice == 6:
                goal_id = ask_int("Goal ID to mark complete")
                if ask_confirm(f"Mark goal #{goal_id} as completed?"):
                    result = ctx.goals.update_goal(goal_id, status="completed")
                    print_result(result)
                pause()
 
            elif choice == 7:
                goal_id = ask_int("Goal ID")
                goal    = ctx.goals.get_goal(goal_id)
                current_status = goal.get("status", "active")
                if current_status == "paused":
                    action = "active"
                    label  = "Resume"
                else:
                    action = "paused"
                    label  = "Pause"
                if ask_confirm(f"{label} goal #{goal_id}?"):
                    result = ctx.goals.update_goal(goal_id, status=action)
                    print_result(result)
                pause()
 
            elif choice == 8:
                goal_id = ask_int("Goal ID")
                hard    = ask_confirm("Hard delete?", default=False)
                result  = ctx.goals.delete_goal(goal_id, soft=not hard)
                print_result(result)
                pause()
 
            elif choice == 9:
                cat_id = ask_int("Category ID (blank for account-based)", required=False)
                acc_id = None
                if not cat_id:
                    acc_id = ask_int("Account ID", required=False)
                result = ctx.goals.check_budget_cap(
                    category_id=cat_id, account_id=acc_id
                )
                caps = result.get("caps", [])
                if result.get("any_exceeded"):
                    print_warning("⚠️  Some budget caps are EXCEEDED:")
                else:
                    print_success("All budget caps are within limits ✔")
                print_table(
                    caps,
                    columns=[
                        ("Goal",     "name"),
                        ("Target",   "target_amount"),
                        ("Current",  "current_amount"),
                        ("Over",     "overspend"),
                        ("Exceeded", "exceeded"),
                    ],
                    formatters={
                        "target_amount":  lambda v: fmt_money(v),
                        "current_amount": lambda v: fmt_money(v),
                        "overspend":      lambda v: fmt_money(v),
                        "exceeded":       lambda v: "[red]YES[/red]" if v else "[green]NO[/green]",
                    },
                )
                pause()
 
            elif choice == 10:
                summary = ctx.goals.get_summary()
                print_detail_panel(
                    {
                        "Total Goals":    summary.get("total_goals"),
                        "By Status":      str(summary.get("by_status", {})),
                        "By Type":        str(summary.get("by_type", {})),
                        "Caps Exceeded":  len(summary.get("caps_exceeded", [])),
                    },
                    title="Goals Summary",
                )
                pause()
 
            elif choice == 11:
                goal_id = ask_int("Goal ID (blank for all)", required=False)
                logs    = ctx.goals.view_audit_logs(goal_id=goal_id)
                print_table(
                    logs,
                    columns=[
                        ("Time",   "timestamp"),
                        ("Action", "action"),
                        ("Changed", "changed_fields"),
                    ],
                    title="Goal Audit Logs",
                    formatters={"timestamp": lambda x: fmt_datetime(x)},
                )
                pause()
 
        except BackSignal:
            pass
        except Exception as exc:
            print_error(str(exc))
            pause()
 
 
def _create_goal(ctx: AppCtx) -> None:
    print_section("➕  Create Goal")
    name        = ask_str("Goal name")
    goal_type   = ask_choice("Goal type", GOAL_TYPES)
    target      = ask_float("Target amount", min_val=0.01)
    start_date  = ask_date("Start date", required=True, default=date.today())
    end_date    = ask_date("End date",   required=True)
    desc        = ask_str("Description", required=False)
    status      = ask_choice("Status", GOAL_STATUSES, default="active")
    is_global   = ask_confirm("Make global?", default=False)
 
    cat_id = None
    acc_id = None
    if goal_type in ("spending", "budget_cap"):
        cat_id = ask_int("Category ID", required=False)
        if not cat_id:
            acc_id = ask_int("Account ID", required=False)
    elif goal_type == "saving":
        acc_id = ask_int("Account ID")
 
    data = dict(
        name=name, goal_type=goal_type, target_amount=target,
        start_date=start_date, end_date=end_date,
        description=desc, status=status, is_global=int(is_global),
    )
    if cat_id:
        data["category_id"] = cat_id
    if acc_id:
        data["account_id"]  = acc_id
 
    result = ctx.goals.create_goal(**{k: v for k, v in data.items() if v is not None})
    if result.get("goal_id") or result.get("success"):
        gid = result.get("goal_id") or result.get("goal", {}).get("goal_id", "?")
        print_success(f"Goal created! ID: [bold cyan]#{gid}[/bold cyan]")
    else:
        print_result(result)
    pause()
 
 
# ════════════════════════════════════════════════════════
# ⑨ RECURRING TRANSACTIONS
# ════════════════════════════════════════════════════════
 
FREQUENCIES = ["daily", "weekly", "monthly", "yearly"]
 
 
def menu_recurring(ctx: AppCtx) -> None:
    ITEMS = [
        ("List Recurring",      "All scheduled transactions"),
        ("Create Recurring",    "Set up a new recurring rule"),
        ("View Recurring",      "Details of one rule"),
        ("Update Recurring",    "Edit a rule"),
        ("Toggle Active",       "Enable or disable a rule"),
        ("Delete Recurring",    "Remove a rule"),
        ("Upcoming Due",        "Bills due in the next N days"),
        ("Process Due Now",     "Manually trigger overdue transactions"),
    ]
 
    while True:
        clear_screen()
        print_header("🔁  Recurring Transactions", username=ctx.username, role=ctx.role)
 
        try:
            choice = prompt_choice(ITEMS, title="Recurring", show_back=True)
        except BackSignal:
            return
 
        try:
            if choice == 1:
                res  = ctx.recurring.list()
                print_table(
                    res,
                    columns=[
                        ("ID",        "recurring_id"),
                        ("Name",      "name"),
                        ("Type",      "transaction_type"),
                        ("Freq",      "frequency"),
                        ("Amount",    "amount"),
                        ("Next Due",  "next_due"),
                        ("Maximum missed", "max_missed_runs"),
                        ("Last Ran Status", "last_run_status"),
                        ("Active",    "is_active"),
                    ],
                    title="Recurring Rules",
                    formatters={
                        "amount":   lambda v: fmt_money(v),
                        "next_due": fmt_date,
                        "is_active": lambda v: "[green]✔[/green]" if v else "[red]✘[/red]",
                    },
                )
                pause()
 
            elif choice == 2:
                _create_recurring(ctx)
 
            elif choice == 3:
                rid  = ask_int("Recurring ID")
                rec  = ctx.recurring.get_recurring(rid)
                print_detail_panel(
                    rec,
                    title=f"Recurring #{rid}",
                    currency_keys={"amount"},
                    date_keys={"next_due", "created_at"},
                )
                pause()
 
            elif choice == 4:
                _update_recurring(ctx)
 
            elif choice == 5:
                rid = ask_int("Recurring ID")
                rec = ctx.recurring.get_recurring(rid)
                new_state = not rec.get("is_active", True)
                result    = ctx.recurring.update_recurring(rid, is_active=int(new_state))
                label     = "Activated" if new_state else "Deactivated"
                print_success(f"Rule #{rid} {label}.")
                pause()
 
            elif choice == 6:
                rid  = ask_int("Recurring ID")
                soft = ask_confirm("Soft delete?", default=True)
                result = ctx.recurring.delete_recurring(rid, soft=soft)
                print_result(result)
                pause()
 
            elif choice == 7:
                days = ask_int("Look-ahead days", default=7, min_val=1)
                rows = ctx.scheduler.get_upcoming_due(days_ahead=days)
                print_table(
                    rows,
                    columns=[
                        ("Name",    "name"),
                        ("Type",    "transaction_type"),
                        ("Amount",  "amount"),
                        ("Due",     "next_due"),
                        ("Freq",    "frequency"),
                    ],
                    title=f"Upcoming in {days} day(s)",
                    formatters={
                        "amount":   lambda v: fmt_money(v),
                        "next_due": fmt_date,
                    },
                )
                pause()
 
            elif choice == 8:
                if ask_confirm("Process all overdue recurring transactions now?"):
                    result = ctx.scheduler.run_all_due_recurring()
                    processed = result.get("processed", 0)
                    print_success(f"Processed {processed} transaction(s).")
                    if result.get("errors"):
                        for err in result["errors"]:
                            print_warning(str(err))
                pause()
 
        except BackSignal:
            pass
        except Exception as exc:
            print_error(str(exc))
            pause()
 
 
def _create_recurring(ctx: AppCtx) -> None:
    print_section("➕  Create Recurring Transaction")
    name       = ask_str("name", required=True)
    desc       = ask_str("Description", required=False)
    tx_type    = ask_choice("Transaction type", TX_TYPES)
    freq       = ask_choice("Frequency", FREQUENCIES)
    interval   = ask_int("Interval (e.g. every N periods)", default=1, min_val=1)
    amount     = ask_float("Amount", min_val=0.01)
    cat_id     = ask_int("Category ID", required=False)
    next_due   = ask_date("Next due date", required=True, default=date.today())
    is_global  = ask_confirm("Make global?", default=False)
 
    account_id             = None
    source_account_id      = None
    destination_account_id = None
 
    if tx_type in {"income", "expense", "debt_borrowed", "debt_repaid"}:
        account_id = ask_int("Account ID")
    elif tx_type in {"transfer", "investment_deposit", "investment_withdraw"}:
        source_account_id      = ask_int("Source account ID")
        destination_account_id = ask_int("Destination account ID")
 
    result = ctx.recurring.create_recurring(
        name=name,
        description=desc,
        transaction_type=tx_type,
        frequency=freq,
        interval_value=interval,
        amount=amount,
        category_id=cat_id,
        next_due=datetime.combine(next_due or date.today(), datetime.min.time()),
        account_id=account_id,
        source_account_id=source_account_id,
        destination_account_id=destination_account_id,
        is_global=int(is_global),
    )
    print_result(result)
    pause()

def _update_recurring(ctx: AppCtx) -> None:
    """Prompt for field-level updates on an existing recurring transaction."""
    rid = ask_int("Recurring transaction ID to update")
 
    # Show current state first
    current = ctx.recurring.get_recurring(rid)
    print_detail_panel(
        current,
        title=f"Current  —  Recurring Transaction #{rid}",
        currency_keys={"amount"},
        date_keys={"next_due"},
        style="dim",
    )
    current_type = current.get("transaction_type")
    print_info("Leave blank to keep current value.")
    updates = {}

    title = ask_str("New title", required=False)
    if title:
        updates["title"] = title

    amount_raw = ask_float("New amount", required=False)
    if amount_raw is not None:
        updates["amount"] = amount_raw
    
    new_type = ask_choice("New recurring transaction type", TX_TYPES, required=False)
    if new_type:
        updates["transaction_type"] = new_type

    freq = ask_choice("New frequency", FREQUENCIES, required=False)
    if freq:
        updates["frequency"] = freq

    interv = ask_int("New interval (e.g. every N periods)", default=None, min_val=1)
    if interv:
        updates["interval_value"] = interv

    pay = ask_choice("New payment method", PAY_METHODS, required=False)
    if pay:
        updates["payment_method"] = pay

    new_date = ask_date("New next due date", required=False)
    if new_date:
        updates["next_due"] = new_date

    desc = ask_str("New notes", required=False)
    if desc:
        updates["description"] = desc

    cat_id = ask_int("New category ID", required=False)
    if cat_id:
        updates["category_id"] = cat_id

    if current_type in {"income", "expense", "debt_borrowed", "debt_repaid"}:
        account_id = ask_int("New account ID", required=False)
        if account_id:
            updates["account_id"] = account_id

    elif current_type in {"transfer", "investment_deposit", "investment_withdraw"}: 
        source_account_id      = ask_int("New source account ID", required=False)
        destination_account_id = ask_int("New destination account ID", required=False)
        if source_account_id:
            updates["source_account_id"] = source_account_id
        if destination_account_id:
            updates["destination_account_id"] = destination_account_id

    allow_od = ask_confirm("Allow overdraft?", default=False)
    updates["allow_overdraft"] = allow_od

    if not updates:
        print_warning("No changes entered.")
        pause()
        return

    result = ctx.recurring.update(rid, **updates)
    print_result(result)
    pause()

 
# ════════════════════════════════════════════════════════
# ⑩ SEARCH
# ════════════════════════════════════════════════════════
 
def menu_search(ctx: AppCtx) -> None:
    ITEMS = [
        ("Search Transactions", "Full-text + filter search"),
        ("Search Categories",   "Find categories by name"),
        ("Search Accounts",     "Find accounts by type or balance"),
    ]
 
    while True:
        clear_screen()
        print_header("🔍  Search", username=ctx.username, role=ctx.role)
 
        try:
            choice = prompt_choice(ITEMS, title="Search", show_back=True)
        except BackSignal:
            return
 
        try:
            if choice == 1:
                print_section("🔍  Transaction Search")
                text    = ask_str("Search text (title / notes)", required=False)
                pay_methods = ask_choice("Payment method", PAY_METHODS, required=False)
                start   = ask_date("From date",  required=False)
                end     = ask_date("To date",    required=False)
                min_amt = ask_float("Min amount", required=False)
                max_amt = ask_float("Max amount", required=False)
                date_preset = ask_choice("Date preset", ValidationPatterns().DATE_PRESETS, required=False, default=None)
                tx_type = ask_choice("Transaction type", TX_TYPES, required=False)
                cat     = ask_int("Category ID", required=False)
                limit   = ask_int("Max results", default=50, min_val=1)
 
                req = TransactionSearchRequest(
                    text=TextSearchFilter(search_text=text) if text else TextSearchFilter(),
                    date=DateFilter(start_date=start, end_date=end, date_preset=date_preset),
                    category=CategoryFilter(category_id=cat) if cat else CategoryFilter(),
                    amount=AmountFilter(min_amount=min_amt, max_amount=max_amt),
                    tx_type=TransactionTypeFilter(
                        transaction_types=[tx_type] if tx_type else None,
                        payment_methods=pay_methods,
                    ),
                    pagination=Pagination(page_size=limit),
                )
                result = ctx.search_svc.search_transactions(req)
                rows   = result.get("results", [])
                print_table(
                    rows,
                    columns=[
                        ("ID",     "transaction_id"),
                        ("Date",   "transaction_date"),
                        ("Title",  "title"),
                        ("Type",   "transaction_type"),
                        ("Amount", "amount"),
                    ],
                    title=f"Results: {result.get('count', len(rows))}",
                    highlight_col="transaction_type",
                    formatters={
                        "amount":           lambda v: fmt_money(v),
                        "transaction_date": fmt_date,
                    },
                )
                pause()
 
            elif choice == 2:
                text   = ask_str("Category name to search")
                category = ask_int("Category ID to filter by", required=False)
                include_children = ask_confirm("Include subcategories?", default=True)
                from features.search import CategorySearchRequest
                req    = CategorySearchRequest(text=TextSearchFilter(search_text=text), 
                                               category= CategoryFilter(category_ids=[category], 
                                                                        include_children=include_children) if category else CategoryFilter())
                result = ctx.search_svc.search_categories(req)
                rows   = result.get("results", [])
                print_table(
                    rows,
                    columns=[
                        ("ID",     "category_id"),
                        ("Name",   "name"),
                        ("Parent", "parent_id"),
                    ],
                    title="Matching Categories",
                )
                if include_children:
                    print_info(f"Included subcategories of category ID {category}.")
                    _print_tree(rows)
                pause()
 
            elif choice == 3:
                from features.search import AccountSearchRequest
                acc_id   = ask_int("Account ID to search for", required=False)
                acc_type = ask_choice("Account type", ACCOUNT_TYPES, required=False)
                req      = AccountSearchRequest(AccountFilter(account_ids=[acc_id] if acc_id else None,
                                                               account_types=acc_type))
                result   = ctx.search_svc.search_accounts(req)
                rows     = result.get("results", [])
                print_table(
                    rows,
                    columns=[
                        ("ID",      "account_id"),
                        ("Name",    "name"),
                        ("Type",    "account_type"),
                        ("Balance", "balance"),
                    ],
                    title="Matching Accounts",
                    formatters={"balance": lambda v: fmt_money(v)},
                )
                pause()
 
        except BackSignal:
            pass
        except (ImportError, AttributeError) as exc:
            # SearchService filter classes may have different names
            print_error(f"Search module error: {exc}")
            pause()
        except Exception as exc:
            print_error(str(exc))
            pause()

# ════════════════════════════════════════════════════════════════════════════
# ⑨  SCHEDULER
# ════════════════════════════════════════════════════════════════════════════

def menu_scheduler(ctx: AppCtx) -> None:
    from datetime import timedelta

    ITEMS = [
        # ── Execution ─────────────────────────────────────
        ("▶️   Run All Due Now",        "Execute every overdue recurring rule"),
        ("⏰  Run Scheduler Job",       "Full cron-style run with report"),
        # ── Monitoring ────────────────────────────────────
        ("📊  Scheduler Status",        "Active / paused / overdue counts"),
        ("📅  Upcoming Due",            "Rules due in the next N days"),
        ("🔍  Preview Next Run",        "See what a rule will create next"),
        # ── Control ───────────────────────────────────────
        ("⏸️   Pause Rule",              "Suspend a rule until a future date"),
        ("▶️   Resume Rule",             "Un-pause a suspended rule"),
        ("⏭️   Skip Next Occurrence",    "Skip one upcoming run only"),
        ("💰  One-Time Amount Override","Override the amount for next run only"),
        ("🔴  Deactivate Rule",         "Disable without deleting"),
        ("🟢  Activate Rule",           "Re-enable a deactivated rule"),
        # ── History ───────────────────────────────────────
        ("📜  Full Execution History",  "All recurring run logs"),
        ("📜  History for One Rule",    "Logs for a specific recurring ID"),
        ("📜  History by Status",       "Filter logs: generated / skipped / failed"),
    ]

    while True:
        clear_screen()
        print_header("🗓️   Scheduler", username=ctx.username, role=ctx.role)

        try:
            choice = prompt_choice(ITEMS, title="Scheduler", show_back=True)
        except BackSignal:
            return

        try:
            # ── 1. Run all due ───────────────────────────
            if choice == 1:
                if ask_confirm("Run all due recurring transactions now?", default=False):
                    result = ctx.scheduler.run_all_due_recurring()
                    if result["success"]:
                        print_success(
                            f"Created [bold cyan]{result['created_count']}[/bold cyan] "
                            f"transaction(s).  IDs: {result['transaction_ids'] or '—'}"
                        )
                    else:
                        print_error(result.get("message", "Run failed."))
                pause()

            # ── 2. Run scheduler job (cron-style) ────────
            elif choice == 2:
                if ask_confirm("Execute full scheduler job?", default=False):
                    report = ctx.scheduler.run_scheduler_job()
                    status_colour = "green" if report["job_status"] == "completed" else "red"
                    print_detail_panel(
                        {
                            "Job Status":   report["job_status"],
                            "Start Time":   report["start_time"],
                            "End Time":     report["end_time"],
                            "Created":      report["result"].get("created_count", 0),
                            "Tx IDs":       str(report["result"].get("transaction_ids", [])),
                            "Message":      report["result"].get("message", ""),
                        },
                        title="Scheduler Job Report",
                        style=status_colour,
                    )
                pause()

            # ── 3. Scheduler status ──────────────────────
            elif choice == 3:
                s = ctx.scheduler.get_scheduler_status()
                from rich.columns import Columns
                from rich.panel import Panel
                console.print()
                console.print(Columns([
                    Panel(f"[bold green]{s['total_active']}[/bold green]",
                          title="✅ Active",  border_style="green"),
                    Panel(f"[bold yellow]{s['total_paused']}[/bold yellow]",
                          title="⏸️  Paused",  border_style="yellow"),
                    Panel(f"[bold red]{s['total_overdue']}[/bold red]",
                          title="🔴 Overdue", border_style="red"),
                ], expand=True))
                console.print(f"  [dim]As of {s['timestamp']}[/dim]")
                pause()

            # ── 4. Upcoming due ──────────────────────────
            elif choice == 4:
                days = ask_int("Look-ahead days", default=7, min_val=1)
                rows = ctx.scheduler.get_upcoming_due(days_ahead=days)
                print_table(
                    rows,
                    columns=[
                        ("ID",       "recurring_id"),
                        ("Name",     "name"),
                        ("Type",     "transaction_type"),
                        ("Amount",   "amount"),
                        ("Next Due", "next_due"),
                        ("Freq",     "frequency"),
                    ],
                    title=f"Due in next {days} day(s)  —  {len(rows)} rule(s)",
                    formatters={
                        "amount":   lambda v: fmt_money(v),
                        "next_due": fmt_date,
                    },
                    empty_message=f"Nothing due in the next {days} days 🎉",
                )
                pause()

            # ── 5. Preview next run ──────────────────────
            elif choice == 5:
                rid    = ask_int("Recurring rule ID")
                result = ctx.scheduler.preview_next_run(rid)
                print_detail_panel(
                    result,
                    title=f"Preview — Rule #{rid}",
                    currency_keys={"amount", "override_amount"},
                    date_keys={"next_due", "last_run"},
                    style="cyan",
                )
                pause()

            # ── 6. Pause ─────────────────────────────────
            elif choice == 6:
                rid        = ask_int("Recurring rule ID")
                pause_days = ask_int("Pause for how many days?", min_val=1)
                pause_until = datetime.now() + timedelta(days=pause_days)

                result = ctx.scheduler.pause_recurring(rid, pause_until)
                print_result(result)
                print_info(f"Rule #{rid} paused until [bold]{fmt_date(pause_until)}[/bold].")
                pause()

            # ── 7. Resume ────────────────────────────────
            elif choice == 7:
                rid    = ask_int("Recurring rule ID")
                result = ctx.scheduler.resume_recurring(rid)
                print_result(result)
                pause()

            # ── 8. Skip next occurrence ──────────────────
            elif choice == 8:
                rid = ask_int("Recurring rule ID")
                if ask_confirm(f"Skip the next run of rule #{rid}?", default=False):
                    result = ctx.scheduler.skip_next_occurrence(rid)
                    print_result(result)
                pause()

            # ── 9. One-time amount override ───────────────
            elif choice == 9:
                rid      = ask_int("Recurring rule ID")
                override = ask_float("Override amount for next run only", min_val=0.01)
                result   = ctx.scheduler.set_one_time_override(rid, override)
                print_result(result)
                print_info(f"Next run of rule #{rid} will use [bold cyan]{fmt_money(override)}[/bold cyan].")
                pause()

            # ── 10. Deactivate ────────────────────────────
            elif choice == 10:
                rid = ask_int("Recurring rule ID")
                if ask_confirm(f"Deactivate rule #{rid}?", default=False):
                    result = ctx.scheduler.deactivate_recurring(rid)
                    print_result(result)
                pause()

            # ── 11. Activate ──────────────────────────────
            elif choice == 11:
                rid    = ask_int("Recurring rule ID")
                result = ctx.scheduler.activate_recurring(rid)
                print_result(result)
                pause()

            # ── 12. Full execution history ────────────────
            elif choice == 12:
                limit = ask_int("Max records", default=50, min_val=1)
                logs  = ctx.scheduler.get_recurring_history(limit=limit)
                _print_scheduler_history(logs)
                pause()

            # ── 13. History for one rule ──────────────────
            elif choice == 13:
                rid   = ask_int("Recurring rule ID")
                limit = ask_int("Max records", default=20, min_val=1)
                logs  = ctx.scheduler.get_recurring_history(
                    recurring_id=rid, limit=limit
                )
                _print_scheduler_history(logs, title=f"History — Rule #{rid}")
                pause()

            # ── 14. History by status ─────────────────────
            elif choice == 14:
                status = ask_choice(
                    "Status filter",
                    ["generated", "skipped", "failed"],
                )
                limit = ask_int("Max records", default=50, min_val=1)
                logs  = ctx.scheduler.get_recurring_history(
                    status=status, limit=limit
                )
                _print_scheduler_history(logs, title=f"History — {status.title()}")
                pause()

        except BackSignal:
            pass
        except Exception as exc:
            print_error(str(exc))
            pause()


def _print_scheduler_history(
    logs: list,
    title: str = "Execution History",
) -> None:
    """Render recurring execution history as a Rich table."""
    STATUS_COLOUR = {
        "generated": "[bold green]generated[/bold green]",
        "skipped":   "[bold yellow]skipped[/bold yellow]",
        "failed":    "[bold red]failed[/bold red]",
    }
    print_table(
        logs,
        columns=[
            ("Run Date",      "run_date"),
            ("Rule ID",       "recurring_id"),
            ("Amount Used",   "amount_used"),
            ("Status",        "status"),
            ("Override Used", "override_used"),
            ("Tx ID",         "posted_transaction_id"),
            ("Message",       "message"),
        ],
        title=f"{title}  ({len(logs)} record(s))",
        formatters={
            "run_date":    fmt_date,
            "amount_used": lambda v: fmt_money(v) if v is not None else "—",
            "status":      lambda v: STATUS_COLOUR.get(str(v).lower(), str(v)),
            "override_used": lambda v: "[cyan]Yes[/cyan]" if v else "—",
        },
        empty_message="No execution history found.",
    )

# ════════════════════════════════════════════════════════════════════════════
# ⑩  INSIGHTS
# ════════════════════════════════════════════════════════════════════════════

# Severity badge map
_SEV_STYLE = {
    "critical": "[bold red]🚨 CRITICAL[/bold red]",
    "warning":  "[bold yellow]⚠️  WARNING[/bold yellow]",
    "info":     "[bold cyan]ℹ️  INFO[/bold cyan]",
}

# InsightCategory display labels
_CAT_LABELS = {
    "spending":    "💸 Spending",
    "income":      "💚 Income",
    "savings":     "🏦 Savings",
    "category":    "🗂  Category",
    "transaction": "🧾 Transaction",
    "debt":        "📋 Debt",
    "payment":     "💳 Payment",
}


def menu_insights(ctx: AppCtx) -> None:
    ITEMS = [
        ("All Insights",            "Full report — every category, sorted by severity"),
        ("Spending Insights",       "Spikes, daily averages & streak detection"),
        ("Income Insights",         "Income drops & missing income warnings"),
        ("Savings Insights",        "Savings rate health & net position"),
        ("Category Insights",       "Per-category spikes, budget caps & top-shift"),
        ("Transaction Insights",    "Large single-transaction alerts"),
        ("Debt Insights",           "Borrowing ratio & debt trend"),
        ("Payment Method Insights", "Dominant payment method shift detection"),
        ("Insights Summary",        "Badge-style count: critical / warning / info"),
        ("Filter by Severity",      "Show only critical, warning or info insights"),
    ]

    while True:
        clear_screen()
        print_header("💡  Smart Insights", username=ctx.username, role=ctx.role)

        try:
            choice = prompt_choice(ITEMS, title="Insights", show_back=True)
        except BackSignal:
            return

        try:
            # ── Shared date range prompt ─────────────────────────────
            # Defaulting to current-month vs prior-month (engine default).
            # Ask the user if they want a custom range.
            curr_start = curr_end = prev_start = prev_end = None

            if ask_confirm("Use custom date range? (default: this month vs last month)",
                           default=False):
                print_section("Current Period")
                curr_start = ask_date("Current start date", required=True)
                curr_end   = ask_date("Current end date",   required=True)
                print_section("Baseline / Prior Period")
                prev_start = ask_date("Prior start date",   required=True)
                prev_end   = ask_date("Prior end date",     required=True)

            # ── 1. All Insights ──────────────────────────────────────
            if choice == 1:
                insights = ctx.insights.get_all_insights(
                    curr_start=curr_start, curr_end=curr_end,
                    prev_start=prev_start, prev_end=prev_end,
                    as_dicts=False,
                )
                _render_insights(insights)
                pause()

            # ── 2. Spending ──────────────────────────────────────────
            elif choice == 2:
                insights = ctx.insights.get_spending_insights(
                    curr_start=curr_start, curr_end=curr_end,
                    prev_start=prev_start, prev_end=prev_end,
                )
                _render_insights(insights, section="💸  Spending Insights")
                pause()

            # ── 3. Income ────────────────────────────────────────────
            elif choice == 3:
                insights = ctx.insights.get_income_insights(
                    curr_start=curr_start, curr_end=curr_end,
                    prev_start=prev_start, prev_end=prev_end,
                )
                _render_insights(insights, section="💚  Income Insights")
                pause()

            # ── 4. Savings ───────────────────────────────────────────
            elif choice == 4:
                insights = ctx.insights.get_savings_insights(
                    curr_start=curr_start, curr_end=curr_end,
                )
                _render_insights(insights, section="🏦  Savings Insights")
                pause()

            # ── 5. Category ──────────────────────────────────────────
            elif choice == 5:
                insights = ctx.insights.get_category_insights(
                    curr_start=curr_start, curr_end=curr_end,
                    prev_start=prev_start, prev_end=prev_end,
                )
                _render_insights(insights, section="🗂   Category Insights")
                pause()

            # ── 6. Transaction ───────────────────────────────────────
            elif choice == 6:
                insights = ctx.insights.get_transaction_insights(
                    curr_start=curr_start, curr_end=curr_end,
                )
                _render_insights(insights, section="🧾  Transaction Insights")
                pause()

            # ── 7. Debt ──────────────────────────────────────────────
            elif choice == 7:
                insights = ctx.insights.get_debt_insights(
                    curr_start=curr_start, curr_end=curr_end,
                )
                _render_insights(insights, section="📋  Debt Insights")
                pause()

            # ── 8. Payment method ────────────────────────────────────
            elif choice == 8:
                insights = ctx.insights.get_payment_insights(
                    curr_start=curr_start, curr_end=curr_end,
                    prev_start=prev_start, prev_end=prev_end,
                )
                _render_insights(insights, section="💳  Payment Method Insights")
                pause()

            # ── 9. Summary ───────────────────────────────────────────
            elif choice == 9:
                summary = ctx.insights.get_summary(
                    curr_start=curr_start, curr_end=curr_end,
                    prev_start=prev_start, prev_end=prev_end,
                )
                _render_insights_summary(summary)
                pause()

            # ── 10. Filter by severity ───────────────────────────────
            elif choice == 10:
                sev = ask_choice(
                    "Severity level",
                    ["critical", "warning", "info"],
                )
                insights = ctx.insights.get_all_insights(
                    curr_start=curr_start, curr_end=curr_end,
                    prev_start=prev_start, prev_end=prev_end,
                    severity_filter=sev,
                    as_dicts=False,
                )
                _render_insights(
                    insights,
                    section=f"{_SEV_STYLE[sev]}  Insights",
                )
                pause()

        except BackSignal:
            pass
        except Exception as exc:
            print_error(str(exc))
            pause()


def _render_insights(insights: list, section: str = "Insights") -> None:
    """
    Render a list of Insight objects (or dicts) as rich panels.
    Each insight gets its own colour-coded panel: red/yellow/cyan.
    """
    from rich.panel import Panel

    print_section(section)

    if not insights:
        print_info("No insights generated for this period. 🎉 All metrics look healthy!")
        return

    console.print(f"  [dim]{len(insights)} insight(s) found[/dim]\n")

    _border = {
        "critical": "red",
        "warning":  "yellow",
        "info":     "cyan",
    }

    for ins in insights:
        # Accept both Insight objects and plain dicts
        if hasattr(ins, "severity"):
            sev, title, msg, cat = ins.severity, ins.title, ins.message, ins.category
        else:
            sev   = ins.get("severity", "info")
            title = ins.get("title", "—")
            msg   = ins.get("message", "")
            cat   = ins.get("category", "")

        cat_label  = _CAT_LABELS.get(cat, cat)
        sev_badge  = _SEV_STYLE.get(sev, sev)
        border_col = _border.get(sev, "cyan")

        body = (
            f"{msg}\n\n"
            f"[dim]Category: {cat_label}   Severity: {sev_badge}[/dim]"
        )

        console.print(
            Panel(
                body,
                title=f"[bold]{title}[/bold]",
                border_style=border_col,
                padding=(0, 2),
            )
        )


def _render_insights_summary(summary: dict) -> None:
    """Render the insights summary as colour-coded badge panels + top insight."""
    from rich.columns import Columns
    from rich.panel import Panel
    from rich.align import Align

    print_section("💡  Insights Summary")

    total    = summary.get("total", 0)
    critical = summary.get("critical", 0)
    warning  = summary.get("warning", 0)
    info_cnt = summary.get("info", 0)
    period   = summary.get("period", {})

    console.print()
    console.print(Columns([
        Panel(
            Align.center(f"[bold red]{critical}[/bold red]"),
            title="🚨 Critical",
            border_style="red",
        ),
        Panel(
            Align.center(f"[bold yellow]{warning}[/bold yellow]"),
            title="⚠️  Warning",
            border_style="yellow",
        ),
        Panel(
            Align.center(f"[bold cyan]{info_cnt}[/bold cyan]"),
            title="ℹ️  Info",
            border_style="cyan",
        ),
        Panel(
            Align.center(f"[bold white]{total}[/bold white]"),
            title="📋 Total",
            border_style="dim",
        ),
    ], expand=True))

    if period:
        console.print(
            f"\n  [dim]Current period : {period.get('current', '—')}[/dim]"
        )
        console.print(
            f"  [dim]Prior period   : {period.get('prior',   '—')}[/dim]\n"
        )

    # By-category breakdown table
    by_cat = summary.get("by_category", {})
    if any(v > 0 for v in by_cat.values()):
        print_section("By Category")
        rows = [
            {"category": _CAT_LABELS.get(k, k), "count": v}
            for k, v in by_cat.items() if v > 0
        ]
        rows.sort(key=lambda r: r["count"], reverse=True)
        print_table(
            rows,
            columns=[("Category", "category"), ("Insights", "count")],
            title="",
        )

    # Top insight highlight
    top = summary.get("top_insight")
    if top:
        print_section("🔝 Top Insight")
        _render_insights([top])
 
 
# ════════════════════════════════════════════════════════
# ⑪ ACCOUNT SETTINGS
# ════════════════════════════════════════════════════════
 
def menu_settings(ctx: AppCtx) -> None:
    # ── Base items (all users) ────────────────────────────────
    ITEMS = [
        ("Change Password",          "Update your login password"),
        ("Change Security Answer",   "Update your security answer"),
        ("Change Security Question", "Update your security question"),
        ("View My Profile",          "See your account details"),
        ("Logout",                   "Sign out and return to login"),
    ]

    # ── Admin-only extras ─────────────────────────────────────
    if ctx.is_admin():
        ITEMS += [
            ("List All Users",    "[admin] View all registered users"),
            ("Promote to Admin",  "[admin] Grant admin role to a user"),
            ("Demote to User",    "[admin] Revoke admin from a user"),
            ("Activate User",     "[admin] Re-enable a disabled account"),   # was MISSING
            ("Deactivate User",   "[admin] Disable a user account"),
            ("Delete User",       "[admin] Permanently remove a user"),      # was MISSING
        ]

    while True:
        clear_screen()
        print_header("👤  Account Settings", username=ctx.username, role=ctx.role)

        try:
            choice = prompt_choice(ITEMS, title="Settings", show_back=True)
        except BackSignal:
            return

        # Fresh UserModel each iteration so current_user is always in sync
        um = UserModel(ctx.conn)
        um.current_user = ctx.user

        try:
            # ── 1. Change Password ───────────────────────────
            if choice == 1:
                old_pass = ask_password("Current password (to verify it's you)")
                test = UserModel(ctx.conn).authenticate(ctx.username, old_pass)
                if not test.get("success"):
                    print_error("Current password is incorrect.")
                    pause()
                    continue

                new_pass = ask_password("New password (min 6 chars)")
                # Fetch and display the stored security question
                try:
                    question = um.get_security_question()
                except Exception:
                    question = "Security answer"
                sec_ans = ask_str(
                    f"Security answer  [{question}]",
                    required=True,
                )
                # UserModel.change_password(new_password, secur_ans) — no username arg
                result = um.change_password(new_pass, sec_ans)
                print_result(result)
                pause()

            # ── 2. Change Security Answer ────────────────────
            elif choice == 2:
                try:
                    question = um.get_security_question()
                except Exception:
                    question = "your security question"
                new_ans = ask_str(f"New answer for: [{question}]", required=True)
                # UserModel.change_security_answer(new_answer) — no username arg
                result = um.change_security_answer(new_ans)
                print_result(result)
                pause()

            # ── 3. Change Security Question ──────────────────
            elif choice == 3:
                try:
                    current_q = um.get_security_question()
                    print_info(f"Current question: [bold]{current_q}[/bold]")
                except Exception:
                    pass
                new_q = ask_str("New security question", required=True)
                result = um.change_security_question(new_q)
                print_result(result)
                pause()

            # ── 4. View My Profile ───────────────────────────
            elif choice == 4:
                password    = ask_password("Confirm password")
                sec_ans     = ask_str("Security answer", required=False, default="")
                res         = um.get_all_user_details(
                    ctx.username,
                    password=password,
                    security_answer=sec_ans or None,
                )
                if res.get("success"):
                    # get_all_user_details returns a "users" list — find own record
                    users_list = res.get("users", [])
                    own = next(
                        (u for u in users_list if u.get("username") == ctx.username),
                        users_list[0] if users_list else {},
                    )
                    print_detail_panel(
                        own,
                        title="My Profile",
                        exclude_keys=["password_hash", "security_answer_hash",
                                      "security_question"],
                        date_keys={"created_at", "updated_at"},
                    )
                else:
                    print_error(res.get("message", "Could not retrieve profile."))
                pause()

            # ── 5. Logout ────────────────────────────────────
            elif choice == 5:
                if ask_confirm("Log out?", default=False):
                    um.logout()
                    raise LogoutSignal()

            # ══ ADMIN-ONLY (choices 6–11) ════════════════════

            # ── 6. List All Users ────────────────────────────
            elif ctx.is_admin() and choice == 6:
                res  = um.list_users()
                rows = res.get("users", []) if isinstance(res, dict) else res
                print_table(
                    rows,
                    columns=[
                        ("ID",         "user_id"),
                        ("Username",   "username"),
                        ("Role",       "role"),
                        ("Active",     "is_active"),
                        ("Created",    "created_at"),
                    ],
                    title=f"All Users ({len(rows)})",
                    formatters={
                        "is_active":  lambda v: "[green]Yes[/green]" if v else "[red]No[/red]",
                        "created_at": fmt_date,
                    },
                )
                pause()

            # ── 7. Promote to Admin ──────────────────────────
            elif ctx.is_admin() and choice == 7:
                uname  = ask_str("Username to promote")
                if ask_confirm(f"Grant admin to '{uname}'?", default=False):
                    result = um.promote_to_admin(uname)
                    print_result(result)
                pause()

            # ── 8. Demote to User ────────────────────────────
            elif ctx.is_admin() and choice == 8:
                uname  = ask_str("Username to demote")
                if ask_confirm(f"Revoke admin from '{uname}'?", default=False):
                    result = um.demote_to_user(uname)
                    print_result(result)
                pause()

            # ── 9. Activate User  (was MISSING) ─────────────
            elif ctx.is_admin() and choice == 9:
                uname  = ask_str("Username to activate")
                result = um.activate_user(uname)
                print_result(result)
                pause()

            # ── 10. Deactivate User ──────────────────────────
            elif ctx.is_admin() and choice == 10:
                uname = ask_str("Username to deactivate")
                if ask_confirm(f"Deactivate '{uname}'?", default=False):
                    result = um.deactivate_user(uname)
                    print_result(result)
                pause()

            # ── 11. Delete User  (was MISSING) ───────────────
            elif ctx.is_admin() and choice == 11:
                uname = ask_str("Username to permanently delete")
                print_warning(
                    f"This will PERMANENTLY delete '{uname}' — this cannot be undone."
                )
                if ask_confirm(f"Type 'yes' to confirm deletion of '{uname}'?",
                               default=False):
                    result = um.delete_user(uname)
                    if result is True or (isinstance(result, dict) and result.get("success")):
                        print_success(f"User '{uname}' deleted.")
                    else:
                        msg = result.get("message", "Delete failed.") if isinstance(result, dict) else "User not found."
                        print_error(msg)
                pause()

        except BackSignal:
            pass
        except LogoutSignal:
            raise
        except Exception as exc:
            print_error(str(exc))
            pause()
            
# ════════════════════════════════════════════════════════════════════════════
# ⑪  EXPORT / REPORTS
# ════════════════════════════════════════════════════════════════════════════

# Shared import helpers used inside this menu
def _build_tx_filters(
    group_by: Optional[str] = None,
) -> "TransactionSearchRequest":
    """Interactive prompt to build a TransactionSearchRequest."""
    print_section("📅  Date Range  (blank = all time)")
    start = ask_date("Start date", required=False)
    end   = ask_date("End date",   required=False)

    print_section("💰  Amount Range  (blank = no limit)")
    min_amt = ask_float("Min amount", required=False)
    max_amt = ask_float("Max amount", required=False)

    print_section("🔖  Transaction Type  (blank = all)")
    tx_type = ask_choice(
        "Type filter",
        ["income", "expense", "transfer",
         "debt_borrowed", "debt_repaid",
         "investment_deposit", "investment_withdraw"],
        required=False,
    )

    return TransactionSearchRequest(
        date=DateFilter(start_date=start, end_date=end),
        amount=AmountFilter(
            min_amount=min_amt,
            max_amount=max_amt,
        ),
        tx_type=TransactionTypeFilter(
            transaction_types=[tx_type] if tx_type else None
        ),
        sort=SortOptions(sort_by="transaction_date", sort_order="ASC"),
    )


def _print_export_result(meta: "ExportMetadata") -> None:
    """Display a Rich panel summarising the export output."""
    size_kb = meta.file_size_bytes / 1024
    print_detail_panel(
        {
            "File":         meta.filename,
            "Path":         meta.filepath,
            "Format":       meta.format.upper(),
            "Records":      meta.record_count,
            "Date Range":   meta.date_range,
            "File Size":    f"{size_kb:.1f} KB",
            "Generated At": fmt_date(meta.generated_at),
        },
        title="✅  Export Complete",
        style="green",
    )


def menu_exports(ctx: AppCtx) -> None:

    ITEMS = [
        # ── Transaction exports ────────────────────────────────
        ("Transactions → CSV",          "Flat or grouped CSV"),
        ("Transactions → PDF",          "Formatted PDF report"),
        ("Transactions → Excel",        "Multi-sheet .xlsx with charts"),
        # ── Account exports ────────────────────────────────────
        ("Accounts → CSV",              "Account list export"),
        ("Accounts → PDF",              "Account summary PDF"),
        ("Accounts → Excel",            "Formatted account spreadsheet"),
        # ── Category export ────────────────────────────────────
        ("Categories → CSV",            "Category list export"),
        # ── Pre-built reports ──────────────────────────────────
        ("Monthly Report",              "Full month  (CSV + PDF or Excel)"),
        ("Weekly Report",               "ISO-week report (CSV + PDF)"),
        ("Daily Report",                "Single-day report (CSV + PDF)"),
        ("Category Analysis",           "Spending drill-down for one category"),
        # ── Settings ───────────────────────────────────────────
        ("⚙️   Export Settings",         "Change output folder / page size"),
    ]

    GROUP_OPTIONS = ["category", "account", "month", "week", "date"]
    FORMAT_OPTIONS = ["csv", "pdf", "both"]

    while True:
        clear_screen()
        print_header("📤  Export / Reports", username=ctx.username, role=ctx.role)

        try:
            choice = prompt_choice(ITEMS, title="Exports", show_back=True)
        except BackSignal:
            return

        try:
            # ── 1. Transactions → CSV ────────────────────────
            if choice == 1:
                print_section("📄  Transactions → CSV")
                group_by = ask_choice(
                    "Group by (optional)",
                    GROUP_OPTIONS,
                    required=False,
                )
                filters  = _build_tx_filters(group_by)
                meta     = ctx.exports.export_transactions_csv(
                    filters, group_by=group_by
                )
                _print_export_result(meta)
                pause()

            # ── 2. Transactions → PDF ────────────────────────
            elif choice == 2:
                print_section("📑  Transactions → PDF")
                group_by = ask_choice(
                    "Group by (optional)",
                    GROUP_OPTIONS,
                    required=False,
                )
                title    = ask_str("Report title", default="Transaction Report")
                filters  = _build_tx_filters(group_by)
                meta     = ctx.exports.export_transactions_pdf(
                    filters, title=title, group_by=group_by
                )
                _print_export_result(meta)
                pause()

            # ── 3. Transactions → Excel ──────────────────────
            elif choice == 3:
                print_section("📊  Transactions → Excel")
                inc_summary = ask_confirm("Include summary sheet?", default=True)
                inc_charts  = ask_confirm("Include charts?",         default=True)
                filters     = _build_tx_filters()
                meta        = ctx.exports.export_transactions_excel(
                    filters,
                    include_summary=inc_summary,
                    include_charts=inc_charts,
                )
                _print_export_result(meta)
                pause()

            # ── 4. Accounts → CSV ────────────────────────────
            elif choice == 4:
                print_section("📄  Accounts → CSV")
                from features.search import AccountSearchRequest, StatusFilter
                active_only = ask_confirm("Active accounts only?", default=True)
                filters = AccountSearchRequest(
                    status=StatusFilter(active_only=active_only)
                )
                meta = ctx.exports.export_accounts_csv(filters)
                _print_export_result(meta)
                pause()

            # ── 5. Accounts → PDF ────────────────────────────
            elif choice == 5:
                print_section("📑  Accounts → PDF")
                from features.search import AccountSearchRequest, StatusFilter
                active_only = ask_confirm("Active accounts only?", default=True)
                title   = ask_str("Report title", default="Account Summary Report")
                filters = AccountSearchRequest(
                    status=StatusFilter(active_only=active_only)
                )
                meta = ctx.exports.export_account_summary_pdf(filters, title=title)
                _print_export_result(meta)
                pause()

            # ── 6. Accounts → Excel ──────────────────────────
            elif choice == 6:
                print_section("📊  Accounts → Excel")
                from features.search import AccountSearchRequest, StatusFilter
                active_only = ask_confirm("Active accounts only?", default=True)
                filters = AccountSearchRequest(
                    status=StatusFilter(active_only=active_only)
                )
                meta = ctx.exports.export_accounts_excel(filters)
                _print_export_result(meta)
                pause()

            # ── 7. Categories → CSV ──────────────────────────
            elif choice == 7:
                print_section("📄  Categories → CSV")
                from features.search import CategorySearchRequest
                name_filter = ask_str("Filter by name (optional)", required=False)
                filters = CategorySearchRequest(name=name_filter)
                meta = ctx.exports.export_categories_csv(filters)
                _print_export_result(meta)
                pause()

            # ── 8. Monthly Report ────────────────────────────
            elif choice == 8:
                print_section("📅  Monthly Report")
                year   = ask_int("Year",  default=date.today().year,  min_val=2000)
                month  = ask_int("Month", default=date.today().month, min_val=1, max_val=12)
                fmt    = ask_choice("Format", ["csv", "pdf", "excel", "both"],
                                    default="both")

                if fmt == "excel":
                    meta = ctx.exports.export_monthly_report_excel(year, month)
                    _print_export_result(meta)
                else:
                    results = ctx.exports.export_monthly_report(
                        year, month,
                        format="both" if fmt == "both" else fmt,
                    )
                    if isinstance(results, list):
                        for m in results:
                            _print_export_result(m)
                    else:
                        _print_export_result(results)
                pause()

            # ── 9. Weekly Report ─────────────────────────────
            elif choice == 9:
                print_section("📅  Weekly Report")
                year = ask_int("Year", default=date.today().year, min_val=2000)
                week = ask_int("ISO Week number", default=date.today().isocalendar()[1],
                               min_val=1, max_val=53)
                fmt  = ask_choice("Format", FORMAT_OPTIONS, default="both")

                results = ctx.exports.export_weekly_report(year, week, format=fmt)
                if isinstance(results, list):
                    for m in results:
                        _print_export_result(m)
                else:
                    _print_export_result(results)
                pause()

            # ── 10. Daily Report ─────────────────────────────
            elif choice == 10:
                print_section("📅  Daily Report")
                target = ask_date("Report date", required=True, default=date.today())
                fmt    = ask_choice("Format", FORMAT_OPTIONS, default="both")

                results = ctx.exports.export_daily_report(target, format=fmt)
                if isinstance(results, list):
                    for m in results:
                        _print_export_result(m)
                else:
                    _print_export_result(results)
                pause()

            # ── 11. Category Analysis ────────────────────────
            elif choice == 11:
                print_section("🗂   Category Analysis")
                cat_name = ask_str("Category name (exact match)")
                preset   = ask_choice(
                    "Date preset",
                    ["last_7_days", "last_30_days", "last_90_days",
                     "this_month", "last_month", "this_year"],
                    default="last_30_days",
                )
                fmt = ask_choice("Format", FORMAT_OPTIONS, default="both")

                results = ctx.exports.export_category_analysis(
                    cat_name, date_preset=preset, format=fmt
                )
                if isinstance(results, list):
                    for m in results:
                        _print_export_result(m)
                else:
                    _print_export_result(results)
                pause()

            # ── 12. Export Settings ──────────────────────────
            elif choice == 12:
                print_section("⚙️   Export Settings")
                print_detail_panel(
                    {
                        "Output Directory":    ctx.exports.config.output_dir,
                        "PDF Page Size":       ctx.exports.config.pdf_pagesize,
                        "CSV Encoding":        ctx.exports.config.csv_encoding,
                        "Include Charts":      ctx.exports.config.excel_include_charts,
                        "Include Formulas":    ctx.exports.config.excel_include_formulas,
                    },
                    title="Current Export Config",
                )
                if ask_confirm("Change output directory?", default=False):
                    new_dir = ask_str("New output path", default=ctx.exports.config.output_dir)
                    ctx.exports.config.output_dir = new_dir
                    ctx.exports._ensure_output_dir()
                    print_success(f"Output directory set to [bold cyan]{new_dir}[/bold cyan]")

                if ask_confirm("Change PDF page size?", default=False):
                    size = ask_choice("Page size", ["letter", "A4"], default="letter")
                    ctx.exports.config.pdf_pagesize = size
                    print_success(f"PDF page size set to [bold cyan]{size}[/bold cyan]")
                pause()

        except BackSignal:
            pass
        except Exception as exc:
            print_error(str(exc))
            pause()
 
 
# ════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════
 
def main() -> None:
    """
    Bootstrap:
      1. Connect to the database
      2. Auth screen (login / register)   — loop on bad creds
      3. App main menu                    — loop until logout / exit
      4. On LogoutSignal → back to auth screen
      5. On ExitSignal   → clean farewell
    """
    # ── DB Connection ────────────────────────────────────
    db   = DatabaseConnection()
    conn = db.get_connection()
 
    if not conn:
        console.print("[bold red]❌  Could not connect to the database. "
                      "Check your .env / config.[/bold red]")
        sys.exit(1)
 
    # ── Auth + App Loop ───────────────────────────────────
    while True:
        try:
            ctx = auth_screen(conn)
            app_main(ctx)
        except LogoutSignal:
            console.print("\n[dim]Logged out.[/dim]")
            continue     # back to auth
        except ExitSignal:
            break
        except KeyboardInterrupt:
            break
 
    # ── Cleanup ───────────────────────────────────────────
    try:
        conn.close()
    except Exception:
        pass
 
    console.print("\n[bold cyan]👋  Goodbye! Stay financially fit.[/bold cyan]\n")
 
 
if __name__ == "__main__":
    main()