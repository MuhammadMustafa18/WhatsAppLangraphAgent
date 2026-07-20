# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Recluze backend API binary."""

import os

# PyInstaller exec's the spec without __file__. Use CWD instead.
PROJECT_ROOT = os.getcwd()

block_cipher = None

a = Analysis(
    [os.path.join(PROJECT_ROOT, "scripts", "run_backend.py")],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        (os.path.join(PROJECT_ROOT, "alembic.ini"), "."),
        (os.path.join(PROJECT_ROOT, "alembic"), "alembic"),
    ],
    hiddenimports=[
        # Alembic (needed for auto-migration at startup)
        "alembic",
        "alembic.runtime.migration",
        "alembic.config",
        "alembic.script",
        "alembic.script.base",
        "alembic.ddl",
        "alembic.ddl.sqlite",
        # FastAPI / Starlette
        "fastapi",
        "starlette",
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.middleware",
        # ASGI
        "httpx",
        "httpx._transports.default",
        # SQLAlchemy
        "sqlalchemy",
        "sqlalchemy.ext.asyncio",
        "sqlalchemy.sql.default_comparator",
        "aiosqlite",
        # Auth
        "passlib",
        "passlib.handlers.bcrypt",
        "bcrypt",
        "jose",
        "jose.backends.cryptography",
        # LangGraph
        "langgraph",
        "langgraph.checkpoint",
        "langgraph.checkpoint.sqlite",
        "langchain_core",
        # PDF
        "fitz",
        "fitz.frontend",
        # Logging
        "structlog",
        "colorama",
        # Config
        "pydantic",
        "pydantic_settings",
        "dotenv",
        # Our own packages
        "app",
        "app.main",
        "app.graph",
        "app.state",
        "app.core",
        "app.core.config",
        "app.core.logging",
        "app.core.deps",
        "app.db",
        "app.db.engine",
        "app.db.models",
        "app.api",
        "app.api.auth",
        "app.api.personas",
        "app.api.providers",
        "app.schemas",
        "app.schemas.persona",
        "app.schemas.provider",
        "app.services",
        "app.services.auth_service",
        "app.services.persona_service",
        "app.services.provider_service",
        "app.repositories",
        "app.repositories.persona_repo",
        "app.repositories.provider_repo",
        "app.repositories.user_repo",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "cv2",
        "torch",
        "tensorflow",
        "notebook",
        "jupyter",
        "ipython",
        "setuptools._distutils",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="recluze-api",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
