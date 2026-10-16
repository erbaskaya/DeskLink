"""Release identity and bundle-safe icon lookup."""
from pathlib import Path
import sys

APP_VERSION = "0.4.0"
DEFAULT_RELAY = "wss://desklink-relay.erbaskayam.workers.dev/ws"

def bundled_brand_asset(filename: str) -> Path:
    """Works from source as well as frozen PyInstaller .exe / .app bundles."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "brand" / filename
