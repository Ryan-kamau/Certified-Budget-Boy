# core/utils.py
"""
============================================================
 Budget Tracker — Shared Utilities
============================================================
 This module is the single source of truth for:
   - Base exceptions used across every model and feature
   - A simple error-only file logger
   - SQL query building helpers
   - Input sanitization and enum validation
   - Date and amount range parsing / validation
   - Domain-level validation patterns (transaction types etc.)
   - Pagination arithmetic
   - Display formatting helpers

 Import examples
 ---------------
   from core.utils import (
       DatabaseError, ValidationError, NotFoundError,
       error_logger,
       QueryBuilder, InputSanitizer, DateRangeValidator,
       AmountRangeValidator, ValidationPatterns,
       PaginationHelper, FormatHelper,
   )

 Sections
 --------
   1. Base Exceptions
   2. ErrorLogger
   3. QueryBuilder
   4. InputSanitizer
   5. DateRangeValidator
   6. AmountRangeValidator
   7. ValidationPatterns
   8. PaginationHelper
   9. FormatHelper
============================================================
"""

from __future__ import annotations

import logging
import os
import traceback
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional, Tuple, Union


# ===========================================================================
# 1. Base Exceptions
# ===========================================================================
# Why a hierarchy?
# ----------------
# Every model currently defines its own completely separate exception class:
#   AccountDataBaseError, GoalDatabaseError, RecurringDatabaseError …
# They are all unrelated types in Python's eye even though they mean the
# same thing.  The app layer (main.py) therefore has no way to catch "any
# database error" without importing and listing every one of them.
#
# By making each per-model exception inherit from the shared base below,
# a single `except DatabaseError` in main.py catches them all — without
# changing the names or any other behaviour in the individual models.
#
# Migration is one line per model:
#   BEFORE: class AccountDataBaseError(AccountError): pass
#   AFTER:  class AccountDataBaseError(DatabaseError): pass
# ===========================================================================

class BudgetTrackerError(Exception):
    """
    Root base class for every custom exception in this application.

    Inheriting from this (directly or indirectly) lets the app entry
    point catch anything the application raises without accidentally
    swallowing Python built-in errors like KeyError or AttributeError.

    Usage in main.py:
        except BudgetTrackerError as exc:
            print_error(str(exc))   # last-resort handler
    """


class DatabaseError(BudgetTrackerError):
    """
    Raised when any database operation fails.

    Covers connection failures, query execution errors, constraint
    violations, and rollback failures.

    The ``original`` attribute stores the raw mysql.connector.Error that
    triggered this exception.  Preserving it means you never lose the
    MySQL error code or message even after it has been wrapped — the
    error log and the stack trace both show both layers.
    """

    def __init__(self, message: str, *, original: Optional[Exception] = None) -> None:
        super().__init__(message)
        # Store the raw exception so callers can inspect it if needed:
        #   except DatabaseError as exc:
        #       print(exc.original)  # → IntegrityError(1062, "Duplicate entry …")
        self.original = original

    def __str__(self) -> str:
        # Override __str__ so that str(exc) or print(exc) automatically
        # includes the original MySQL error in the output — useful in logs.
        if self.original:
            return f"{super().__str__()} (caused by: {self.original!r})"
        return super().__str__()


class ValidationError(BudgetTrackerError):
    """
    Raised when user-supplied data fails a business-rule check.

    Examples of when to raise this:
      - Amount is negative
      - Transaction type is not in the allowed list
      - End date is before start date
      - Required field is missing or blank

    The ``field`` and ``value`` attributes make the error message precise.
    Instead of "invalid input", the CLI layer can show exactly which field
    was wrong and what value the user gave.

    How to use in a model
    ---------------------
    Change the parent class:

        from core.utils import ValidationError

        class TransactionValidationError(ValidationError): pass

    Raise with context:

        if amount <= 0:
            raise TransactionValidationError(
                "Amount must be greater than zero.",
                field="amount",
                value=amount,
            )

    In main.py the handler then has access to exc.field and exc.value
    to build a precise error message for the user.
    """

    def __init__(
        self,
        message: str,
        *,
        field: Optional[str] = None,   # name of the bad input field
        value: Any = None,             # the actual bad value supplied
    ) -> None:
        super().__init__(message)
        self.field = field
        self.value = value

    def __str__(self) -> str:
        # Build a pipe-separated string so the log line is easy to scan:
        #   "Amount must be > 0 | field='amount' | value=-50"
        parts = [super().__str__()]
        if self.field:
            parts.append(f"field='{self.field}'")
        if self.value is not None:
            parts.append(f"value={self.value!r}")
        return " | ".join(parts)


class ConfigurationError(BudgetTrackerError):
    """
    Raised when the application cannot read its own configuration.

    Triggered by DatabaseConnection._load_config() when:
      - config/config.ini does not exist
      - The [mysql] section is missing
      - A required key (host, user, password, database, port) is absent

    This is raised before any DB connection is attempted, so it is
    distinct from DatabaseError which covers runtime query failures.
    """


