# FinTrack 💰

A personal finance tracker that runs entirely in your terminal. Track income, expenses, accounts, goals, and recurring bills — with PDF/Excel exports and smart spending insights.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![MySQL](https://img.shields.io/badge/MySQL-8.0%2B-orange)
![License](https://img.shields.io/badge/license-MIT-green)

---

## What it does

| Area | Features |
|---|---|
| **Transactions** | Income, expense, transfer, debt, investments — all 7 types |
| **Accounts** | Cash, bank, mobile money, credit, savings — balance auto-updates on every transaction |
| **Categories** | Hierarchical tree (parent → children), full CRUD |
| **Goals** | Saving, spending, and budget-cap goals with live progress from real transactions |
| **Recurring** | Scheduled transactions (daily/weekly/monthly/yearly) with pause, skip, and override |
| **Analytics** | Income vs expenses, top categories, monthly trends, daily spending |
| **Exports** | CSV, PDF, and Excel (.xlsx) — flat, grouped by category/month, or full monthly reports |
| **Charts** | 4 Matplotlib charts: monthly trends, category donut, daily heatmap, net worth |
| **Insights** | 11 smart alerts — spending spikes, income drops, budget cap warnings, large transactions |
| **Dashboard** | Rich terminal dashboard — net worth, cash flow, upcoming bills, recent transactions |
| **Scheduler** | Windows Task Scheduler integration — runs recurring transactions automatically |

---

## Requirements

- Python 3.10+ (not needed for the standalone exe)
- MySQL 8.0+
- Windows 9/10/11, Linux, or macOS

---

## Installation

### Method 1 — Standalone Executable (Windows, no Python required)

Download the latest release from the [Releases](../../releases) page, unzip it, and:

```
1. Open the FinTrack/ folder
2. Copy config/config.ini.template → config/config.ini
3. Fill in your MySQL credentials (see config.ini section below)
4. Double-click FinTrack.exe
```

That's it. No Python, no pip, no setup.

---

### Method 2 — pip install

```bash
pip install budget-tracker
```

Or from the wheel file directly:

```bash
pip install budget_tracker-1.0.0-py3-none-any.whl
```

Then create your config file and run:

```bash
# Create the config directory
mkdir config

# Copy the template (find it in the repo or the wheel's data files)
cp config/config.ini.template config/config.ini

# Edit config.ini with your MySQL credentials, then:
fintrack
# or
python -m budget_tracker
```

---

### Method 3 — Clone and run (development)

```bash
# 1. Clone
git clone https://github.com/yourname/budget-tracker.git
cd budget-tracker

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up the database
# Create a MySQL database, then import the schema:
mysql -u root -p your_database < data/seeds.sql

# 5. Create your config file
cp config/config.ini.template config/config.ini
# Edit config/config.ini with your credentials

# 6. Run
python main.py
```

---

## Configuration

The app reads `config/config.ini` to connect to MySQL. Create it from the template:

```ini
[mysql]
host     = localhost
user     = your_mysql_username
password = your_mysql_password
database = your_database_name
port     = 3306
```

> **Never commit `config.ini`** — it contains your DB credentials. It is already in `.gitignore`.

---

## First run

On first run, the registration screen appears. The **first registered user automatically becomes admin**. All users after that are regular users unless an admin promotes them.

```
1. Choose "Register"
2. Enter username, password, security answer
3. Login with those credentials
4. You're in — the main menu appears
```

---

## Project structure

```
fintrack/
├── fintrack/
│   ├── main.py              # Unified entry point (CLI router)
│   ├── app.py               # Main application logic
│   ├── core/                # Database, scheduler, utilities
│   ├── models/              # Data models
│   ├── features/            # Business features
│   ├── cron/                # Cron runner
│   ├── setup/               # DB + scheduler setup
│   └── data/                # SQL schema & seeds
│
├── config/                  # User config (NOT committed)
├── reports/                 # Exports + logs
├── scripts/                 # Build tools only
├── packaging/               # PyInstaller spec
├── tests/                   # Test suite
├── pyproject.toml
└── README.md
---

## Automatic recurring transactions

To have FinTrack run due recurring transactions automatically every hour on Windows:

```bat
# Run once as Administrator:
scripts\setup_task_scheduler.bat
```

This registers a Windows Task Scheduler job. To trigger it manually any time:

```bat
scripts\run_cron.bat
```

---

## Building from source

To build the standalone exe or the pip wheel yourself:

```bash
chmod +x scripts/build.sh

./scripts/build.sh              # builds both wheel and exe
./scripts/build.sh --exe-only   # exe only
./scripts/build.sh --wheel-only # wheel only
./scripts/build.sh --clean      # wipe everything and rebuild
```

Output:
- `dist/FinTrack/FinTrack.exe` — standalone executable
- `dist/budget_tracker-1.0.0-py3-none-any.whl` — pip-installable wheel

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| mysql-connector-python | ≥8.3.0 | MySQL driver |
| rich | ≥13.0.0 | Terminal UI |
| matplotlib | ≥3.7.0 | Charts |
| numpy | ≥1.24.0 | Chart calculations |
| pandas | ≥2.0.0 | CSV/Excel export |
| openpyxl | ≥3.1.0 | Excel (.xlsx) export |
| reportlab | ≥4.0.0 | PDF export |
| bcrypt | ≥4.0.0 | Password hashing |

---

## License

MIT — see [LICENSE](LICENSE)