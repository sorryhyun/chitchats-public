"""Interactive console-mode first-time setup wizard."""

import getpass
import secrets


def run_first_time_setup():
    """Run interactive first-time setup wizard (console mode)."""
    import bcrypt

    print("=" * 60)
    print("ChitChats - 초기 설정")
    print("=" * 60)
    print()
    print("환영합니다! 애플리케이션을 설정해주세요.")
    print()

    while True:
        password = getpass.getpass("비밀번호를 입력하세요: ")
        if len(password) < 4:
            print("비밀번호는 최소 4자 이상이어야 합니다. 다시 시도해주세요.")
            continue

        password_confirm = getpass.getpass("비밀번호 확인: ")
        if password != password_confirm:
            print("비밀번호가 일치하지 않습니다. 다시 시도해주세요.")
            continue

        if len(password) < 8:
            print("\n참고: 비밀번호가 8자 미만입니다.")
            proceed = input("계속하시겠습니까? (Y/n): ").strip().lower()
            if proceed == "n":
                continue

        break

    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    jwt_secret = secrets.token_hex(32)

    user_name = input("\n표시할 이름을 입력하세요 (기본값: User): ").strip()
    if not user_name:
        user_name = "User"

    return {
        "password_hash": password_hash,
        "jwt_secret": jwt_secret,
        "user_name": user_name,
    }
