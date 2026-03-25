# -*- mode: python ; coding: utf-8 -*-
# =============================================================================
# budget_tracker.spec
# -----------------------------------------------------------------------------
# PyInstaller configuration for FinTrack — Personal Finance Tracker
#
# Produces:
#   dist/FinTrack/FinTrack.exe   (Windows, --onedir)   ← default
#   dist/FinTrack.exe            (Windows, --onefile)  ← set ONEFILE=True below
#
# Build:
#   pyinstaller budget_tracker.spec
#
# Or via the build script (recommended):
#   ./scripts/build.sh --exe-only
#
# Why every section exists
# ------------------------
# hiddenimports  : PyInstaller traces static imports at analysis time.
#                  It cannot see: dynamic imports, plugin discovery,
#                  conditional imports guarded by try/except, or any
#                  module that another module loads by string name.
#                  Every package listed here falls into one of those
#                  categories for this codebase.
#
# collect_all    : For packages that (a) have non-Python data files
#                  embedded in their wheel (fonts, colormaps, locale
#                  files, XML schemas) AND (b) have so many submodules
#                  that listing them manually would be fragile.
#                  collect_all() == collect_submodules() +
#                                   collect_data_files() +
#                                   collect_dynamic_libs()
#
# datas          : Project-level asset folders that are not Python
#                  packages but are referenced at runtime via
#                  relative paths (config/, reports/templates/).
#
# excludes       : Modules that would be pulled in transitively but
#                  are never used.  Removing them shrinks the exe.
#
# runtime_hooks  : Small scripts that run inside the frozen process
#                  BEFORE main.py starts.  Used here to force
#                  matplotlib to use the correct backend for a
#                  frozen Windows GUI-less console app.
# =============================================================================

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
    collect_data_files,
    collect_dynamic_libs,
)

# ── Toggle: True = single .exe  |  False = directory (faster cold start) ────
ONEFILE = False

# ── Application metadata ─────────────────────────────────────────────────────
APP_NAME    = "FinTrack"
APP_VERSION = "1.0.0"
ENTRY_POINT = "main.py"

# ── Paths ─────────────────────────────────────────────────────────────────────
# When spec is run with `pyinstaller budget_tracker.spec` from the project
# root, SPECPATH is the project root.  We use it as the anchor for all
# relative paths so the build works regardless of CWD.
PROJ_ROOT = Path(SPECPATH)

# =============================================================================
# STEP 1 — collect_all for heavy packages
#   Returns (binaries, datas, hiddenimports) tuples.
# =============================================================================

_mpl_b,  _mpl_d,  _mpl_h  = collect_all('matplotlib')
_np_b,   _np_d,   _np_h   = collect_all('numpy')
_pd_b,   _pd_d,   _pd_h   = collect_all('pandas')
_rl_b,   _rl_d,   _rl_h   = collect_all('reportlab')
_xl_b,   _xl_d,   _xl_h   = collect_all('openpyxl')
_rich_b, _rich_d, _rich_h = collect_all('rich')

# mysql.connector ships with C-extension auth plugins that PyInstaller
# misses; collect_all handles the dynamic libs (.so / .pyd) correctly.
_my_b,   _my_d,   _my_h   = collect_all('mysql')

# bcrypt contains a compiled C extension — collect_dynamic_libs ensures
# the .pyd (Windows) or .so (Linux/Mac) is bundled.
_bc_libs = collect_dynamic_libs('bcrypt')

# =============================================================================
# STEP 2 — Project source tree as datas
#   Format: (source_glob_or_dir, dest_dir_inside_bundle)
# =============================================================================

project_datas = [
    # Config template (NOT config.ini — that has DB credentials).
    # The app reads config/config.ini at runtime; the user must supply it.
    # We ship the template so users know exactly what to fill in.
    (str(PROJ_ROOT / 'config' / 'config.ini.template'), 'config'),

    # Report template directory (HTML/CSS templates used by export_reports.py)
    (str(PROJ_ROOT / 'reports' / 'templates'), 'reports/templates'),
]

# Only include paths that actually exist in the project at build time
project_datas = [
    (src, dst) for src, dst in project_datas
    if Path(src).exists()
]

# =============================================================================
# STEP 3 — Hidden imports (all packages PyInstaller cannot auto-detect)
# =============================================================================

