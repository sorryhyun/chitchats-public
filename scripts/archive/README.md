# Archived Scripts

This folder contains archived scripts that are no longer recommended for use.

## build_tauri.ps1

**Status:** Archived
**Reason:** Tauri build is not suitable for Windows deployment

The Tauri desktop app approach was explored but found to have issues on Windows:
- Complex build process requiring Rust toolchain
- Sidecar management complications
- Better alternatives exist (standalone PyInstaller exe)

### Recommended Alternative

Use the standalone Windows executable build instead:

```bash
make build-non-tauri
# or directly:
.\scripts\windows\build_exe.ps1
```

This creates a single `ChitChats.exe` with embedded frontend that works reliably on Windows.

### If You Still Need Tauri

The Tauri source code remains in `frontend/src-tauri/` but is not actively maintained. Use at your own risk:

```bash
make build-tauri-archived
```
