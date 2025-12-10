#Handles recurring tramsactions
from __future__ import annotations
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import mysql.connector

# Import from your other modules
from features.recurring import RecurringModel, RecurringError, RecurringNotFoundError, RecurringValidationError

class SchedulerError(Exception): 
    """Base exception for Scheduler-specific errors"""
    pass


class Scheduler:
    """
    Automated scheduler/coordinator for recurring transactions.
    
    This is a THIN wrapper that orchestrates recurring transaction execution.
    It does NOT duplicate logic - it delegates everything to RecurringModel.
    
    Architecture:
    - Scheduler = Coordinator & Runner (this class)
    - RecurringModel = Engine & Validator (handles all recurring logic)
    - TransactionModel = Transaction Creator (handles all transaction CRUD)
    
    Scheduler should NEVER:
    - Compute next run dates (RecurringModel does this)
    - Validate recurring rules (RecurringModel does this)
    - Create transactions directly (RecurringModel delegates to TransactionModel)
    - Update recurring records (RecurringModel does this)
    """
    def __init__(self, conn: mysql.connector.MySQLConnection, current_user: Dict[str, Any]):
        self.conn = conn
        self.current_user = current_user
        self.user_id = current_user.get("user_id")
        self.role = current_user.get("role")

        # Dependencies: delegate to specialized modules
        self.recurring = RecurringModel(conn, current_user)