hidden_imports = [

    # ── mysql-connector-python ───────────────────────────────────────────────
    # Uses plugin-based authentication discovery — each auth mechanism is a
    # standalone module loaded by name at connection time.
    'mysql',
    'mysql.connector',
    'mysql.connector.abstracts',
    'mysql.connector.aio',
    'mysql.connector.aio.abstracts',
    'mysql.connector.aio.cursor',
    'mysql.connector.aio.network',
    'mysql.connector.aio.pooling',
    'mysql.connector.aio.protocol',
    'mysql.connector.authentication',
    'mysql.connector.charset',
    'mysql.connector.connection',
    'mysql.connector.connection_cext',
    'mysql.connector.constants',
    'mysql.connector.conversion',
    'mysql.connector.cursor',
    'mysql.connector.cursor_cext',
    'mysql.connector.dbapi',
    'mysql.connector.errorcode',
    'mysql.connector.errors',
    'mysql.connector.locales',
    'mysql.connector.locales.eng',
    'mysql.connector.locales.eng.client_error',
    'mysql.connector.network',
    'mysql.connector.opentelemetry',
    'mysql.connector.optionfiles',
    'mysql.connector.plugins',
    'mysql.connector.plugins.mysql_native_password',
    'mysql.connector.plugins.caching_sha2_password',
    'mysql.connector.plugins.sha256_password',
    'mysql.connector.plugins.ldap_sasl_client_auth',
    'mysql.connector.pooling',
    'mysql.connector.protocol',
    'mysql.connector.types',
    'mysql.connector.utils',
    'mysql.connector.version',

    # ── bcrypt ───────────────────────────────────────────────────────────────
    # Loaded by user_model.py for password hashing.  The C extension is
    # handled by collect_dynamic_libs above; these cover the pure-Python side.
    'bcrypt',
    'bcrypt._bcrypt',

    # ── rich internal modules ─────────────────────────────────────────────────
    # rich uses __import__ internally for emoji, spinners, and colour tables.
    'rich._cell_widths',
    'rich._emoji_codes',
    'rich._emoji_replace',
    'rich._export_format',
    'rich._loop',
    'rich._palettes',
    'rich._pick',
    'rich._ratio',
    'rich._spinners',
    'rich._windows',
    'rich._windows_renderer',
    'rich._wrap',
    'rich.default_styles',
    'rich.highlighter',
    'rich.progress',
    'rich.progress_bar',
    'rich.spinner',
    'rich.status',
    'rich.live',
    'rich.live_render',
    'rich.logging',
    'rich.pretty',
    'rich.repr',
    'rich.syntax',
    'rich.traceback',
    'rich.tree',

    # ── matplotlib backends ───────────────────────────────────────────────────
    # plt.show() triggers dynamic backend loading.  On Windows the default
    # interactive backend is TkAgg.  Agg is the non-interactive fallback
    # (used when the MPLBACKEND env var is set to 'Agg', e.g. in CI).
    # Both are bundled so the runtime hook can pick the right one.
    'matplotlib.backends.backend_tkagg',
    'matplotlib.backends.backend_agg',
    'matplotlib.backends.backend_pdf',
    'matplotlib.backends.backend_ps',
    'matplotlib.backends.backend_svg',
    'matplotlib.backends._backend_agg',
    'matplotlib.backends._backend_tk',
    'matplotlib.backends._tkagg',

    # ── pandas internal C extensions ─────────────────────────────────────────
    # These .pyd / .so files are referenced by string in pandas internals.
    'pandas._libs.tslibs.np_datetime',
    'pandas._libs.tslibs.nattype',
    'pandas._libs.tslibs.timestamps',
    'pandas._libs.tslibs.timedeltas',
    'pandas._libs.tslibs.offsets',
    'pandas._libs.tslibs.parsing',
    'pandas._libs.tslibs.period',
    'pandas._libs.tslibs.strptime',
    'pandas._libs.tslibs.timezones',
    'pandas._libs.tslibs.tzconversion',
    'pandas._libs.tslibs.vectorized',
    'pandas._libs.tslibs.ccalendar',
    'pandas._libs.tslibs.dtypes',
    'pandas._libs.tslibs.fields',
    'pandas.io.formats.style',
    'pandas.core.arrays.masked',
    'pandas.core.arrays.integer',
    'pandas.core.arrays.floating',
    'pandas.core.arrays.string_',
    'pandas.core.arrays.boolean',
    'pandas.core.arrays.categorical',
    'pandas.core.arrays.datetime_',
    'pandas.core.arrays.datetimes',
    'pandas.core.arrays.timedeltas',
    'pandas.core.arrays.period',
    'pandas.plotting._matplotlib',
    'pandas.plotting._matplotlib.core',

    # ── numpy ─────────────────────────────────────────────────────────────────
    'numpy.core._dtype_ctypes',
    'numpy.random',
    'numpy.random.mtrand',

    # ── reportlab runtime font resolution ────────────────────────────────────
    'reportlab.rl_settings',
    'reportlab.pdfbase._fontdata',
    'reportlab.pdfbase._glyphlist',
    'reportlab.pdfbase.pdfmetrics',
    'reportlab.pdfbase.ttfonts',
    'reportlab.pdfbase.cidfonts',
    'reportlab.pdfbase.pdfdoc',

    # ── openpyxl worksheet table styles ──────────────────────────────────────
    # openpyxl uses importlib.import_module to lazy-load its XML namespaces.
    'openpyxl.worksheet.table',
    'openpyxl.worksheet._writer',
    'openpyxl.worksheet._reader',
    'openpyxl.writer.excel',
    'openpyxl.writer.theme',
    'openpyxl.packaging.manifest',
    'openpyxl.packaging.relationship',
    'openpyxl.descriptors.serialisable',

    # ── pyparsing (used by matplotlib's mathtext and by charts.py) ───────────
    'pyparsing',
    'pyparsing.actions',
    'pyparsing.common',
    'pyparsing.core',
    'pyparsing.exceptions',
    'pyparsing.helpers',
    'pyparsing.results',
    'pyparsing.unicode',

    # ── cycler (used transitively by matplotlib and search.py) ───────────────
    'cycler',

    # ── standard library modules sometimes missed ─────────────────────────────
    'configparser',
    'logging.handlers',
    'email.mime.text',
    'email.mime.multipart',

    # ── Project internal packages ─────────────────────────────────────────────
    # PyInstaller resolves these from the project root but listing them
    # explicitly ensures they are always included even if the auto-scan
    # misses a conditional import path.
    'core',
    'core.database',
    'core.scheduler',
    'core.utils',
    'core.cli_helpers',
    'models',
    'models.user_model',
    'models.account_model',
    'models.category_model',
    'models.transactions_model',
    'models.analytics_model',
    'models.goal_model',
    'features',
    'features.balance',
    'features.goals',
    'features.charts',
    'features.dashboard',
    'features.search',
    'features.recurring',
    'features.export_reports',
    'features.insights',

    # Collected by collect_all above — merged below
    *_mpl_h,
    *_np_h,
    *_pd_h,
    *_rl_h,
    *_xl_h,
    *_rich_h,
    *_my_h,
]