class NotFoundError(BudgetTrackerError):
    """
    Raised when a requested record does not exist in the database.

    Per-model subclasses should inherit from this:

        from core.utils import NotFoundError

        class AccountNotFoundError(NotFoundError): pass   # was (AccountError)
        class GoalNotFoundError(NotFoundError): pass      # was (GoalError)

    The ``resource_id`` attribute stores the ID that was looked up so
    the error message can include it without formatting it into the
    message string at the raise site.

    Example:
        raise AccountNotFoundError(
            "Account not found.",
            resource_id=account_id,
        )

        # In main.py:
        except NotFoundError as exc:
            print_error(f"Record {exc.resource_id} does not exist.")
    """

    def __init__(self, message: str, *, resource_id: Any = None) -> None:
        super().__init__(message)
        # The PK / ID that was searched for — None for list queries
        self.resource_id = resource_id


# ===========================================================================
# 2. ErrorLogger
# ===========================================================================
# Design decisions
# ----------------
# ONE file for the whole app (reports/logs/errors.log).
#   Your audit_log table already records every successful CRUD operation
#   with full before/after data.  The error logger fills the gap that
#   audit_log cannot cover: failures that happen before a DB commit, which
#   leave no trace once the terminal session closes.
#   A single file is easier to grep than eleven per-module files.
#
# ERROR level only.
#   Successes go to audit_log.  This file is for failures.
#
# Human-readable lines, not JSON.
#   You will read this with `tail -f` or a text editor, not a log
#   aggregator.  Plain timestamped lines are faster to scan.
#
# Rotating file (10 MB, 3 backups).
#   Prevents unbounded disk growth.  You get ~40 MB of error history
#   before the oldest entries are dropped — plenty for a local app.
#
# Module-level singleton `error_logger`.
#   One instance is imported everywhere.  If every model created its own
#   ErrorLogger(), Python would open the same file multiple times and the
#   RotatingFileHandler would compete with itself.
# ===========================================================================