# ===================================================================
    # PUBLIC API - Scheduler Operations (Thin Coordinator Layer)
    # ===================================================================

    def run_all_due_recurring(self) -> Dict[str, Any]:
        """
        Execute all due recurring transactions for the current user.
        
        This is the PRIMARY method for automated execution.
        Delegates entirely to RecurringModel.run_due()
        
        Returns:
            {
                "success": bool,
                "created_count": int,
                "transaction_ids": List[int],
                "message": str
            }
        """
        try:
            created_ids = self.recurring.run_due()
            return {
                "success": True,
                "created_count": len(created_ids),
                "transaction_ids": created_ids,
                "message": f"Successfully created {len(created_ids)} transactions from recurring rules"
            }
        except RecurringError as e:
            return {
                "success": False,
                "error": str(e),
                "created_count": 0,
                "transaction_ids": [],
                "message": f"Failed to execute recurring transactions: {str(e)}"
            }
        
    def preview_next_run(self, recurring_id: int) -> Dict[str, Any]:
        """
        Preview the next execution of a recurring transaction WITHOUT creating it.
        
        Args:
            recurring_id: ID of the recurring transaction to preview
            
        Returns:
            Preview details including next_due, amount, frequency, etc.
            
        Raises:
            SchedulerError: If preview fails
        """
        try:
            return self.recurring.preview_next_run(recurring_id)
        except (RecurringNotFoundError, RecurringValidationError) as e:
            raise SchedulerError(f"Preview failed: {str(e)}")

    def get_recurring_history(self, 
                            recurring_id: Optional[int] = None,
                            limit: Optional[int] = 50,
                            status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get execution history for recurring transactions.
        
        Args:
            recurring_id: Optional - filter by specific recurring transaction
            limit: Optional - maximum number of records to return
            status: Optional - filter by status ('generated', 'skipped', 'failed')
            
        Returns:
            List of history records from recurring_logs table
            
        Raises:
            SchedulerError: If history retrieval fails
        """
        try:
            return self.recurring.get_history(
                recurring_id=recurring_id, limit=limit,
                status=status
            ) 
        except RecurringError as e:
            raise SchedulerError(f"Failed to retrieve history: {str(e)}")
    
    def pause_recurring(self, recurring_id: int, pause_until: datetime) -> Dict[str, Any]:
        """
        Pause a recurring transaction until a specific date.
        
        Args:
            recurring_id: ID of recurring transaction to pause
            pause_until: Date to resume automatic execution
            
        Returns:
            Success response with updated recurring details
            
        Raises:
            SchedulerError: If pause operation fails
        """
        try:
            return self.recurring.update(
                recurring_id=recurring_id,
                pause_until=pause_until,
                is_active=0
            )
        except RecurringError as e:
            raise SchedulerError(f"Failed to pause recurring: {str(e)}")

    def resume_recurring(self, recurring_id: int) -> Dict[str, Any]:
        """
        Resume a paused recurring transaction.
        
        Args:
            recurring_id: ID of recurring transaction to resume
            
        Returns:
            Success response with updated recurring details
            
        Raises:
            SchedulerError: If resume operation fails
        """
        try:
            return self.recurring.update(
                recurring_id=recurring_id,
                pause_until=None,
                is_active=1
            )
        except RecurringError as e:
            raise SchedulerError(f"Failed to resume recurring: {str(e)}")

    def skip_next_occurrence(self, recurring_id: int) -> Dict[str, Any]:
        """
        Skip the next scheduled occurrence of a recurring transaction.
        The skip is consumed on the next run_due() execution.
        
        Args:
            recurring_id: ID of recurring transaction
            
        Returns:
            Success response with updated recurring details
            
        Raises:
            SchedulerError: If skip operation fails
        """
        try:
            return self.recurring.update(
                recurring_id=recurring_id,
                skip_next=1
            )
        except RecurringError as e:
            raise SchedulerError(f"Failed to skip next occurrence: {str(e)}")
        
    def set_one_time_override(self, recurring_id: int, override_amount: float) -> Dict[str, Any]:
        """
        Set a one-time amount override for the next occurrence.
        The override is consumed on the next run_due() execution.
        
        Args:
            recurring_id: ID of recurring transaction
            override_amount: Amount to use for next occurrence only
            
        Returns:
            Success response with updated recurring details
            
        Raises:
            SchedulerError: If override operation fails
        """
        try:
            return self.recurring.update(
                recurring_id=recurring_id,
                override_amount=override_amount
            )
        except RecurringError as e:
            raise SchedulerError(f"Failed to set override: {str(e)}")

    def get_upcoming_due(self, days_ahead: int = 7) -> List[Dict[str, Any]]:
        """
        Get all recurring transactions that will be due within the next N days.
        Useful for notification systems or dashboard previews.
        
        Args:
            days_ahead: Number of days to look ahead (default: 7)
            
        Returns:
            List of recurring transactions with upcoming due dates
        """
        try:
            # Calculate the cutoff date
            cutoff = datetime.now() + timedelta(days=days_ahead)
            # Use RecurringModel to fetch active recurring transactions
            all_recurring = self.recurring.list(frequency=None, trans_type=None) 
            # Filter for upcoming due dates
            upcoming = [
                r for r in all_recurring
                if r.get('is_active') == 1
                and r.get('next_due')
                and r.get('next_due') <= cutoff 
            ]
            return upcoming
            
        except RecurringError as e:
            raise SchedulerError(f"Failed to get upcoming due: {str(e)}")

    def deactivate_recurring(self, recurring_id: int) -> Dict[str, Any]:
        """
        Deactivate a recurring transaction (without deleting it).
        
        Args:
            recurring_id: ID of recurring transaction to deactivate
            
        Returns:
            Success response with updated recurring details
            
        Raises:
            SchedulerError: If deactivation fails
        """
        try:
            return self.recurring.update(
                recurring_id=recurring_id,
                is_active=0
            )
        except RecurringError as e:
            raise SchedulerError(f"Failed to deactivate recurring: {str(e)}")

    def activate_recurring(self, recurring_id: int) -> Dict[str, Any]:
        """
        Activate a deactivated recurring transaction.
        
        Args:
            recurring_id: ID of recurring transaction to activate
            
        Returns:
            Success response with updated recurring details
            
        Raises:
            SchedulerError: If activation fails
        """
        try:
            return self.recurring.update(
                recurring_id=recurring_id,
                is_active=1
            )
        except RecurringError as e:
            raise SchedulerError(f"Failed to activate recurring: {str(e)}")

    # ===================================================================
    # OPTIONAL: Cron-style Runner (for external scheduler systems)
    # ===================================================================

    def run_scheduler_job(self) -> Dict[str, Any]:
        """
        Main entry point for external cron jobs or task schedulers.
        
        This method is designed to be called by:
        - APScheduler
        - Celery Beat
        - Cron jobs
        - Cloud scheduler (AWS EventBridge, GCP Cloud Scheduler, etc.)
        
        Returns comprehensive execution report.
        
        Usage example with APScheduler:
            ```python
            from apscheduler.schedulers.background import BackgroundScheduler
            
            scheduler = BackgroundScheduler()
            scheduler.add_job(
                func=lambda: Scheduler(conn, admin_user).run_scheduler_job(),
                trigger="interval",
                hours=1,
                id="recurring_transaction_runner"
            )
            scheduler.start()
            ```
        """
        start_time = datetime.now()
        
        try:
            result = self.run_all_due_recurring()
            
            return {
                "job_status": "completed",
                "start_time": start_time.isoformat(),
                "end_time": datetime.now().isoformat(),
                "user_id": self.user_id,
                "result": result
            }
            
        except Exception as e:
            return {
                "job_status": "failed",
                "start_time": start_time.isoformat(),
                "end_time": datetime.now().isoformat(),
                "user_id": self.user_id,
                "error": str(e),
                "result": {
                    "success": False,
                    "created_count": 0,
                    "transaction_ids": [],
                    "message": f"Scheduler job failed: {str(e)}"
                }
            }

    def get_scheduler_status(self) -> Dict[str, Any]:
        """
        Get current status of all recurring transactions for monitoring.
        
        Returns:
            Summary statistics including:
            - Total active recurring transactions
            - Total paused
            - Total overdue
            - Next upcoming due dates
        """
        try:
            all_recurring = self.recurring.list(frequency=None, trans_type=None)
            
            now = datetime.now()
            
            active_count = sum(1 for r in all_recurring if r.get('is_active') == 1)
            paused_count = sum(1 for r in all_recurring if r.get('is_active') == 0)
            overdue_count = sum(1 for r in all_recurring 
                              if r.get('is_active') == 1 
                              and r.get('next_due')
                              and r['next_due'] < now)
            
            return {
                "total_active": active_count,
                "total_paused": paused_count,
                "total_overdue": overdue_count,
                "timestamp": now.isoformat(),
                "user_id": self.user_id
            }
            
        except RecurringError as e:
            raise SchedulerError(f"Failed to get scheduler status: {str(e)}")
