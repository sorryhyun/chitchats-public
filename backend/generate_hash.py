#!/usr/bin/env python3
"""
Utility script to generate bcrypt password hashes for the API_KEY_HASH.

Usage:
    python generate_hash.py
    python generate_hash.py --password "your_password" --output-only

This will prompt you for a password (or accept one via --password) and
output a bcrypt hash that you can add to your .env file as API_KEY_HASH.
"""

import argparse
import getpass
import sys

import bcrypt


def _print_header():
    print("=" * 60)
    print("Claude Code Role Play Password Hash Generator")
    print("=" * 60)
    print()
    print("This script will generate a bcrypt hash for your password.")
    print("Add the generated hash to your .env file as API_KEY_HASH.")
    print()


def _maybe_warn_short(password: str, allow_short: bool) -> bool:
    if len(password) >= 8:
        return True

    print("\n⚠️  Warning: Password is less than 8 characters.")
    print("   Consider using a longer password for better security.")

    if allow_short:
        return True

    proceed = input("Continue anyway? (y/N): ")
    return proceed.lower() == "y"


def _hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password.encode("utf-8"), salt)
    return password_hash.decode("utf-8")


def generate_hash(password: str | None = None, *, allow_short: bool = False, output_only: bool = False) -> str:
    """Generate a bcrypt hash from user input or a provided password."""

    if password is None:
        _print_header()
        password = getpass.getpass("Enter your desired password: ")
        password_confirm = getpass.getpass("Confirm password: ")

        if password != password_confirm:
            raise ValueError("Passwords do not match. Please try again.")

        if not _maybe_warn_short(password, allow_short):
            raise ValueError("Aborted by user.")
    else:
        if len(password) < 8 and not allow_short:
            raise ValueError("Password is less than 8 characters. Re-run with a longer password or --allow-short.")

    hash_str = _hash_password(password)

    if output_only:
        print(hash_str)
        return hash_str

    print("\n" + "=" * 60)
    print("✅ Hash generated successfully!")
    print("=" * 60)
    print()
    print("Add this line to your .env file:")
    print()
    print(f"API_KEY_HASH={hash_str}")
    print()
    print("=" * 60)
    print()
    print("📝 Notes:")
    print("  - Keep this hash secret and don't commit it to git")
    print("  - You can remove the old API_KEY line from .env")
    print("  - Users will login with the original password, not the hash")
    print("  - Restart your backend server after updating .env")
    print()
    return hash_str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate bcrypt hash for API_KEY_HASH")
    parser.add_argument("--password", help="Password to hash (non-interactive)")
    parser.add_argument("--allow-short", action="store_true", help="Allow passwords shorter than 8 characters without prompting")
    parser.add_argument(
        "--output-only",
        action="store_true",
        help="Print only the hash (useful for scripting)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    try:
        generate_hash(args.password, allow_short=args.allow_short, output_only=args.output_only)
    except KeyboardInterrupt:
        print("\n\nAborted.")
        sys.exit(1)
    except Exception as error:  # noqa: BLE001 - script-friendly error reporting
        print(f"\n❌ Error: {error}")
        sys.exit(1)
