# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for ChitChats-Haiku (Sonnet 4.6 mode).

Same as ChitChats.spec but with a runtime hook that forces USE_HAIKU=true,
producing ChitChats-Haiku.exe that always runs with Claude Sonnet 4.6.

Build command: pyinstaller ChitChats-Haiku.spec
"""

import os
from pathlib import Path

# Get the project root directory
project_root = Path(SPECPATH)
backend_dir = project_root / 'backend'
frontend_dist = project_root / 'frontend' / 'dist'
agents_dir = project_root / 'agents'

# Data files to include
mcp_servers_config_dir = backend_dir / 'mcp_servers' / 'config'
providers_dir = backend_dir / 'providers'

datas = [
    # Frontend static files
    (str(frontend_dist), 'static'),
    # MCP servers config files (tools.py, guidelines.yaml, debug.yaml) - bundled at mcp_servers/config/
    (str(mcp_servers_config_dir), 'mcp_servers/config'),
    # Provider-specific prompts.yaml files
    (str(providers_dir / 'claude' / 'prompts.yaml'), 'providers/claude'),
    (str(providers_dir / 'codex' / 'prompts.yaml'), 'providers/codex'),
    # .env.example as template
    (str(project_root / '.env.example'), '.'),
]

# Collect local backend modules dynamically
def collect_backend_modules(backend_path):
    """Find all Python modules in the backend directory."""
    modules = []
    for root, dirs, files in os.walk(backend_path):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', 'tests', '.pytest_cache')]

        rel_path = os.path.relpath(root, backend_path)
        if rel_path == '.':
            package = ''
        else:
            package = rel_path.replace(os.sep, '.')

        for file in files:
            if file.endswith('.py') and not file.startswith('test_'):
                module_name = file[:-3]
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
    runtime_hooks=[str(project_root / 'scripts' / 'windows' / 'runtime_hook_haiku.py')],
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
    name='ChitChats-Haiku',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / 'frontend' / 'public' / 'chitchats.ico'),
)