# Deduplicate (collect_all may produce overlaps)
hidden_imports = sorted(set(hidden_imports))

# =============================================================================
# STEP 4 — Modules to EXCLUDE
#   These are pulled in transitively but are never used by FinTrack.
#   Removing them reduces the bundle size significantly.
# =============================================================================

excludes = [
    # Test infrastructure
    'pytest', 'unittest', 'doctest',
    '_pytest', 'pytest_asyncio',

    # Jupyter / IPython ecosystem (matplotlib pulls these in transitively)
    'IPython', 'ipykernel', 'ipython_genutils',
    'nbformat', 'nbconvert', 'notebook',
    'traitlets', 'jinja2',           # only needed for notebooks

    # GUI toolkits we don't use  (TkAgg is the one we DO want — don't exclude tk)
    'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
    'wx', 'gi',

    # Scientific extras not needed
    'scipy', 'sklearn', 'sklearn',
    'statsmodels', 'sympy', 'cvxpy',

    # Database backends other than MySQL
    'psycopg2', 'sqlalchemy', 'pymongo',
    'sqlite3',   # we use MySQL exclusively

    # Development tools
    'mypy', 'flake8', 'black', 'isort',
    'setuptools', 'pip', 'wheel', 'distutils',

    # XML/HTML extras not used
    'lxml', 'beautifulsoup4', 'bs4',
    'html5lib',

    # Async networking (not used in this sync codebase)
    'aiohttp', 'asyncio', 'uvicorn', 'fastapi',
    'twisted',
]

# =============================================================================
# STEP 5 — Runtime hook
#   Written inline to a temp file so the spec is self-contained.
#   The hook runs INSIDE the frozen process before main.py starts.
#
#   It does three things:
#     1. Sets the matplotlib backend to TkAgg (interactive, for plt.show())
#        or falls back to Agg if Tk is unavailable (headless servers, CI).
#     2. Tells matplotlib where to find its bundled font/data files.
#     3. Fixes the working directory so config/config.ini is found correctly
#        when the exe is double-clicked from a different directory.
# =============================================================================

