"""
Claude Code conversation export endpoints.

These endpoints provide access to Claude Code conversation files (.jsonl)
stored in ~/.claude/projects/ directories for both Windows and WSL.
"""

import json
import platform
from pathlib import Path
from typing import Any, List

from core.auth import require_admin
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()


class ConversationFile(BaseModel):
    """Represents a Claude Code conversation file."""
    id: str
    filename: str
    project: str
    modified: str
    size: int


class ConversationList(BaseModel):
    """List of conversation files."""
    conversations: List[ConversationFile]


def get_claude_projects_dirs() -> List[Path]:
    """
    Get all Claude Code projects directories.

    Supports Windows native, WSL, and Linux/macOS paths.
    On WSL, checks both native Linux path and Windows user paths.
    On Windows, also derives user directory from temp path for bundled exe support.

    Returns:
        List of existing .claude/projects directories
    """
    import os
    import tempfile

    candidates = []

    # Check native home directory first (works on all platforms)
    home = Path.home()
    candidates.append(home / ".claude" / "projects")

    system = platform.system()

    if system == "Windows":
        # Windows native - also check common user directories
        # Check USERPROFILE if different from home
        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            userprofile_path = Path(userprofile) / ".claude" / "projects"
            if userprofile_path not in candidates:
                candidates.append(userprofile_path)

        # In bundled mode, derive user directory from temp path
        # Temp path is typically C:\Users\{username}\AppData\Local\Temp
        temp_dir = Path(tempfile.gettempdir())
        try:
            # Navigate up from temp to find Users directory
            # C:\Users\username\AppData\Local\Temp -> C:\Users\username
            parts = temp_dir.parts
            if len(parts) >= 4 and parts[1].lower() == "users":
                # Reconstruct user home from temp path
                user_home = Path(parts[0]) / parts[1] / parts[2]
                user_claude = user_home / ".claude" / "projects"
                if user_claude not in candidates:
                    candidates.append(user_claude)
        except Exception:
            pass

    elif system == "Linux" and "microsoft" in platform.release().lower():
        # WSL detected - check Windows user directories via /mnt/
        try:
            for base_path in ["/mnt/c/Users", "/mnt/d/Users"]:
                base = Path(base_path)
                if base.exists():
                    for user_dir in base.iterdir():
                        if user_dir.is_dir() and not user_dir.name.startswith(
                            ('Default', 'Public', 'All Users', 'Default User')
                        ):
                            win_claude = user_dir / ".claude" / "projects"
                            if win_claude.exists():
                                candidates.append(win_claude)
        except Exception:
            pass

    # Return all existing directories (deduplicated)
    seen = set()
    result = []
    for path in candidates:
        if path.exists() and path.is_dir():
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                result.append(path)

    return result


def is_chitchats_project(project_name: str) -> bool:
    """
    Check if a project directory is a ChitChats conversation directory.

    ChitChats uses a temp directory named 'claude-empty' for SDK conversations.
    Project names are path-encoded, so we look for directories ending with 'claude-empty'.

    Examples:
        - WSL/Linux: '-tmp-claude-empty'
        - Windows: '-C-Users-username-AppData-Local-Temp-claude-empty'

    Args:
        project_name: The project directory name

    Returns:
        True if this is a ChitChats project directory
    """
    return project_name.endswith("claude-empty")


def list_project_conversations(projects_dir: Path) -> List[ConversationFile]:
    """
    List all conversation files in the projects directory.

    Only includes conversations from ChitChats (claude-empty) projects.

    Args:
        projects_dir: Path to .claude/projects directory

    Returns:
        List of ConversationFile objects
    """
    conversations = []

    try:
        for project_dir in projects_dir.iterdir():
            if project_dir.is_dir():
                project_name = project_dir.name
                # Only include ChitChats projects (claude-empty directories)
                if not is_chitchats_project(project_name):
                    continue
                for jsonl_file in project_dir.glob("*.jsonl"):
                    # Skip sub-agent conversation files (spawned by Task tool)
                    if jsonl_file.stem.startswith("agent-"):
                        continue
                    stat = jsonl_file.stat()
                    conversations.append(ConversationFile(
                        id=jsonl_file.stem,
                        filename=jsonl_file.name,
                        project=project_name,
                        modified=str(stat.st_mtime),
                        size=stat.st_size
                    ))
    except Exception:
        pass

    # Sort by modification time, newest first
    conversations.sort(key=lambda x: float(x.modified), reverse=True)
    return conversations


