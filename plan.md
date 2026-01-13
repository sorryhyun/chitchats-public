# SDK Restructuring Plan

## Overview

Restructure shared infrastructure to properly separate from provider-specific code.

**Goals:**
- Clean separation between shared orchestration logic and provider-specific implementations
- Easy addition of new providers (GPT-4, Gemini, local LLMs, etc.)
- No Claude-specific imports in shared code

## Current State (After Phase 2)

```
backend/
├── core/                         # Shared infrastructure (merged from sdk/)
│   ├── manager.py                # AgentManager - uses ClaudeClientPool (Phase 3 will generalize)
│   ├── client_pool.py            # BaseClientPool - abstract base class, no Claude imports
│   ├── config/                   # Shared config loading
│   └── memory/                   # Shared memory parsing
└── providers/
    ├── base.py                   # Abstract interfaces (AIProvider, AIClient, ClientPoolInterface)
    ├── factory.py                # Provider factory
    ├── claude/
    │   ├── provider.py
    │   ├── parser.py
    │   ├── client.py
    │   └── pool.py               # ClaudeClientPool - Claude-specific pool
    └── codex/
        ├── provider.py
        ├── parser.py
        ├── client.py
        └── pool.py               # CodexClientPool - Codex-specific pool
```

## Completed Phases

### Phase 2: Extract Provider-Specific Pool Logic ✅

Split `ClientPool` into base class (shared) + provider implementations.

1. ✅ Created `ClientPoolInterface` in `providers/base.py`
2. ✅ Refactored `core/client_pool.py` to `BaseClientPool` with shared logic only (no Claude imports)
3. ✅ Created `providers/claude/pool.py` with `ClaudeClientPool`
4. ✅ Created `providers/codex/pool.py` with `CodexClientPool`
5. ✅ Updated `core/manager.py` to use `ClaudeClientPool`
6. ✅ Fixed circular import in `core/__init__.py` with lazy loading for `AgentManager`

## Remaining Phases

### Phase 3: Clean Up AgentManager

Remove Claude-specific imports from `AgentManager`.

1. Replace `ClaudeSDKClient` type hints with `AIClient`
2. Use provider factory instead of direct Claude SDK imports
3. Create pools per provider lazily via `_get_pool(provider_type)`

### Phase 4: Provider Factory Enhancement

Add `create_pool()` method to `AIProvider` interface.

## Target State

```
backend/
├── core/                         # Shared infrastructure
│   ├── manager.py                # Provider-agnostic AgentManager
│   ├── client_pool.py            # BaseClientPool (abstract)
│   ├── config/
│   └── memory/
└── providers/
    ├── base.py                   # AIProvider, AIClient, ClientPoolInterface
    ├── claude/
    │   ├── provider.py           # create_pool() -> ClaudeClientPool
    │   ├── pool.py               # Claude-specific pool (NEW)
    │   └── ...
    └── codex/
        ├── provider.py           # create_pool() -> CodexClientPool
        ├── pool.py               # Codex-specific pool (NEW)
        └── ...
```

## Adding a New Provider

```
providers/{name}/
├── provider.py    # Implement AIProvider
├── client.py      # Implement AIClient
├── pool.py        # Extend BaseClientPool
└── parser.py      # Implement StreamParser
```

No changes needed to `core/` or existing providers.