_RUNTIME_HOOK_SRC = """\
import os
import sys

# ── 1. Fix working directory for frozen exe ──────────────────────────────────
# When PyInstaller packs to --onefile, sys._MEIPASS is the temp extraction dir.
# When packed to --onedir, sys._MEIPASS is the dist folder itself.
# Either way, change CWD to the directory containing the exe so that
# config/config.ini is found at the expected relative path.
if getattr(sys, 'frozen', False):
    # sys.executable is the path to the .exe
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    os.chdir(exe_dir)

# ── 2. Set MPLCONFIGDIR to a writable location ───────────────────────────────
# matplotlib writes a font cache to MPLCONFIGDIR.  Inside a frozen exe the
# default path may not be writable, so we redirect to %APPDATA%/FinTrack.
if 'MPLCONFIGDIR' not in os.environ:
    appdata = os.environ.get('APPDATA') or os.path.expanduser('~')
    mpl_dir = os.path.join(appdata, 'FinTrack', 'mpl_config')
    os.makedirs(mpl_dir, exist_ok=True)
    os.environ['MPLCONFIGDIR'] = mpl_dir

# ── 3. Force matplotlib backend ──────────────────────────────────────────────
# Must be done BEFORE any matplotlib import.
# TkAgg = interactive (plt.show() opens a real window) — used in production.
# Agg   = non-interactive (renders to memory only)     — used in CI / headless.
if 'MPLBACKEND' not in os.environ:
    try:
        import tkinter  # noqa: F401 — just testing availability
        os.environ['MPLBACKEND'] = 'TkAgg'
    except ImportError:
        os.environ['MPLBACKEND'] = 'Agg'
"""

import tempfile, atexit

_hook_fd, _hook_path = tempfile.mkstemp(suffix='.py', prefix='fintrack_rthook_')
with os.fdopen(_hook_fd, 'w') as _f:
    _f.write(_RUNTIME_HOOK_SRC)

def _cleanup_hook():
    try:
        os.unlink(_hook_path)
    except Exception:
        pass

atexit.register(_cleanup_hook)

# =============================================================================
# STEP 6 — Analysis
# =============================================================================

a = Analysis(
    scripts=[ENTRY_POINT],

    pathex=[
        str(PROJ_ROOT),           # project root on sys.path
        str(PROJ_ROOT / 'core'),
        str(PROJ_ROOT / 'models'),
        str(PROJ_ROOT / 'features'),
    ],

    binaries=(
        _mpl_b + _np_b + _pd_b + _rl_b + _xl_b + _rich_b + _my_b + _bc_libs
    ),

    datas=(
        project_datas
        + _mpl_d
        + _np_d
        + _pd_d
        + _rl_d
        + _xl_d
        + _rich_d
        + _my_d
    ),

    hiddenimports=hidden_imports,

    hookspath=[
        # If you add custom hooks later, put them in scripts/pyinstaller_hooks/
        str(PROJ_ROOT / 'scripts' / 'pyinstaller_hooks'),
    ],

    hooksconfig={},

    runtime_hooks=[_hook_path],

    excludes=excludes,

    # Let PyInstaller decide module origin at build time (leave as-is)
    noarchive=False,
    optimize=0,
)

# =============================================================================
# STEP 7 — PYZ archive
# =============================================================================

pyz = PYZ(a.pure)

# =============================================================================
# STEP 8 — EXE
# =============================================================================

exe = EXE(
    pyz,
    a.scripts,
    a.binaries   if ONEFILE else [],
    a.zipfiles   if ONEFILE else [],
    a.datas      if ONEFILE else [],
    [],

    name=APP_NAME,

    # Console app (True) = terminal window stays open.
    # Set False only if you add a GUI splash screen later.
    console=True,

    # Strip debug symbols from the binary (reduces size ~10%)
    strip=False,

    # UPX compression: disabled by default — set to True if UPX is installed
    # and you want a smaller exe at the cost of a slower cold start.
    upx=False,

    # Windows version info block (visible in File Properties)
    version=None,   # supply a version_info dict or path to a .rc file here

    # Windows UAC: asInvoker = run as the current user (no admin prompt)
    uac_admin=False,

    # Onefile packing
    onefile=ONEFILE,
)

# =============================================================================
# STEP 9 — COLLECT (only for --onedir mode)
#   Gathers all the pieces into dist/FinTrack/
# =============================================================================

if not ONEFILE:
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name=APP_NAME,
    )