def simplify_conversation(content: str) -> str:
    """
    Simplify JSONL conversation content for export.

    Removes:
    - 'signature' field from thinking blocks
    - 'parentUuid' and 'sessionId' internal tracking fields

    Args:
        content: JSONL file content

    Returns:
        Simplified content
    """
    lines = []
    for line in content.strip().split('\n'):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            _simplify_entry(data)
            lines.append(json.dumps(data, ensure_ascii=False))
        except json.JSONDecodeError:
            # Keep malformed lines as-is
            lines.append(line)
    return '\n'.join(lines)


def _simplify_entry(obj: Any) -> None:
    """
    Simplify a JSONL entry by removing internal tracking fields.

    Removes at top level:
    - parentUuid, sessionId, uuid
    - requestId, isSidechain
    - toolUseResult (duplicates message.content)

    Removes recursively:
    - signature from thinking blocks
    - image content blocks (base64 data)
    """
    if isinstance(obj, dict):
        # Remove top-level tracking fields
        for field in (
            'parentUuid', 'sessionId', 'uuid', 'requestId', 'isSidechain',
            'toolUseResult',  # Duplicates message.content for tool results
        ):
            obj.pop(field, None)

        # Remove signature if this is a thinking block
        if obj.get('type') == 'thinking':
            obj.pop('signature', None)

        # Recurse into all values
        for value in obj.values():
            _simplify_entry(value)
    elif isinstance(obj, list):
        # Filter out image content blocks before recursing
        items_to_remove = []
        for i, item in enumerate(obj):
            if isinstance(item, dict) and item.get('type') == 'image':
                items_to_remove.append(i)
            else:
                _simplify_entry(item)
        # Remove image items in reverse order to preserve indices
        for i in reversed(items_to_remove):
            obj.pop(i)


@router.get("/conversations", dependencies=[Depends(require_admin)])
async def list_conversations() -> ConversationList:
    """
    List all available Claude Code conversation files.

    Searches in ~/.claude/projects/ and related directories.

    Returns:
        List of conversation files with metadata
    """
    projects_dirs = get_claude_projects_dirs()

    if not projects_dirs:
        return ConversationList(conversations=[])

    # Aggregate conversations from all directories
    all_conversations = []
    for projects_dir in projects_dirs:
        all_conversations.extend(list_project_conversations(projects_dir))

    # Sort by modification time, newest first
    all_conversations.sort(key=lambda x: float(x.modified), reverse=True)
    return ConversationList(conversations=all_conversations)


@router.get("/conversations/{project}/{conversation_id}")
async def download_conversation(
    project: str,
    conversation_id: str,
    simplified: bool = False,
) -> StreamingResponse:
    """
    Download a specific Claude Code conversation file.

    Args:
        project: Project directory name (e.g., "-home-user-myproject")
        conversation_id: Conversation UUID (without .jsonl extension)
        simplified: If True, removes thinking signatures from output

    Returns:
        JSONL file as download
    """
    projects_dirs = get_claude_projects_dirs()

    if not projects_dirs:
        raise HTTPException(status_code=404, detail="Claude projects directory not found")

    # Validate path components - prevent directory traversal
    if ".." in project or "/" in project or "\\" in project:
        raise HTTPException(status_code=400, detail="Invalid project name")
    if ".." in conversation_id or "/" in conversation_id or "\\" in conversation_id:
        raise HTTPException(status_code=400, detail="Invalid conversation ID")

    # Only allow downloads from ChitChats projects
    if not is_chitchats_project(project):
        raise HTTPException(status_code=403, detail="Only ChitChats conversations can be exported")

    # Search for file in all projects directories
    file_path = None
    for projects_dir in projects_dirs:
        candidate = projects_dir / project / f"{conversation_id}.jsonl"
        if candidate.exists():
            file_path = candidate
            break

    if file_path is None:
        raise HTTPException(status_code=404, detail="Conversation file not found")

    # Read file content
    content = file_path.read_text(encoding='utf-8')

    # Apply simplification if requested
    if simplified:
        content = simplify_conversation(content)
        suffix = "_simplified"
    else:
        suffix = ""

    filename = f"{conversation_id}{suffix}.jsonl"

    def iterate_content():
        yield content

    return StreamingResponse(
        iterate_content(),
        media_type="application/x-jsonlines",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )
