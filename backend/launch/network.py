"""Port discovery."""

import socket

DEFAULT_PORT = 8000
FALLBACK_PORTS = [8001, 8080, 8888, 9000]


def find_available_port(preferred_port: int = DEFAULT_PORT) -> int:
    """Find an available port, starting with the preferred port."""
    ports_to_try = [preferred_port] + [p for p in FALLBACK_PORTS if p != preferred_port]

    for port in ports_to_try:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except (OSError, PermissionError):
            continue

    # Last resort: let OS assign a port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
