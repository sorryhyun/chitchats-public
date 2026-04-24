"""First-time setup orchestration."""

import sys

from ..agents_bootstrap import copy_default_agents
from ..logging_setup import is_windowed_mode
from ..paths import get_work_dir
from .console import run_first_time_setup
from .env_file import create_env_file, is_env_configured
from .gui import run_first_time_setup_gui


def setup_environment() -> bool:
    """Set up environment for the bundled application. Returns True if setup was run."""
    env_file = get_work_dir() / ".env"

    copy_default_agents()

    if is_env_configured(env_file):
        return False

    try:
        if is_windowed_mode():
            config = run_first_time_setup_gui()
            if config is None:
                sys.exit(0)
        else:
            config = run_first_time_setup()

        create_env_file(env_file, config)
        print()
        print("=" * 60)
        print("설정 완료! 애플리케이션을 시작합니다...")
        print("=" * 60)
        print()
        return True
    except KeyboardInterrupt:
        print("\n\n설정이 취소되었습니다.")
        sys.exit(0)