class ErrorLogger:
    """
    Shared, error-only file logger for the entire application.

    Writes one entry to ``reports/logs/errors.log`` each time
    :meth:`log_error` is called.  The file is created automatically on
    first use; the ``reports/logs/`` directory is created if it does not
    exist.

    Do not instantiate this class yourself.  Import and use the singleton
    defined at the bottom of this section::

        from core.utils import error_logger

    Log line format
    ---------------
    Each entry in the file looks like this::

        2025-07-04 14:32:01 | ERROR | TransactionModel._execute |
        user_id=7 | table=transactions | IntegrityError: 1062 Duplicate entry
        Traceback (most recent call last):
          File "models/transactions_model.py", line 94, in _execute
            cursor.execute(query, params)
        mysql.connector.errors.IntegrityError: 1062 Duplicate entry …

    File rotation
    -------------
    ``errors.log`` → ``errors.log.1`` → ``errors.log.2`` → ``errors.log.3``
    Each file capped at 10 MB.  Python's RotatingFileHandler handles the
    rename automatically on each app run when the size threshold is hit.
    """

    # Path to the directory where the log file will be created.
    # Matches the reports/exports/ pattern already used by ExportService.
    LOG_DIR = "reports/logs"

    # Single log file name — one file for the whole application.
    LOG_FILE = "errors.log"

    # Rotate when the file reaches 10 MB.
    MAX_BYTES = 10 * 1024 * 1024

    # Keep this many old rotated files before deleting the oldest.
    # 5 backups + the current file = up to ~50 MB of error history.
    BACKUP_COUNT = 5

    def __init__(self) -> None:
        # Build the underlying Python logger once when the singleton is
        # created at module import time.  Every call to log_error() after
        # that just writes to the already-open file handle.
        self._logger = self._build_logger()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_error(
        self,
        exc: Exception,
        *,
        location: str,
        user_id: Optional[int] = None,
        extra: Optional[str] = None,
        include_traceback: bool = True,
    ) -> None:
        """
        Write one error entry to ``reports/logs/errors.log``.

        Call this inside every ``except`` block that catches a genuine
        failure — before re-raising the wrapped exception.  The goal is
        to capture failures that never reach the audit_log table because
        the transaction was rolled back.

        Args:
            exc:
                The exception that was caught.  Its type name and message
                are included in the log line automatically.

            location:
                Dotted path to the method where the error was caught.
                Be specific — include both the class and method name so
                you can find it instantly without grepping the codebase.
                Examples:
                  "AccountModel._execute"
                  "TransactionModel.create_transaction"
                  "Scheduler.run_all_due_recurring"

            user_id:
                The current user's ID from ``current_user["user_id"]``.
                Pass ``None`` for errors that occur before login
                (e.g. a connection failure in DatabaseConnection).

            extra:
                A short freeform string for any additional context that
                is not covered by the other parameters.  Keep it brief.
                Examples:
                  "table=accounts"
                  "recurring_id=5"
                  "sql_preview=SELECT * FROM transactions WHERE …"

            include_traceback:
                ``True`` by default — the full Python stack trace is
                appended after the log line.  This is what you want for
                unexpected failures like MySQL errors.

                Set ``False`` for known / expected error types such as
                ``NotFoundError`` or ``ValidationError`` where the stack
                trace adds noise rather than diagnostic value — the error
                message already tells you everything.

        Usage examples::

            # In a model's _execute method (unexpected DB failure)
            except mysql.connector.Error as exc:
                error_logger.log_error(
                    exc,
                    location="AccountModel._execute",
                    user_id=self.user.get("user_id"),
                    extra="table=accounts",
                )
                raise AccountDataBaseError(f"MySQL Error: {exc}") from exc

            # In a feature service (known error type, no traceback needed)
            except RecurringNotFoundError as exc:
                error_logger.log_error(
                    exc,
                    location="Scheduler.preview_next_run",
                    user_id=self.user_id,
                    extra=f"recurring_id={recurring_id}",
                    include_traceback=False,
                )
                raise SchedulerError(f"Preview failed: {exc}") from exc
        """
        # Build each component of the log line separately for clarity
        user_part  = f"user_id={user_id}" if user_id is not None else "user_id=unknown"
        extra_part = f" | {extra}" if extra else ""

        # Type name + message, e.g. "IntegrityError: 1062 Duplicate entry"
        error_text = f"{type(exc).__name__}: {exc}"

        # Combine into a single line:
        # "AccountModel._execute | user_id=7 | table=accounts | IntegrityError: …"
        line = f"{location} | {user_part}{extra_part} | {error_text}"

        if include_traceback:
            # traceback.format_exc() returns the current exception's full
            # stack trace as a string.  When called outside an except block
            # it returns the string "NoneType: None" — guard against that.
            tb = traceback.format_exc().strip()
            if tb and "NoneType: None" not in tb:
                # Append the stack trace on the next line, indented by the
                # formatter's timestamp prefix so it reads as one block.
                line = f"{line}\n{tb}"

        # Write at ERROR level — the RotatingFileHandler filters to ERROR
        # and above, so info/debug calls elsewhere won't pollute this file.
        self._logger.error(line)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_logger(self) -> logging.Logger:
        """
        Configure and return the underlying Python logger.

        Called once by __init__.  Creates the log directory if needed,
        attaches a RotatingFileHandler, and sets a timestamp formatter.

        The ``propagate = False`` line prevents the log entries from also
        appearing in the root logger (which might print to stdout or
        write to a different file depending on the user's logging config).

        The ``if not logger.handlers`` guard prevents duplicate handlers
        being attached if this module is reloaded during testing or in
        interactive sessions.
        """
        # Create reports/logs/ if it doesn't already exist.
        # exist_ok=True means no error if it's already there.
        os.makedirs(self.LOG_DIR, exist_ok=True)

        log_path = os.path.join(self.LOG_DIR, self.LOG_FILE)

        # Use a namespaced logger name so it doesn't collide with any
        # other logger in the application or in third-party libraries.
        logger = logging.getLogger("budget_tracker.errors")
        logger.setLevel(logging.ERROR)

        # Cut off propagation to the root logger so entries only go to
        # our rotating file, not to stdout or any other handler.
        logger.propagate = False

        if not logger.handlers:
            # RotatingFileHandler automatically renames the current log
            # file to errors.log.1 (then .2, .3) when maxBytes is hit,
            # and starts a fresh errors.log.  backupCount controls how
            # many old copies to keep before deleting the oldest.
            handler = RotatingFileHandler(
                log_path,
                maxBytes=self.MAX_BYTES,
                backupCount=self.BACKUP_COUNT,
                encoding="utf-8",
            )
            # The formatter prepends the timestamp and level to every line.
            # %(asctime)s → "2025-07-04 14:32:01"
            # %(levelname)s → "ERROR"
            # %(message)s → the string we pass to self._logger.error(line)
            handler.setFormatter(
                logging.Formatter(
                    fmt="%(asctime)s | %(levelname)s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            logger.addHandler(handler)

        return logger


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
# Created once when this module is first imported.  Every model and feature
# that does `from core.utils import error_logger` gets the same instance,
# which means the same open file handle and no duplicate handlers.
error_logger = ErrorLogger()


# ===========================================================================
# 3. QueryBuilder
# ===========================================================================

class QueryBuilder:
    """
    Fluent builder for constructing dynamic SQL WHERE clauses.

    The problem it solves
    ---------------------
    Many queries in this app need optional filters — the user may or may
    not supply a date range, a category, a payment method, etc.  Without
    a builder you end up concatenating strings and managing a params list
    manually, which gets messy and error-prone.

    QueryBuilder lets you call only the methods for the filters that are
    actually present and builds the query incrementally.

    Typical usage::

        qb = QueryBuilder("SELECT * FROM transactions t WHERE 1=1")
        qb.add_condition("t.user_id = %s", user_id)
        qb.add_date_range("t.transaction_date", start, end)
        qb.add_amount_range("t.amount", min_amt, max_amt)
        qb.add_in_condition("t.transaction_type", ["income", "expense"])
        qb.add_order_by("t.transaction_date DESC")
        qb.add_limit_offset(limit=50, offset=0)

        sql, params = qb.build()
        cursor.execute(sql, params)

    The ``WHERE 1=1`` in the base query is intentional — it means the
    first ``add_condition`` call can always prefix with ``AND`` without
    needing to check whether it is the first condition or not.
    """

    def __init__(self, base_query: str) -> None:
        """
        Initialise the builder with the base SELECT / FROM / JOIN part of
        the query.  All add_* methods append to this string.

        Args:
            base_query: The fixed part of the SQL, usually ending with
                        ``WHERE 1=1`` so every subsequent condition can
                        start with ``AND``.
        """
        # The growing SQL string — add_* methods append to this
        self.query = base_query
        # Parallel list of bound parameters in the same order as the %s
        # placeholders added to self.query
        self.params: List[Any] = []

    def add_condition(self, condition: str, *params: Any) -> "QueryBuilder":
        """
        Append a raw ``AND <condition>`` clause with its bound parameters.

        This is the lowest-level method — all other add_* methods call
        this internally.  Use it directly when the higher-level helpers
        don't cover your specific filter.

        Args:
            condition: SQL fragment with %s placeholders, e.g.
                       ``"t.is_deleted = %s"`` or
                       ``"(t.account_id = %s OR t.source_account_id = %s)"``
            *params:   The values to bind to the %s placeholders in order.

        Returns:
            self — for method chaining.

        Example::

            qb.add_condition("t.is_deleted = %s", 0)
            qb.add_condition(
                "(t.account_id = %s OR t.source_account_id = %s)",
                account_id, account_id
            )
        """
        self.query += f" AND {condition}"
        self.params.extend(params)
        return self

    def add_date_range(
        self,
        column: str,
        start_date: Optional[date],
        end_date: Optional[date],
    ) -> "QueryBuilder":
        """
        Append ``>= start_date`` and / or ``<= end_date`` conditions.

        Both parameters are optional — pass ``None`` to skip either end
        of the range.  If both are None this method is a no-op.

        Args:
            column:     Fully qualified column name, e.g.
                        ``"t.transaction_date"``
            start_date: Lower bound (inclusive).  None → no lower bound.
            end_date:   Upper bound (inclusive).  None → no upper bound.

        Returns:
            self — for method chaining.
        """
        if start_date:
            self.add_condition(f"{column} >= %s", start_date)
        if end_date:
            self.add_condition(f"{column} <= %s", end_date)
        return self

    def add_amount_range(
        self,
        column: str,
        min_amount: Optional[Decimal],
        max_amount: Optional[Decimal],
    ) -> "QueryBuilder":
        """
        Append ``>= min_amount`` and / or ``<= max_amount`` conditions.

        Both parameters are optional — pass ``None`` to skip either bound.

        Args:
            column:     Column name, e.g. ``"t.amount"`` or ``"a.balance"``
            min_amount: Lower bound (inclusive).  None → no lower bound.
            max_amount: Upper bound (inclusive).  None → no upper bound.

        Returns:
            self — for method chaining.
        """
        if min_amount is not None:
            self.add_condition(f"{column} >= %s", min_amount)
        if max_amount is not None:
            self.add_condition(f"{column} <= %s", max_amount)
        return self

    def add_in_condition(
        self,
        column: str,
        values: Optional[List[Any]],
    ) -> "QueryBuilder":
        """
        Append a ``column IN (v1, v2, …)`` condition.

        Generates the correct number of %s placeholders automatically.
        If ``values`` is None or empty this method is a no-op, so it is
        safe to call unconditionally.

        Args:
            column: Column name, e.g. ``"t.transaction_type"``
            values: List of values.  None or [] → no condition added.

        Returns:
            self — for method chaining.

        Example::

            qb.add_in_condition("t.transaction_type", ["income", "expense"])
            # appends: AND t.transaction_type IN (%s, %s)
            # params:  ["income", "expense"]
        """
        if values:
            # Build exactly len(values) placeholders joined by commas
            placeholders = ", ".join(["%s"] * len(values))
            self.add_condition(f"{column} IN ({placeholders})", *values)
        return self

    def add_like_condition(
        self,
        column: str,
        search_term: Optional[str],
        match_type: str = "contains",
    ) -> "QueryBuilder":
        """
        Append a ``column LIKE %s`` condition with the appropriate wildcard.

        If ``search_term`` is None or empty this method is a no-op.

        Args:
            column:      Column name, e.g. ``"t.title"``
            search_term: The text to search for.  None → no condition.
            match_type:  Controls where the wildcard % is placed:
                           "contains"    → ``%term%``   (default)
                           "starts_with" → ``term%``
                           "ends_with"   → ``%term``
                           "exact"       → ``term``  (equivalent to =)

        Returns:
            self — for method chaining.

        Raises:
            ValidationError: If match_type is not one of the four options.
                             Changed from ValueError in v2 so the app layer
                             catches it alongside other validation errors.
        """
        if search_term:
            # Map each match_type to its wildcard pattern
            patterns = {
                "contains":    f"%{search_term}%",
                "starts_with": f"{search_term}%",
                "ends_with":   f"%{search_term}",
                "exact":       search_term,
            }
            if match_type not in patterns:
                # Raise ValidationError (not ValueError) so the app layer
                # catches it with the same except block as other bad inputs
                raise ValidationError(
                    f"Unknown match_type '{match_type}'. "
                    f"Must be one of: {', '.join(patterns.keys())}",
                    field="match_type",
                    value=match_type,
                )
            self.add_condition(f"{column} LIKE %s", patterns[match_type])
        return self

    def add_order_by(self, order_clause: str) -> "QueryBuilder":
        """
        Append an ``ORDER BY`` clause.

        Args:
            order_clause: The full ORDER BY expression, e.g.
                          ``"t.transaction_date DESC"`` or
                          ``"amount DESC, title ASC"``

        Returns:
            self — for method chaining.

        Note: Call this after all add_condition / add_*_range calls and
        before add_limit_offset, so the clause order is correct.
        """
        self.query += f" ORDER BY {order_clause}"
        return self

    def add_limit_offset(
        self,
        limit: Optional[int],
        offset: Optional[int] = None,
    ) -> "QueryBuilder":
        """
        Append ``LIMIT`` and optionally ``OFFSET`` clauses for pagination.

        Both parameters are optional — pass ``None`` to omit either clause.

        Args:
            limit:  Maximum rows to return.  None → no LIMIT clause.
            offset: Number of rows to skip.  None → no OFFSET clause.
                    Typically calculated by PaginationHelper.

        Returns:
            self — for method chaining.
        """
        if limit is not None:
            self.query += " LIMIT %s"
            self.params.append(limit)
        if offset is not None:
            self.query += " OFFSET %s"
            self.params.append(offset)
        return self

    def build(self) -> Tuple[str, List[Any]]:
        """
        Return the final SQL string and its bound parameters.

        Returns:
            ``(sql_string, params_list)`` — pass directly to
            ``cursor.execute(sql, params)``

        Example::

            sql, params = qb.build()
            cursor.execute(sql, tuple(params))
        """
        return self.query, self.params


# ===========================================================================
# 4. InputSanitizer
# ===========================================================================

class InputSanitizer:
    """
    Clean and validate raw user input before it reaches the database.

    All methods are static — no instantiation needed.  Import the class
    and call the methods directly::

        from core.utils import InputSanitizer

        clean = InputSanitizer.sanitize_string(raw_input, max_length=255)
        validated_type = InputSanitizer.validate_enum(
            tx_type, ["income", "expense"], field_name="transaction_type"
        )
    """

    @staticmethod
    def sanitize_string(
        value: Optional[str],
        max_length: Optional[int] = None,
        allow_empty: bool = True,
    ) -> Optional[str]:
        """
        Strip whitespace, enforce a maximum length, and handle empty strings.

        Args:
            value:       The raw string from user input or the database.
                         None is returned as-is.
            max_length:  If set, silently truncate the string to this length.
                         Useful for enforcing DB column limits before hitting
                         a MySQL "Data too long" error.
            allow_empty: If True (default), an empty string after stripping
                         is returned as "".
                         If False, an empty string is returned as None so
                         callers can treat it the same as a missing value.

        Returns:
            Cleaned string, "" (if allow_empty=True and input was blank),
            or None.
        """
        if value is None:
            return None
        # Remove leading/trailing whitespace before any other check
        cleaned = value.strip()
        # Treat a blank string according to the allow_empty flag
        if not cleaned:
            return None if not allow_empty else ""
        # Truncate silently rather than raising — the caller decides
        # whether to reject or accept a truncated value
        if max_length and len(cleaned) > max_length:
            cleaned = cleaned[:max_length]
        return cleaned

    @staticmethod
    def validate_enum(
        value: Optional[str],
        allowed_values: List[str],
        case_sensitive: bool = False,
        field_name: Optional[str] = None,
    ) -> Optional[str]:
        """
        Confirm that ``value`` is one of the items in ``allowed_values``.

        Comparison is case-insensitive by default so "Income", "INCOME",
        and "income" all pass when "income" is in the allowed list.

        Args:
            value:          The string to validate.  None is returned as-is
                            so optional enum fields don't need a None check
                            before calling this.
            allowed_values: The permitted values, e.g.
                            ``["income", "expense", "transfer"]``
            case_sensitive: Set True to require exact case match.
            field_name:     Passed into ValidationError so the error
                            message names the field, e.g. "transaction_type".
                            Changed from plain ValueError in v2.

        Returns:
            The validated string (lowercased if case_sensitive=False).

        Raises:
            ValidationError: If the value is not in allowed_values.
                             Carries field= and value= attributes so the
                             CLI layer can produce a precise error message.
        """
        if value is None:
            return None

        # Strip whitespace before comparing
        cleaned = value.strip()
        # Normalise case for the comparison only — the returned value
        # retains its original case if case_sensitive=True
        compare_cleaned = cleaned if case_sensitive else cleaned.lower()
        compare_allowed = (
            allowed_values if case_sensitive
            else [v.lower() for v in allowed_values]
        )

        if compare_cleaned not in compare_allowed:
            raise ValidationError(
                f"Invalid value '{value}'. "
                f"Must be one of: {', '.join(allowed_values)}",
                field=field_name,
                value=value,
            )
        return cleaned

    @staticmethod
    def parse_comma_separated(value: Optional[str]) -> List[str]:
        """
        Split a comma-separated string into a clean list of stripped tokens.

        Useful for CLI inputs where a user types multiple values in one
        field, e.g. ``"income, expense, transfer"``.

        Args:
            value: Raw comma-separated string.  None or "" → empty list.

        Returns:
            List of non-empty stripped strings.  Empty slots (from double
            commas) are discarded.

        Example::

            InputSanitizer.parse_comma_separated("income, expense ,transfer")
            # → ["income", "expense", "transfer"]

            InputSanitizer.parse_comma_separated(None)
            # → []
        """
        if not value:
            return []
        # Split, strip each piece, and drop any empty strings that result
        # from trailing commas or double commas
        return [item.strip() for item in value.split(",") if item.strip()]


# ===========================================================================
# 5. DateRangeValidator
# ===========================================================================

class DateRangeValidator:
    """
    Parse, normalise, and validate date range inputs from the CLI or API.

    All methods are static.  Usage::

        from core.utils import DateRangeValidator

        start, end = DateRangeValidator.validate_range("2025-01-01", "2025-06-30")
        start, end = DateRangeValidator.get_preset_range("this_month")
    """

    @staticmethod
    def parse_date(
        date_input: Union[str, date, datetime, None],
    ) -> Optional[date]:
        """
        Convert various date representations into a ``datetime.date`` object.

        Accepts:
          - None                 → returns None
          - datetime.date        → returns as-is
          - datetime.datetime    → returns .date() component only
          - str "YYYY-MM-DD"     → ISO format (preferred)
          - str "DD/MM/YYYY"     → day-first format
          - str "MM/DD/YYYY"     → month-first format

        Unrecognised strings return None rather than raising, so callers
        can decide how to handle the missing value.

        Args:
            date_input: The raw date value in any of the above forms.

        Returns:
            ``datetime.date`` object, or None if the input was None or
            could not be parsed.
        """
        if date_input is None:
            return None
        # Already a datetime — extract only the date part
        if isinstance(date_input, datetime):
            return date_input.date()
        # Already a date — return unchanged
        if isinstance(date_input, date):
            return date_input
        if isinstance(date_input, str):
            date_input = date_input.strip()
            # Try each format in order of preference
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
                try:
                    return datetime.strptime(date_input, fmt).date()
                except ValueError:
                    continue
        # Could not parse — return None so the caller can handle it
        return None

    @staticmethod
    def validate_range(
        start_date: Optional[Union[str, date]],
        end_date: Optional[Union[str, date]],
    ) -> Tuple[Optional[date], Optional[date]]:
        """
        Parse both ends of a date range and confirm they are in order.

        Both parameters are optional — passing None for either means
        "open-ended" (no lower or upper bound on the date filter).

        Args:
            start_date: Start of the range.  None → no lower bound.
            end_date:   End of the range.    None → no upper bound.

        Returns:
            ``(start_date, end_date)`` as ``datetime.date`` objects (or None).

        Raises:
            ValueError: If end_date is earlier than start_date.
                        Kept as ValueError (not ValidationError) to remain
                        compatible with the existing callers in features/search.py
                        which already catch ValueError for this case.
        """
        start = DateRangeValidator.parse_date(start_date)
        end   = DateRangeValidator.parse_date(end_date)
        if start and end and end < start:
            raise ValueError(
                f"End date ({end}) cannot be before start date ({start})"
            )
        return start, end

    @staticmethod
    def get_preset_range(preset: str) -> Tuple[date, date]:
        """
        Return a ``(start_date, end_date)`` pair for a named time preset.

        Presets are relative to today's date at call time, so
        ``"this_month"`` always returns the current month regardless of
        when you call it.

        Supported presets:
          today, yesterday, this_week, last_week, this_month,
          last_month, this_year, last_year,
          last_7_days, last_30_days, last_90_days

        Args:
            preset: One of the supported preset names (case-sensitive).

        Returns:
            ``(start_date, end_date)`` both as ``datetime.date`` objects.

        Raises:
            ValueError: If the preset name is not recognised.
        """
        from datetime import timedelta

        today = date.today()

        if preset == "today":
            return today, today

        elif preset == "yesterday":
            y = today - timedelta(days=1)
            return y, y

        elif preset == "this_week":
            # Monday of the current week → today
            return today - timedelta(days=today.weekday()), today

        elif preset == "last_week":
            # Monday → Sunday of the previous calendar week
            last_mon = today - timedelta(days=today.weekday() + 7)
            return last_mon, last_mon + timedelta(days=6)

        elif preset == "this_month":
            # First day of current month → today
            return today.replace(day=1), today

        elif preset == "last_month":
            # First day → last day of the previous calendar month
            first_this = today.replace(day=1)
            last_prev  = first_this - timedelta(days=1)
            return last_prev.replace(day=1), last_prev

        elif preset == "this_year":
            return today.replace(month=1, day=1), today

        elif preset == "last_year":
            y = today.year - 1
            return date(y, 1, 1), date(y, 12, 31)

        elif preset == "last_7_days":
            # 6 days ago through today = 7 days inclusive
            return today - timedelta(days=6), today

        elif preset == "last_30_days":
            return today - timedelta(days=29), today

        elif preset == "last_90_days":
            return today - timedelta(days=89), today

        else:
            raise ValueError(
                f"Unknown preset: '{preset}'. Valid options: today, yesterday, "
                "this_week, last_week, this_month, last_month, this_year, "
                "last_year, last_7_days, last_30_days, last_90_days"
            )


# ===========================================================================
# 6. AmountRangeValidator
# ===========================================================================

class AmountRangeValidator:
    """
    Parse and validate monetary amount range inputs.

    Uses ``Decimal`` internally for precise arithmetic — never float for
    money.

    All methods are static.  Usage::

        from core.utils import AmountRangeValidator

        min_val, max_val = AmountRangeValidator.validate_range("100", "5000")
        amount = AmountRangeValidator.parse_amount("1,250.99")
    """

    @staticmethod
    def parse_amount(
        amount_input: Union[str, int, float, Decimal, None],
    ) -> Optional[Decimal]:
        """
        Convert a raw amount value into a ``Decimal``.

        Accepts int, float, string, or Decimal input.  String input is
        stripped before parsing so ``" 1250.00 "`` works correctly.

        Args:
            amount_input: The raw value to convert.  None → returns None.

        Returns:
            ``Decimal`` representation of the amount, or None if the input
            was None or an unparseable string.

        Note: Returns None (rather than raising) for bad strings so the
        caller decides how to handle missing / invalid amounts.
        """
        if amount_input is None:
            return None
        # Decimal input — return unchanged to avoid any precision change
        if isinstance(amount_input, Decimal):
            return amount_input
        # int / float — convert via string to avoid float precision issues
        # e.g. Decimal(0.1) gives 0.1000000000000000055... but
        #      Decimal("0.1") gives exactly 0.1
        if isinstance(amount_input, (int, float)):
            return Decimal(str(amount_input))
        if isinstance(amount_input, str):
            try:
                return Decimal(amount_input.strip())
            except InvalidOperation:
                # Unparseable string (e.g. "abc") — return None
                return None
        return None

    @staticmethod
    def validate_range(
        min_amount: Optional[Union[str, float, Decimal]],
        max_amount: Optional[Union[str, float, Decimal]],
    ) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """
        Parse both bounds of an amount range and validate their relationship.

        Both parameters are optional — pass None for an open-ended range.

        Args:
            min_amount: Lower bound.  None → no lower bound.
            max_amount: Upper bound.  None → no upper bound.

        Returns:
            ``(min_amount, max_amount)`` both as ``Decimal`` (or None).

        Raises:
            ValueError: If either bound is negative, or if max < min.
        """
        min_val = AmountRangeValidator.parse_amount(min_amount)
        max_val = AmountRangeValidator.parse_amount(max_amount)

        # Amounts in this app are always non-negative
        if min_val is not None and min_val < 0:
            raise ValueError("Minimum amount cannot be negative")
        if max_val is not None and max_val < 0:
            raise ValueError("Maximum amount cannot be negative")
        # The range must be ordered correctly
        if min_val and max_val and max_val < min_val:
            raise ValueError(
                f"Maximum amount ({max_val}) cannot be less than "
                f"minimum amount ({min_val})"
            )
        return min_val, max_val


# ===========================================================================
# 7. ValidationPatterns
# ===========================================================================

class ValidationPatterns:
    """
    Domain-level validation constants and convenience validators.

    Centralises all the allowed values for the app's core enums so they
    are defined in one place rather than being repeated as inline lists
    across every model.

    Usage::

        from core.utils import ValidationPatterns

        # Validate a single value
        clean_type = ValidationPatterns.validate_transaction_type(raw_type)

        # Use the list directly in a model
        if tx_type not in ValidationPatterns.TRANSACTION_TYPES:
            raise TransactionValidationError(...)

        # Use in CLI prompt helpers
        ask_choice("Type", ValidationPatterns.TRANSACTION_TYPES)
    """

    # All valid transaction_type column values in the transactions table
    TRANSACTION_TYPES = [
        "income", "expense", "transfer",
        "debt_borrowed", "debt_repaid",
        "investment_deposit", "investment_withdraw",
    ]

    # All valid payment_method column values
    PAYMENT_METHODS = ["cash", "bank", "mobile_money", "credit_card", "other"]

    # All valid account_type column values in the accounts table
    ACCOUNT_TYPES = [
        "cash", "bank", "mobile_money", "credit",
        "savings", "investments", "other",
    ]

    # All valid frequency column values in recurring_transactions
    RECURRING_FREQUENCIES = ["daily", "weekly", "monthly", "yearly"]

    # Valid SQL ORDER BY directions used by QueryBuilder and search filters
    SORT_ORDERS = ["ASC", "DESC"]

    # All preset names accepted by DateRangeValidator.get_preset_range()
    DATE_PRESETS = [
        "today", "yesterday", "this_week", "last_week",
        "this_month", "last_month", "this_year", "last_year",
        "last_7_days", "last_30_days", "last_90_days",
    ]

    @staticmethod
    def validate_transaction_type(value: str) -> str:
        """
        Validate and return a transaction type string.

        Raises:
            ValidationError: With field="transaction_type" if invalid.
        """
        return InputSanitizer.validate_enum(
            value,
            ValidationPatterns.TRANSACTION_TYPES,
            field_name="transaction_type",
        )

    @staticmethod
    def validate_payment_method(value: str) -> str:
        """
        Validate and return a payment method string.

        Raises:
            ValidationError: With field="payment_method" if invalid.
        """
        return InputSanitizer.validate_enum(
            value,
            ValidationPatterns.PAYMENT_METHODS,
            field_name="payment_method",
        )

    @staticmethod
    def validate_sort_order(value: str) -> str:
        """
        Validate and return a sort order string ("ASC" or "DESC").

        Raises:
            ValidationError: With field="sort_order" if invalid.
        """
        return InputSanitizer.validate_enum(
            value,
            ValidationPatterns.SORT_ORDERS,
            field_name="sort_order",
        )


# ===========================================================================
# 8. PaginationHelper
# ===========================================================================

class PaginationHelper:
    """
    Calculate pagination metadata from a total record count and page request.

    Used by SearchService to convert a raw count and page/size into the
    offset and metadata dict that the query and the API response need.

    All methods are static.  Usage::

        from core.utils import PaginationHelper

        pagination = PaginationHelper.calculate_pagination(
            total_count=247, page=3, page_size=25
        )
        # → {'total_count': 247, 'page': 3, 'page_size': 25,
        #    'total_pages': 10, 'offset': 50,
        #    'has_next': True, 'has_prev': True}

        cursor.execute(sql + " LIMIT %s OFFSET %s",
                       (pagination["page_size"], pagination["offset"]))
    """

    @staticmethod
    def calculate_pagination(
        total_count: int,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        Return a dict with all the pagination values the UI and queries need.

        Args:
            total_count: Total number of records matching the query
                         (before pagination is applied).
            page:        Requested page number, 1-indexed.
                         Values < 1 are clamped to 1.
            page_size:   Number of records per page.
                         Values < 1 are clamped to 1.

        Returns:
            Dict with keys:
              total_count  — original count passed in
              page         — normalised page number
              page_size    — normalised page size
              total_pages  — ceiling division of count / page_size
              offset       — (page - 1) * page_size, for OFFSET clause
              has_next     — True if there is a page after this one
              has_prev     — True if there is a page before this one
        """
        # Clamp both values to at least 1 — negative or zero inputs
        # would produce nonsensical offsets and page counts
        page      = max(1, page)
        page_size = max(1, page_size)

        # Ceiling division: (247 + 24) // 25 = 10 (not 9)
        total_pages = (total_count + page_size - 1) // page_size
        # Rows to skip in the SQL OFFSET clause
        offset = (page - 1) * page_size

        return {
            "total_count": total_count,
            "page":        page,
            "page_size":   page_size,
            "total_pages": total_pages,
            "offset":      offset,
            "has_next":    page < total_pages,
            "has_prev":    page > 1,
        }


# ===========================================================================
# 9. FormatHelper
# ===========================================================================

class FormatHelper:
    """
    Format financial and date data for display in the CLI and reports.

    All methods are static.  Usage::

        from core.utils import FormatHelper

        FormatHelper.format_currency(1234.56)
        # → "KES 1,234.56"

        FormatHelper.format_date_range(date(2025,1,1), date(2025,6,30))
        # → "2025-01-01 to 2025-06-30"
    """

    @staticmethod
    def format_currency(
        amount: Union[float, Decimal],
        currency: str = "KES",
    ) -> str:
        """
        Format a numeric amount as a currency string.

        Args:
            amount:   The monetary value.  Supports float and Decimal.
            currency: The currency code prefix.  Defaults to "KES".

        Returns:
            String in the format ``"KES 1,234.56"`` — thousands-separated
            with exactly two decimal places.
        """
        return f"{currency} {amount:,.2f}"

    @staticmethod
    def format_date_range(
        start: Optional[date],
        end: Optional[date],
    ) -> str:
        """
        Format a date range as a human-readable string.

        Handles open-ended ranges (None on either side) gracefully so
        the output always makes sense in a report heading or filter summary.

        Args:
            start: Start date.  None → range has no lower bound.
            end:   End date.    None → range has no upper bound.

        Returns:
            "2025-01-01 to 2025-06-30"  — both ends provided
            "From 2025-01-01"           — no end date
            "Until 2025-06-30"          — no start date
            "All dates"                 — both None
        """
        if start and end:
            return f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"
        if start:
            return f"From {start.strftime('%Y-%m-%d')}"
        if end:
            return f"Until {end.strftime('%Y-%m-%d')}"
        return "All dates"