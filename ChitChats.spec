# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for ChitChats.

This bundles the FastAPI backend with the pre-built React frontend
into a single Windows executable.

Build command: pyinstaller ChitChats.spec
"""

import os
from pathlib import Path

# Get the project root directory
project_root = Path(SPECPATH)
backend_dir = project_root / 'backend'
frontend_dist = project_root / 'frontend' / 'dist'
agents_dir = project_root / 'agents'

# Data files to include
# NOTE: Agents are NOT bundled here - they are distributed as agents.zip alongside the exe
# This reduces exe size and allows users to update agents independently
# Use `make agents-zip` to create agents.zip for distribution
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
    # Python-dotenv
    'dotenv',
    # Image processing
    'PIL',
    'PIL.Image',
    'PIL.WebPImagePlugin',
    # System tray (standalone mode)
    'pystray',
    'pystray._win32',
]

# Windows version info
version_info = None
if os.name == 'nt' or True:  # Always generate (cross-compile friendly)
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )
    version_info = VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=(1, 0, 0, 0),
            prodvers=(1, 0, 0, 0),
            mask=0x3f,
            flags=0x0,
            OS=0x40004,        # VOS_NT_WINDOWS32
            fileType=0x1,      # VFT_APP
            subtype=0x0,
        ),
        kids=[
            StringFileInfo([
                StringTable(
                    '040904B0',  # lang=US English, charset=Unicode
                    [
                        StringStruct('CompanyName', 'ChitChats'),
                        StringStruct('FileDescription', 'ChitChats - Multi-Agent Chat Room'),
                        StringStruct('FileVersion', '1.0.0'),
                        StringStruct('InternalName', 'ChitChats'),
                        StringStruct('OriginalFilename', 'ChitChats.exe'),
                        StringStruct('ProductName', 'ChitChats'),
                        StringStruct('ProductVersion', '1.0.0'),
                    ],
                ),
            ]),
            VarFileInfo([VarStruct('Translation', [0x0409, 0x04B0])]),
        ],
    )

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
    name='ChitChats',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Windowed mode - no console window, uses system tray instead
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / 'frontend' / 'public' / 'chitchats.ico'),
    version=version_info,
)
