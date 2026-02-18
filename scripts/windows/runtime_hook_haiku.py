"""PyInstaller runtime hook to force USE_HAIKU=true (Sonnet 4.6 mode)."""
import os

os.environ["USE_HAIKU"] = "true"
