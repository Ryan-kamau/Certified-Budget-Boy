#!/usr/bin/env bash
# =============================================================================
# scripts/build.sh
# -----------------------------------------------------------------------------
# FinTrack — One-command build script
#
# What it does (in order)
# -----------------------
#   1. Validates Python version (>= 3.9)
#   2. Creates / reuses a virtual environment at .venv/
#   3. Installs / upgrades all dependencies
#   4. Generates a canonical requirements.txt (if one doesn't exist)
#   5. Builds a Python wheel (dist/*.whl) with setuptools
#   6. Runs PyInstaller with budget_tracker.spec to produce the exe
#   7. Prints the output paths and bundle size
#
# Usage
# -----
#   ./scripts/build.sh                     Build wheel + exe (default)
#   ./scripts/build.sh --exe-only          Skip wheel, build exe only
#   ./scripts/build.sh --wheel-only        Skip exe, build wheel only
#   ./scripts/build.sh --clean             Delete build/ dist/ .venv/, then build
#   ./scripts/build.sh --clean --exe-only  Clean + exe only
#   ./scripts/build.sh --dry-run           Show what would happen; nothing runs
#   ./scripts/build.sh --verbose           Show all pip/PyInstaller output
#   ./scripts/build.sh --help              Print this help text
#
# Flags can be combined:
#   ./scripts/build.sh --clean --exe-only --verbose
#
# Output
# ------
#   dist/<APP_NAME>/         — executable directory (--onedir, default)
#   dist/<APP_NAME>.exe      — single-file exe (set ONEFILE=True in spec)
#   dist/<APP_NAME>-*.whl    — installable Python wheel
#
# Requirements
# ------------
#   • Python 3.9+ on PATH  (or set PYTHON env variable)
#   • Internet access for pip install (first run only)
#   • Windows: run from Git Bash, WSL, or any POSIX-compatible shell
#     (PowerShell users: use build.ps1 instead — see comments at EOF)
# =============================================================================

set -euo pipefail   # exit on error, unset variable, or pipe failure

# ─── Colour helpers ──────────────────────────────────────────────────────────
if [ -t 1 ]; then   # only use colour if stdout is a terminal
    C_RESET='\033[0m'
    C_BOLD='\033[1m'
    C_GREEN='\033[0;32m'
    C_YELLOW='\033[0;33m'
    C_CYAN='\033[0;36m'
    C_RED='\033[0;31m'
    C_DIM='\033[2m'
else
    C_RESET='' C_BOLD='' C_GREEN='' C_YELLOW='' C_CYAN='' C_RED='' C_DIM=''
fi

info()    { echo -e "${C_CYAN}${C_BOLD}[INFO]${C_RESET}  $*"; }
success() { echo -e "${C_GREEN}${C_BOLD}[OK]${C_RESET}    $*"; }
warn()    { echo -e "${C_YELLOW}${C_BOLD}[WARN]${C_RESET}  $*"; }
error()   { echo -e "${C_RED}${C_BOLD}[ERROR]${C_RESET} $*" >&2; }
step()    { echo -e "\n${C_BOLD}══ $* ${C_DIM}$(printf '═%.0s' {1..50} | head -c $((54 - ${#1})))${C_RESET}"; }
dim()     { echo -e "${C_DIM}$*${C_RESET}"; }


# =============================================================================
# CONFIGURATION — edit these to match your project
# =============================================================================

APP_NAME="FinTrack"
APP_VERSION="1.0.0"
ENTRY_POINT="fintrack/main.py"
SPEC_FILE="packaging/budget_tracker.spec"
VENV_DIR=".venv"
MIN_PYTHON="3.10"

# Python interpreter to use (override with: PYTHON=/path/to/python3.11 ./build.sh)
PYTHON="${PYTHON:-}"

# pip install flags
PIP_QUIET=""        # set to "--quiet" if you want less pip noise by default

# PyInstaller flags (appended to the pyinstaller command)
PYINSTALLER_FLAGS=""   # e.g. "--log-level WARN"

