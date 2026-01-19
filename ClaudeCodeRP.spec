# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Claude Code Role Play.

This bundles the FastAPI backend with the pre-built React frontend
into a single Windows executable.

Build command: pyinstaller ClaudeCodeRP.spec
"""

import os
from pathlib import Path

# Get the project root directory
project_root = Path(SPECPATH)
backend_dir = project_root / 'backend'
frontend_dist = project_root / 'frontend' / 'dist'
agents_dir = project_root / 'agents'
config_dir = backend_dir / 'config'

# Data files to include
datas = [
    # Frontend static files
    (str(frontend_dist), 'static'),
    # Agent configurations
    (str(agents_dir), 'agents'),
    # Backend config files (YAML) - must be at config/ since settings.py looks for backend_dir/config
    # In bundled mode, backend modules are at root, so config should be at config/ not backend/config/
    (str(config_dir), 'config'),
    # .env.example as template
    (str(project_root / '.env.example'), '.'),
]

# Collect local backend modules dynamically
def collect_backend_modules(backend_path):
    """Find all Python modules in the backend directory."""
    modules = []
    for root, dirs, files in os.walk(backend_path):
        # Skip __pycache__ and test directories
        dirs[:] = [d for d in dirs if d not in ('__pycache__', 'tests', '.pytest_cache')]

        rel_path = os.path.relpath(root, backend_path)
        if rel_path == '.':
            package = ''
        else:
            package = rel_path.replace(os.sep, '.')

        for file in files:
            if file.endswith('.py') and not file.startswith('test_'):
                module_name = file[:-3]  # Remove .py extension
                if package:
                    full_module = f'{package}.{module_name}'
                else:
                    full_module = module_name
                modules.append(full_module)

    return modules

backend_modules = collect_backend_modules(backend_dir)

# Hidden imports that PyInstaller might miss
hiddenimports = [
    # Local backend modules
    *backend_modules,
    # Uvicorn internals
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    # Database
    'sqlalchemy.dialects.sqlite',
    'aiosqlite',
    # Auth
    'bcrypt',
    'jwt',  # PyJWT package
    # Claude Agent SDK
    'claude_agent_sdk',
    'claude_agent_sdk.client',
    'mcp',
    'mcp.types',
    # HTTP clients
    'httpx',
    'httpcore',
    'anyio',
    'anyio._backends',
    'anyio._backends._asyncio',
    'sniffio',
    'h11',
    'certifi',
    # APScheduler
    'apscheduler.triggers.interval',
    'apscheduler.triggers.cron',
    'apscheduler.schedulers.asyncio',
    'apscheduler.schedulers.background',
    'apscheduler.jobstores.memory',
    'apscheduler.executors.pool',
    # YAML
    'ruamel.yaml',
    'ruamel.yaml.clib',
    # Web framework
    'slowapi',
    'starlette.responses',
    'starlette.staticfiles',
    # Pydantic
    'pydantic',
    'pydantic_core',
    'email_validator',
    # Python-dotenv
    'dotenv',
    # Image processing
    'PIL',
    'PIL.Image',
    'PIL.WebPImagePlugin',
]

a = Analysis(
    [str(backend_dir / 'launcher.py')],
    pathex=[str(backend_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'cv2',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ClaudeCodeRP',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Console window for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / 'frontend' / 'public' / 'chitchats.ico'),
)
