"""Slidepilot backend. Importing the package loads backend/.env.local, then backend/.env."""

from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_DIR / ".env.local")
load_dotenv(_BACKEND_DIR / ".env")
