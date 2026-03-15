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
 
import sys
import traceback
from datetime import date, datetime
from typing import Any, Dict, Optional
 
# ── Rich ─────────────────────────────────────────────────
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
    clear_screen, pause, print_app_banner, print_header,
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
 
            # Need a temp logged-in context for change_password (it requires _require_login)
            # Workaround: direct SQL-level reset via authenticate flow
            username = ask_str("Your username", allow_back=True)
            sec_ans  = ask_str("Security answer", allow_back=True)
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
            elif choice == 9:
                print_info("Going back to main menu…")
                return
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
                currency = ask_str("Currency", default="KES")
                balance  = ask_float("Opening balance", default=0.0, min_val=0)
                desc     = ask_str("Description", required=False)
 
                result = ctx.accounts.create_account(
                    name=name,
                    account_type=acc_type,
                    currency=currency,
                    balance=balance,
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
                    ("currency",     "New currency"),
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
                cats = res.get("categories", res) if isinstance(res, dict) else res
                print_table(
                    cats,
                    columns=[
                        ("ID",     "category_id"),
                        ("Name",   "name"),
                        ("Parent", "parent_id"),
                        ("Colour", "color"),
                        ("Icon",   "icon"),
                    ],
                    title="Categories",
                    empty_message="No categories yet — create one!",
                )
                pause()
 
            elif choice == 2:
                print_section("➕  Create Category")
                name      = ask_str("Category name")
                parent_id = ask_int("Parent category ID", required=False)
                color     = ask_str("Colour hex (e.g. #FF5733)", required=False)
                icon      = ask_str("Icon emoji (e.g. 🍕)", required=False)
                desc      = ask_str("Description", required=False)
 
                result = ctx.categories.create_category(
                    name=name,
                    parent_id=parent_id,
                    color=color,
                    icon=icon,
                    description=desc,
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
                    ("color",       "New colour"),
                    ("icon",        "New icon"),
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
                    result = ctx.categories.delete_category(cat_id)
                    print_result(result)
                pause()
 
            elif choice == 6:
                cat_id = ask_int("Category ID to restore")
                result = ctx.categories.restore_category(cat_id)
                print_result(result)
                pause()
 
            elif choice == 7:
                tree = ctx.categories.get_category_tree()
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
        console.print(f"  {prefix}[cyan]{name}[/cyan]  [dim](#{cat_id})[/dim]")
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
                logs  = ctx.transactions.view_audit_logs(transaction_id=tx_id)
                print_table(
                    logs,
                    columns=[
                        ("Time",   "created_at"),
                        ("Action", "action"),
                        ("User",   "performed_by"),
                    ],
                    title="Transaction Audit Logs",
                    formatters={"created_at": fmt_date},
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
 
    title       = ask_str("Title / description")
    tx_type     = ask_choice("Transaction type", TX_TYPES)
    amount      = ask_float("Amount", min_val=0.01)
    pay_method  = ask_choice("Payment method", PAY_METHODS, default="bank")
    tx_date     = ask_date("Transaction date", required=False, default=date.today())
    cat_id      = ask_int("Category ID", required=False)
    desc        = ask_str("Notes", required=False)
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
        transaction_date=tx_date or date.today(),
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
    limit = ask_int("How many to show", default=20, min_val=1, max_val=200)
 
    res  = ctx.transactions.list_transactions(limit=limit, include_deleted=False)
    txns = res.get("transactions", [])
 
    print_table(
        txns,
        columns=[
            ("ID",      "transaction_id"),
            ("Date",    "transaction_date"),
            ("Title",   "title"),
            ("Type",    "transaction_type"),
            ("Amount",  "amount"),
            ("Account", "account_id"),
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
 
    if not updates or list(updates.keys()) == ["allow_overdraft"]:
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
                limit   = ask_int("How many categories", default=10, min_val=1)
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
                        ("Time",   "created_at"),
                        ("Action", "action"),
                    ],
                    title="Goal Audit Logs",
                    formatters={"created_at": fmt_date},
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
                res  = ctx.recurring.list_recurring()
                rows = res.get("recurring", res) if isinstance(res, dict) else res
                print_table(
                    rows,
                    columns=[
                        ("ID",        "recurring_id"),
                        ("Name",      "name"),
                        ("Type",      "transaction_type"),
                        ("Freq",      "frequency"),
                        ("Amount",    "amount"),
                        ("Next Due",  "next_due"),
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
                rid     = ask_int("Recurring ID")
                updates = {}
                name    = ask_str("New name", required=False)
                if name:
                    updates["name"] = name
                amount  = ask_float("New amount", required=False)
                if amount:
                    updates["amount"] = amount
                freq    = ask_choice("New frequency", FREQUENCIES, required=False)
                if freq:
                    updates["frequency"] = freq
                if updates:
                    result = ctx.recurring.update_recurring(rid, **updates)
                    print_result(result)
                else:
                    print_warning("No changes entered.")
                pause()
 
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
                hard = ask_confirm("Hard delete?", default=False)
                result = ctx.recurring.delete_recurring(rid, soft=not hard)
                print_result(result)
                pause()
 
            elif choice == 7:
                days = ask_int("Look-ahead days", default=7, min_val=1)
                rows = ctx.recurring.get_upcoming_due(days_ahead=days)
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
                    result = ctx.recurring.process_due_transactions()
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
    name       = ask_str("Rule name")
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
                start   = ask_date("From date",  required=False)
                end     = ask_date("To date",    required=False)
                min_amt = ask_float("Min amount", required=False)
                max_amt = ask_float("Max amount", required=False)
                tx_type = ask_choice("Transaction type", TX_TYPES, required=False)
                limit   = ask_int("Max results", default=50, min_val=1)
 
                from features.search import TransactionSearchRequest, TextSearchFilter, DateFilter, AmountFilter, TxTypeFilter
                req = TransactionSearchRequest(
                    text=TextSearchFilter(search_text=text) if text else TextSearchFilter(),
                    date=DateFilter(start_date=start, end_date=end),
                    amount=AmountFilter(min_amount=min_amt, max_amount=max_amt),
                    tx_type=TxTypeFilter(
                        transaction_types=[tx_type] if tx_type else None
                    ),
                    pagination=type("P", (), {"limit": limit, "offset": 0})(),
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
                from features.search import CategorySearchRequest
                req    = CategorySearchRequest(name=text)
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
                pause()
 
            elif choice == 3:
                from features.search import AccountSearchRequest
                acc_type = ask_choice("Account type", ACCOUNT_TYPES, required=False)
                req      = AccountSearchRequest(account_type=acc_type)
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
 
 
# ════════════════════════════════════════════════════════
# ⑪ ACCOUNT SETTINGS
# ════════════════════════════════════════════════════════
 
def menu_settings(ctx: AppCtx) -> None:
    ITEMS = [
        ("Change Password",         "Update your login password"),
        ("Change Security Answer",  "Update password-reset answer"),
        ("View My Profile",         "See your account details"),
        ("Logout",                  "Sign out and return to login"),
    ]
 
    # Admin-only extras
    if ctx.is_admin():
        ITEMS += [
            ("List All Users",   "[admin] View all registered users"),
            ("Promote to Admin", "[admin] Grant admin role to a user"),
            ("Demote to User",   "[admin] Revoke admin from a user"),
            ("Deactivate User",  "[admin] Disable a user account"),
        ]
 
    while True:
        clear_screen()
        print_header("👤  Account Settings", username=ctx.username, role=ctx.role)
 
        try:
            choice = prompt_choice(ITEMS, title="Settings", show_back=True)
        except BackSignal:
            return
 
        um = UserModel(ctx.conn)
        um.current_user = ctx.user
 
        try:
            if choice == 1:
                old_pass = ask_password("Current password")
                # Verify current password first
                test = UserModel(ctx.conn).authenticate(ctx.username, old_pass)
                if not test.get("success"):
                    print_error("Current password is incorrect.")
                    pause()
                    continue
 
                new_pass = ask_password("New password (min 6 chars)")
                sec_ans  = ask_str("Security answer (to confirm)")
                result   = um.change_password(ctx.username, new_pass, sec_ans)
                print_result(result)
                pause()
 
            elif choice == 2:
                new_ans = ask_str("New security answer")
                result  = um.change_security_answer(ctx.username, new_ans)
                print_result(result)
                pause()
 
            elif choice == 3:
                res = um.get_all_user_details(
                    ctx.username,
                    password=ask_password("Confirm password"),
                    security_answer=ask_str("Security answer"),
                )
                if res.get("success"):
                    user_data = res.get("user", res)
                    print_detail_panel(
                        user_data,
                        title="My Profile",
                        exclude_keys=["password_hash", "security_answer_hash"],
                        date_keys={"created_at", "updated_at"},
                    )
                else:
                    print_error(res.get("message", "Could not retrieve profile."))
                pause()
 
            elif choice == 4:
                if ask_confirm("Log out?", default=False):
                    um.logout()
                    raise LogoutSignal()
 
            # ── Admin ─────────────────────────────────
            elif ctx.is_admin() and choice == 5:
                res  = um.list_users()
                rows = res.get("users", res) if isinstance(res, dict) else res
                print_table(
                    rows,
                    columns=[
                        ("ID",       "user_id"),
                        ("Username", "username"),
                        ("Role",     "role"),
                        ("Active",   "is_active"),
                    ],
                    title="All Users",
                    formatters={
                        "is_active": lambda v: "[green]Yes[/green]" if v else "[red]No[/red]",
                    },
                )
                pause()
 
            elif ctx.is_admin() and choice == 6:
                uname  = ask_str("Username to promote")
                result = um.promote_to_admin(uname)
                print_result(result)
                pause()
 
            elif ctx.is_admin() and choice == 7:
                uname  = ask_str("Username to demote")
                result = um.demote_to_user(uname)
                print_result(result)
                pause()
 
            elif ctx.is_admin() and choice == 8:
                uname  = ask_str("Username to deactivate")
                if ask_confirm(f"Deactivate '{uname}'?"):
                    result = um.deactivate_user(uname)
                    print_result(result)
                pause()
 
        except BackSignal:
            pass
        except LogoutSignal:
            raise
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