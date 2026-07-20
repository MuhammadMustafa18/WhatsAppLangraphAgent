"""Entry point for PyInstaller-bundled backend.
Starts the FastAPI app on the given port. Runs Alembic migrations on first launch."""
import os
import sys
from pathlib import Path

import uvicorn
from alembic.config import Config as AlembicConfig
from alembic import command as alembic_command
from app.core.config import get_settings, default_app_data_dir


def _run_migrations() -> None:
    """Run Alembic upgrades synchronously before the async event loop starts."""
    settings = get_settings()
    data_dir = (
        Path(settings.APP_DATA_DIR) if settings.APP_DATA_DIR else default_app_data_dir()
    )
    data_dir.mkdir(parents=True, exist_ok=True)

    # Locate alembic.ini — in dev mode next to project root, in PyInstaller
    # bundle under sys._MEIPASS.
    bundle_dir = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    alembic_ini = bundle_dir / "alembic.ini"
    if not alembic_ini.exists():
        print("[backend] alembic.ini not found — skipping migrations")
        return

    cfg = AlembicConfig(str(alembic_ini))
    cfg.set_main_option("script_location", str(bundle_dir / "alembic"))
    # Point at the same DB the app will use
    url = get_settings().DATABASE_URL.replace("+aiosqlite", "")
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        relative = url.replace("sqlite:///", "", 1)
        full = (data_dir / relative).resolve()
        full.parent.mkdir(parents=True, exist_ok=True)
        url = "sqlite://" + "/" + full.as_posix()
    cfg.set_main_option("sqlalchemy.url", url)

    try:
        alembic_command.upgrade(cfg, "head")
        print("[backend] Alembic migrations complete")
    except Exception as exc:
        print(f"[backend] Alembic upgrade failed: {exc}")


if __name__ == "__main__":
    _run_migrations()

    port = 18234
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 < len(sys.argv):
            port = int(sys.argv[idx + 1])
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
