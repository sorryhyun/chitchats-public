"""
Infrastructure layer - database, caching, scheduler, and logging.

Re-exports commonly used infrastructure components.
"""


# Lazy import to avoid circular dependencies
def __getattr__(name):
    if name == "BackgroundScheduler":
        from .scheduler import BackgroundScheduler

        return BackgroundScheduler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["BackgroundScheduler"]