# Runtime dependencies — these are installed into the venv.
# Pin versions to guarantee reproducible builds.
DEPENDENCIES=(
    # Core DB driver
    "mysql-connector-python>=8.3.0"

    # CLI rendering
    "rich>=13.0.0"

    # Data / reporting
    "pandas>=2.0.0"
    "numpy>=1.24.0"
    "openpyxl>=3.1.0"
    "reportlab>=4.0.0"

    # Charts
    "matplotlib>=3.7.0"

    # Security
    "bcrypt>=4.0.0"

    # Utilities
    "pyparsing>=3.0.0"
    "cycler>=0.11.0"

    # Build toolchain
    "pyinstaller>=6.0.0"
    "setuptools>=68.0.0"
    "wheel>=0.41.0"
    "build>=1.0.0"
)


# =============================================================================
# ARGUMENT PARSING
# =============================================================================

DO_WHEEL=true
DO_EXE=true
DO_CLEAN=false
DRY_RUN=false
VERBOSE=false

usage() {
    grep '^#' "$0" | grep -E '^\# (Usage|    \.|  •)' | sed 's/^# //' || true
    cat <<EOF

Usage:  ./scripts/build.sh [OPTIONS]

Options:
  --exe-only      Build only the PyInstaller executable
  --wheel-only    Build only the Python wheel (.whl)
  --clean         Remove build/, dist/, and .venv/ before building
  --dry-run       Print steps without executing them
  --verbose       Show full pip and PyInstaller output
  --help          Show this help message

Examples:
  ./scripts/build.sh
  ./scripts/build.sh --clean --exe-only
  ./scripts/build.sh --dry-run --verbose
EOF
}

for arg in "$@"; do
    case "$arg" in
        --exe-only)   DO_WHEEL=false ;;
        --wheel-only) DO_EXE=false   ;;
        --clean)      DO_CLEAN=true  ;;
        --dry-run)    DRY_RUN=true   ;;
        --verbose)    VERBOSE=true; PIP_QUIET=""  ;;
        --help|-h)    usage; exit 0  ;;
        *)
            error "Unknown flag: $arg"
            usage
            exit 1
            ;;
    esac
done

# In verbose mode, PyInstaller gets more output too
if $VERBOSE; then
    PYINSTALLER_FLAGS="$PYINSTALLER_FLAGS --log-level INFO"
fi

# Dry-run wrapper — prints the command instead of running it
run() {
    if $DRY_RUN; then
        dim "  [dry-run] $*"
    else
        "$@"
    fi
}

# Like run() but only hides output when not in verbose mode
run_quiet() {
    if $DRY_RUN; then
        dim "  [dry-run] $*"
    elif $VERBOSE; then
        "$@"
    else
        "$@" > /dev/null 2>&1
    fi
}


# =============================================================================
# STEP 0 — Header
# =============================================================================

echo ""
echo -e "${C_BOLD}${C_CYAN}╔══════════════════════════════════════════════════════╗${C_RESET}"
echo -e "${C_BOLD}${C_CYAN}║  FinTrack Build Script  v${APP_VERSION}$(printf ' %.0s' {1..$(( 28 - ${#APP_VERSION} ))})║${C_RESET}"
echo -e "${C_BOLD}${C_CYAN}╚══════════════════════════════════════════════════════╝${C_RESET}"
echo ""

dim  "  App name   : $APP_NAME"
dim  "  Entry point: $ENTRY_POINT"
dim  "  Spec file  : $SPEC_FILE"
dim  "  Venv dir   : $VENV_DIR"
dim  "  Build wheel: $DO_WHEEL"
dim  "  Build exe  : $DO_EXE"
dim  "  Clean first: $DO_CLEAN"
dim  "  Dry run    : $DRY_RUN"
dim  "  Verbose    : $VERBOSE"
echo ""

# Make sure we're in the project root (one level up from scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"
dim  "  Project root: $PROJECT_ROOT"
echo ""


# =============================================================================
# STEP 1 — Find Python
# =============================================================================
step "Step 1 — Locating Python"

