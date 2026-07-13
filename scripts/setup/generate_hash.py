#!/usr/bin/env python3
"""
Utility script to generate bcrypt password hashes and write them to .env.

Usage:
    python generate_hash.py              # write API_KEY_HASH (and friends) into .env
    python generate_hash.py --print-only # just print the hash, don't touch .env

Creates .env from .env.example when it doesn't exist yet, fills in a random
JWT_SECRET if one isn't set, and optionally sets GUEST_PASSWORD_HASH.
"""

import argparse
import getpass
import re
import secrets
import shutil
import sys
from pathlib import Path

import bcrypt

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".env"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"

# Values in .env.example that stand in for "you still need to fill this in".
PLACEHOLDER_PATTERNS = (
    "example_hash_paste",
    "example_guest_hash_paste",
    "your-random-secret-key-here",
)


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the given password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def is_placeholder(value: str) -> bool:
    """True if a value is one of .env.example's fill-me-in stand-ins."""
    return not value.strip() or any(p in value for p in PLACEHOLDER_PATTERNS)


def read_value(lines: list[str], key: str) -> str | None:
    """Return the current (uncommented) value of key, or None if unset."""
    for line in lines:
        match = re.match(rf"\s*{re.escape(key)}\s*=(.*)$", line)
        if match:
            return match.group(1).strip()
    return None


def upsert(lines: list[str], key: str, value: str) -> list[str]:
    """Set key=value, replacing an active line, else uncommenting a commented
    one, else appending. Comments and ordering are otherwise preserved."""
    new_line = f"{key}={value}"

    for i, line in enumerate(lines):
        if re.match(rf"\s*{re.escape(key)}\s*=", line):
            lines[i] = new_line
            return lines

    # No active line: reuse a commented-out template line if there is one, so
    # the value lands next to its explanatory comment instead of at the bottom.
    for i, line in enumerate(lines):
        if re.match(rf"\s*#\s*{re.escape(key)}\s*=", line):
            lines[i] = new_line
            return lines

    if lines and lines[-1].strip():
        lines.append("")
    lines.append(new_line)
    return lines


def prompt_password(label: str) -> str | None:
    """Prompt for a password twice and return it, or None if the user bails."""
    password = getpass.getpass(f"Enter {label}: ")
    if not password:
        print("\n❌ Empty password. Aborted.")
        return None

    if password != getpass.getpass(f"Confirm {label}: "):
        print("\n❌ Passwords do not match. Please try again.")
        return None

    if len(password) < 8:
        print("\n⚠️  Warning: Password is less than 8 characters.")
        print("   Consider using a longer password for better security.")
        if input("Continue anyway? (y/N): ").lower() != "y":
            print("Aborted.")
            return None

    return password


def load_env_lines() -> list[str]:
    """Return .env's lines, seeding it from .env.example on first run."""
    if ENV_PATH.exists():
        return ENV_PATH.read_text().splitlines()

    if ENV_EXAMPLE_PATH.exists():
        print(f"📄 No .env found — creating one from {ENV_EXAMPLE_PATH.name}")
        return ENV_EXAMPLE_PATH.read_text().splitlines()

    print("📄 No .env or .env.example found — creating a minimal .env")
    return []


def write_env(lines: list[str]) -> None:
    """Write .env, backing up any existing file to .env.bak first."""
    if ENV_PATH.exists():
        backup = ENV_PATH.with_name(".env.bak")
        shutil.copy2(ENV_PATH, backup)
        print(f"🗄️  Backed up existing .env to {backup.name}")

    ENV_PATH.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate password hashes for ChitChats.")
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="print the hash instead of writing it to .env",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("ChitChats Password Hash Generator")
    print("=" * 60)
    print()

    password = prompt_password("your desired password")
    if password is None:
        return 1
    admin_hash = hash_password(password)

    if args.print_only:
        print("\n" + "=" * 60)
        print("✅ Hash generated successfully!")
        print("=" * 60)
        print("\nAdd this line to your .env file:\n")
        print(f"API_KEY_HASH={admin_hash}\n")
        return 0

    lines = load_env_lines()
    lines = upsert(lines, "API_KEY_HASH", admin_hash)
    written = ["API_KEY_HASH"]

    # A guest hash is optional; only prompt, never force.
    if input("\nAlso set a guest (read-only) password? (y/N): ").lower() == "y":
        guest_password = prompt_password("the guest password")
        if guest_password is None:
            return 1
        if guest_password == password:
            print("\n❌ Guest password must differ from the admin password.")
            return 1
        lines = upsert(lines, "GUEST_PASSWORD_HASH", hash_password(guest_password))
        written.append("GUEST_PASSWORD_HASH")

    # JWT_SECRET has no reason to be hand-written; fill it if it's still unset.
    jwt_secret = read_value(lines, "JWT_SECRET")
    if jwt_secret is None or is_placeholder(jwt_secret):
        lines = upsert(lines, "JWT_SECRET", secrets.token_hex(32))
        written.append("JWT_SECRET")

    write_env(lines)

    print("\n" + "=" * 60)
    print(f"✅ Wrote {', '.join(written)} to {ENV_PATH}")
    print("=" * 60)
    print()
    print("📝 Notes:")
    print("  - .env is gitignored — keep it that way")
    print("  - You log in with the original password, not the hash")
    print("  - Restart the backend to pick up the changes")
    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nAborted.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
