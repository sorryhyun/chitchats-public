"""Extract/copy default agents for bundled mode."""

import sys

from .paths import get_base_path, get_work_dir


def copy_default_agents():
    """Extract default agents from zip if they don't exist.

    In bundled mode, agents are distributed as agents.zip alongside the exe
    rather than being bundled inside the exe. This reduces exe size and allows
    users to update agents independently.
    """
    if not getattr(sys, "frozen", False):
        return

    work_dir = get_work_dir()
    agents_dest = work_dir / "agents"
    agents_zip = work_dir / "agents.zip"

    if agents_dest.exists():
        return

    if agents_zip.exists():
        import zipfile

        print("에이전트를 압축 해제하는 중...")
        with zipfile.ZipFile(agents_zip, "r") as zf:
            zf.extractall(work_dir)
        print(f"에이전트를 압축 해제했습니다: {agents_dest}")
    else:
        # Fallback: check for bundled agents (legacy support)
        agents_src = get_base_path() / "agents"
        if agents_src.exists():
            import shutil

            shutil.copytree(agents_src, agents_dest)
            print(f"기본 에이전트를 복사했습니다: {agents_dest}")
        else:
            print(f"경고: agents.zip을 찾을 수 없습니다: {agents_zip}")
            print("에이전트 폴더를 수동으로 생성해주세요.")