find_python() {
    # Priority: explicit PYTHON env → python3 → python
    for candidate in "$PYTHON" python3 python; do
        [[ -z "$candidate" ]] && continue
        if command -v "$candidate" &>/dev/null; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

PYTHON_BIN="$(find_python)" || {
    error "Python not found. Install Python $MIN_PYTHON+ or set the PYTHON env variable."
    exit 1
}

PY_VERSION="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
PY_FULL="$("$PYTHON_BIN" --version 2>&1)"

# Version check
IFS='.' read -r -a PY_PARTS <<< "$PY_VERSION"
IFS='.' read -r -a MIN_PARTS <<< "$MIN_PYTHON"

if (( PY_PARTS[0] < MIN_PARTS[0] )) || \
   (( PY_PARTS[0] == MIN_PARTS[0] && PY_PARTS[1] < MIN_PARTS[1] )); then
    error "Python $PY_VERSION found, but $MIN_PYTHON+ required."
    error "Currently using: $("$PYTHON_BIN" -c 'import sys; print(sys.executable)')"
    exit 1
fi

success "Found $PY_FULL  →  $(command -v "$PYTHON_BIN")"


# =============================================================================
# STEP 2 — Clean (optional)
# =============================================================================
step "Step 2 — Cleaning old artifacts"

if $DO_CLEAN; then
    for dir in build dist "$VENV_DIR" "*.egg-info" __pycache__; do
        if $DRY_RUN; then
            dim "  [dry-run] rm -rf $dir"
        else
            find . -name "$dir" -maxdepth 3 -exec rm -rf {} + 2>/dev/null || true
        fi
    done
    # Also clear PyInstaller's hook cache
    run rm -rf "${TMPDIR:-/tmp}"/pyinstaller* 2>/dev/null || true
    success "Cleaned build/, dist/, $VENV_DIR/"
else
    dim "  Skipped (--clean not set)"
fi


# =============================================================================
# STEP 3 — Virtual environment
# =============================================================================
step "Step 3 — Virtual environment ($VENV_DIR/)"

VENV_PYTHON="$PROJECT_ROOT/$VENV_DIR/bin/python"
VENV_PIP="$PROJECT_ROOT/$VENV_DIR/bin/pip"

# Windows compatibility: pip/python may be in Scripts/ not bin/
if [[ ! -f "$VENV_PYTHON" ]]; then
    VENV_PYTHON_WIN="$PROJECT_ROOT/$VENV_DIR/Scripts/python.exe"
    VENV_PIP_WIN="$PROJECT_ROOT/$VENV_DIR/Scripts/pip.exe"
    if [[ -f "$VENV_PYTHON_WIN" ]]; then
        VENV_PYTHON="$VENV_PYTHON_WIN"
        VENV_PIP="$VENV_PIP_WIN"
    fi
fi

if [[ ! -f "$VENV_PYTHON" ]]; then
    info "Creating virtual environment …"
    run "$PYTHON_BIN" -m venv "$VENV_DIR"

    # Re-check after creation (handles Windows)
    VENV_PYTHON="$PROJECT_ROOT/$VENV_DIR/bin/python"
    if [[ ! -f "$VENV_PYTHON" ]]; then
        VENV_PYTHON="$PROJECT_ROOT/$VENV_DIR/Scripts/python.exe"
    fi
    success "Created $VENV_DIR/"
else
    success "Reusing existing $VENV_DIR/"
fi

# Confirm venv python version
VENV_PY_VER="$($DRY_RUN && echo "$PY_VERSION" || "$VENV_PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
dim "  venv Python: $VENV_PY_VER"


# =============================================================================
# STEP 4 — Install / upgrade dependencies
# =============================================================================
step "Step 4 — Installing dependencies"

info "Upgrading pip, setuptools, wheel …"
run_quiet "$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel $PIP_QUIET

info "Installing project dependencies …"
if [[ -f "requirements.txt" ]]; then
    dim "  Using existing requirements.txt"
    run_quiet "$VENV_PYTHON" -m pip install -r requirements.txt $PIP_QUIET
else
    dim "  No requirements.txt found — installing from build script definition"
    run_quiet "$VENV_PYTHON" -m pip install "${DEPENDENCIES[@]}" $PIP_QUIET
fi

# Always ensure the build toolchain is present
run_quiet "$VENV_PYTHON" -m pip install pyinstaller build $PIP_QUIET

success "Dependencies installed"


# =============================================================================
# STEP 5 — Generate / update requirements.txt
# =============================================================================
step "Step 5 — Generating requirements.txt"

REQUIREMENTS_FILE="requirements.txt"

if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
    info "Generating clean requirements.txt …"
    printf "%s\n" "${DEPENDENCIES[@]}" > "$REQUIREMENTS_FILE"
    success "Created clean requirements.txt"
fi


# =============================================================================
# STEP 6 — Generate setup.cfg / pyproject.toml if missing
# =============================================================================
step "Step 6 — Verifying package configuration"

# Generate a minimal pyproject.toml if neither it nor setup.cfg exists.
# This is needed for `python -m build` to produce the wheel.
if [[ ! -f "pyproject.toml" ]] && [[ ! -f "setup.cfg" ]] && [[ ! -f "setup.py" ]]; then
    info "No pyproject.toml / setup.cfg found — generating minimal pyproject.toml …"

    if ! $DRY_RUN; then
        cat > pyproject.toml << TOML
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "fintrack"
version = "${APP_VERSION}"
description = "FinTrack — Personal Finance Tracker"
requires-python = ">=${MIN_PYTHON}"
readme = "README.md"

[tool.setuptools.packages.find]
where = ["."]
include = ["fintrack*"]

[tool.setuptools.package-data]
fintrack = ["config/*.template.ini"]

[tool.setuptools.data-files]
"scripts" = ["scripts/*.bat"]
TOML
    fi
    success "Generated pyproject.toml"
else
    success "Package configuration found"
fi


# =============================================================================
# STEP 7 — Build Python wheel
# =============================================================================
step "Step 7 — Building Python wheel"

if $DO_WHEEL; then
    info "Running: python -m build --wheel"
    if $DRY_RUN; then
        dim "  [dry-run] $VENV_PYTHON -m build --wheel --outdir dist/"
    elif $VERBOSE; then
        "$VENV_PYTHON" -m build --wheel --outdir dist/
    else
        "$VENV_PYTHON" -m build --wheel --outdir dist/ 2>&1 | tail -5
    fi

    WHEEL_FILE="$(ls dist/*.whl 2>/dev/null | head -1)"
    if [[ -n "$WHEEL_FILE" ]] && [[ -f "$WHEEL_FILE" ]]; then
        WHEEL_SIZE="$(du -sh "$WHEEL_FILE" | cut -f1)"
        success "Wheel built: $WHEEL_FILE  ($WHEEL_SIZE)"
    elif ! $DRY_RUN; then
        warn "Wheel file not found after build — check above for errors"
    fi
else
    dim "  Skipped (--wheel-only not active or --exe-only was set)"
fi

#step "Preparing runtime folders"

run mkdir -p dist/$APP_NAME/config
run mkdir -p dist/$APP_NAME/reports/logs


# =============================================================================
# STEP 8 — Build PyInstaller executable
# =============================================================================
step "Step 8 — Building executable with PyInstaller"

if $DO_EXE; then
    # Verify the spec file exists
    if [[ ! -f "$SPEC_FILE" ]]; then
        error "Spec file not found: $SPEC_FILE"
        error "Expected it at: $PROJECT_ROOT/$SPEC_FILE"
        exit 1
    fi

    # Create the PyInstaller hooks directory if it doesn't exist
    mkdir -p scripts/pyinstaller_hooks

    # Create a minimal __init__.py for each project package if missing
    # (PyInstaller needs them to correctly resolve packages)
    for pkg_dir in core models features; do
        INIT_FILE="$pkg_dir/__init__.py"
        if [[ ! -f "$INIT_FILE" ]]; then
            dim "  Creating missing $INIT_FILE"
            run touch "$INIT_FILE"
        fi
    done

    info "Running PyInstaller …"
    info "Spec: $SPEC_FILE"

    PYINSTALLER_CMD=(
        "$VENV_PYTHON" -m PyInstaller
        "$SPEC_FILE"
        --collect-all fintrack #All submodules rebundled
        --noconfirm          # overwrite dist/ without asking
        --clean              # always start from a clean build cache
        $PYINSTALLER_FLAGS
    )

    if $DRY_RUN; then
        dim "  [dry-run] ${PYINSTALLER_CMD[*]}"
    elif $VERBOSE; then
        "${PYINSTALLER_CMD[@]}"
    else
        # PyInstaller is chatty — show a spinner and only print errors
        "${PYINSTALLER_CMD[@]}" 2>&1 | grep -E "^(ERROR|WARNING|INFO: Building)" || true
        echo ""   # newline after grep output
    fi

    # ── Report output ─────────────────────────────────────────────────────────
    EXE_DIR="dist/$APP_NAME"
    EXE_FILE_DIR="$EXE_DIR/$APP_NAME"       # --onedir
    EXE_FILE_ONE="dist/$APP_NAME.exe"       # --onefile

    if $DRY_RUN; then
        dim "  [dry-run] Would produce: dist/$APP_NAME/"
    elif [[ -d "$EXE_DIR" ]]; then
        EXE_SIZE="$(du -sh "$EXE_DIR" | cut -f1)"
        echo ""
        echo -e "${C_GREEN}${C_BOLD}╔══════════════════════════════════════════════════════╗${C_RESET}"
        echo -e "${C_GREEN}${C_BOLD}║  Executable built successfully!                      ║${C_RESET}"
        echo -e "${C_GREEN}${C_BOLD}╚══════════════════════════════════════════════════════╝${C_RESET}"
        echo ""
        info "Output directory : $EXE_DIR/    ($EXE_SIZE)"
        info "Launch with      : $EXE_DIR/$APP_NAME.exe"
        echo ""
        dim  "  To distribute: zip the entire dist/$APP_NAME/ folder."
        dim  "  Recipient needs no Python installed — just unzip and run."
        echo ""
    elif [[ -f "$EXE_FILE_ONE" ]]; then
        EXE_SIZE="$(du -sh "$EXE_FILE_ONE" | cut -f1)"
        echo ""
        success "Single-file exe  : $EXE_FILE_ONE  ($EXE_SIZE)"
    else
        warn "PyInstaller finished but the expected output was not found."
        warn "Check the output above for errors."
        exit 1
    fi
else
    dim "  Skipped (--wheel-only was set)"
fi


# =============================================================================
# STEP 9 — Final summary
# =============================================================================
step "Build complete"

# Copy Windows scheduler script
if [[ -f "scripts/setup_task_scheduler.bat" ]]; then
    run cp "scripts/setup_task_scheduler.bat" "dist/$APP_NAME/"
fi

echo ""
if $DO_WHEEL && [[ -n "${WHEEL_FILE:-}" ]]; then
    success "Wheel  → ${WHEEL_FILE}"
fi
if $DO_EXE && [[ -d "dist/$APP_NAME" ]] && ! $DRY_RUN; then
    success "Exe    → dist/$APP_NAME/$APP_NAME.exe"
fi
echo ""
dim  "  Build log: build/$APP_NAME/warn-$APP_NAME.txt"
dim  "  Run log  : reports/logs/cron.log  (after first execution)"
echo ""

# =============================================================================
# EOF
# =============================================================================
# PowerShell equivalent (paste into your terminal if you prefer PS over bash):
#
#   # Activate venv
#   .\.venv\Scripts\Activate.ps1
#
#   # Install deps
#   pip install -r requirements.txt
#   pip install pyinstaller build
#
#   # Build exe
#   pyinstaller budget_tracker.spec --noconfirm --clean
#
#   # Build wheel
#   python -m build --wheel --outdir dist/
# =============================================================================