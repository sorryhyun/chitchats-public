# Differences from Private Repository

This document tracks differences between the public repository (`claude_code_RP`) and the private development repository (`chitchats`). The private repo is the primary development source, and changes are synced here periodically.

## Overview

| Repository | Purpose | Focus |
|------------|---------|-------|
| `chitchats` (private) | Primary development | Web deployment, research/evaluation |
| `claude_code_RP` (public) | Distribution | Windows desktop app, standalone builds |

## Files Unique to This Repository (Public)

### Frontend

#### `frontend/src/components/SetupWizard.tsx`

Multi-step setup UI for desktop application:

- Password configuration
- Username setup
- Backend initialization status

#### `frontend/src/utils/tauri.ts`

Tauri runtime detection and interaction:

- Setup state checks
- Backend control (start/stop)
- Health check utilities

#### `frontend/public/manifest.json`

PWA manifest for web app installability.

#### `frontend/src-tauri/` (entire directory)

Complete Tauri desktop app configuration:

- Rust backend integration
- Window configuration and capabilities
- Build artifacts and icons

### Scripts

#### `scripts/windows/`

Windows-specific build scripts:

- `build_exe.ps1` - PowerShell script for building Windows executable
- `dev.ps1` - Development environment setup for Windows

#### `scripts/setup/create_env.py`

Environment file creation utility for Tauri setup wizard.

#### `scripts/archive/`

Archived Tauri build scripts (deprecated, kept for reference).

---

## Files Unique to Private Repository

### Backend

#### `backend/config/system_prompt_exp.yaml`

Experimental system prompt configurations for research.

### Scripts

#### `scripts/evaluation/` (8+ scripts)

Research and evaluation framework:

- `evaluate_authenticity.sh` - Agent authenticity evaluation
- `evaluate_humanness.sh` - Humanness scoring
- `evaluate_responses.sh` - Response quality metrics
- `evaluate_questions.sh` - Question evaluation
- `evaluate_parallel.sh` - Parallel evaluation runner
- `generate_checklists.sh` - Evaluation checklist generation
- `collect_answers.sh` - Answer collection
- `parse_transcripts.py` / `parse_transcripts.sh` - Transcript parsing
- `analyze_results.py` - Results analysis

#### `scripts/collect_thinking_signatures.py`

Analysis tool for collecting agent thinking patterns.

#### `scripts/output.py`

Large output processing script for research data.

### Configuration

#### `.vercel/project.json`

Vercel deployment configuration (private deployment settings).

---

## Capability Differences

| Capability | Public (claude_code_RP) | Private (chitchats) |
|------------|-------------------------|---------------------|
| **Deployment Target** | Windows desktop (Tauri) + web | Web-based (Vercel) |
| **Windows Native** | Yes (PowerShell builds) | No |
| **Desktop Setup UI** | SetupWizard component | None |
| **Image Handling** | Full (Codex + Claude) | Full (Codex + Claude) |
| **Research Tools** | Simulation only | Full evaluation framework |
| **Thinking Analysis** | None | Signature collection |

---

## Sync Notes

When syncing from private to public:

1. **Keep public-only files** - Don't delete Windows support, Tauri, or setup wizard files
2. **Skip private-only files** - Don't copy evaluation scripts or research tools
3. **Check for conflicts** - Some files may have diverged

When syncing from public to private:

1. **Skip desktop-specific code** - Windows support and Tauri files aren't needed
2. **Review new features** - Any public contributions should be evaluated for private repo
