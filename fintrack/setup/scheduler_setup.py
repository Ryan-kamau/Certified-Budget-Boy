# fintrack/setup/scheduler_setup.py

import os
import sys
import subprocess
import ctypes

TASK_NAME = "FinTrack_CronRunner"


def is_admin():
    """Check if script is running with admin privileges."""
    try:
        return os.getuid() == 0
    except AttributeError:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0


def get_exe_path():
    """Get path to running executable (works for PyInstaller)."""
    if getattr(sys, 'frozen', False):
        return sys.executable
    else:
        # Dev mode fallback
        return os.path.abspath(sys.argv[0])


def create_task():
    exe_path = get_exe_path()

    command = f'"{exe_path}" --cron'

    print(f"[INFO] Creating scheduled task...")
    print(f"[INFO] Executable: {exe_path}")
    print(f"[INFO] Command: {command}")

    # Delete existing task (if exists)
    subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # Create task (every 8 hours)
    result = subprocess.run(
        [
            "schtasks",
            "/Create",
            "/TN", TASK_NAME,
            "/SC", "HOURLY",
            "/MO", "8",
            "/TR", command,
            "/RL", "HIGHEST",
            "/F"
        ],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("[ERROR] Failed to create scheduled task.")
        print(result.stderr)
        sys.exit(1)

    print("[OK] Scheduled task created successfully!")

    configure_retry()


def configure_retry():
    """Add retry-on-failure using XML patch."""
    xml_path = os.path.join(os.getenv("TEMP"), "fintrack_task.xml")

    # Export task XML
    subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME, "/XML", "ONE"],
        stdout=open(xml_path, "w"),
        stderr=subprocess.DEVNULL
    )

    # Modify XML
    with open(xml_path, "r", encoding="utf-8") as f:
        xml = f.read()

    if "<RestartOnFailure>" not in xml:
        xml = xml.replace(
            "</Settings>",
            """
<RestartOnFailure>
    <Interval>PT5M</Interval>
    <Count>3</Count>
</RestartOnFailure>
</Settings>
"""
        )

    with open(xml_path, "w", encoding="utf-8") as f:
        f.write(xml)

    # Re-import
    subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    subprocess.run(
        ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", xml_path, "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    try:
        os.remove(xml_path)
    except Exception:
        pass

    print("[OK] Retry policy applied (3 retries, 5 min interval)")


def remove_task():
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print("[OK] Scheduled task removed.")
    else:
        print("[WARN] Task may not exist.")


def main():
    print("\n=== FinTrack Scheduler Setup ===\n")

    if not is_admin():
        print("[ERROR] Please run as Administrator.")
        print("Right-click → Run as administrator")
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit()

        create_task()