# [ARCHIVED] Tauri Desktop App

**Status:** Archived - Not recommended for Windows

This directory contains the Tauri desktop application source code. The Tauri build approach has been archived due to issues on Windows.

## Why Archived?

- Complex build process requiring Rust toolchain
- Sidecar management complications on Windows
- The standalone PyInstaller executable (`make build-exe`) provides a simpler, more reliable solution

## Recommended Alternative

Use the standalone Windows executable build instead:

```bash
make build-exe
# or
.\scripts\windows\build_exe.ps1
```

## If You Still Need Tauri

The code remains here for reference or if you need to build for other platforms. Use at your own risk:

```bash
make build-tauri-archived
```

See `scripts/archive/README.md` for more details.

## Directory Structure

- `src/` - Rust source code for Tauri commands
- `capabilities/` - Tauri permission capabilities
- `sidecars/` - Backend sidecar location (created during build)
- `tauri.conf.json` - Tauri configuration
