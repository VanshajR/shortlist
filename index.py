"""Vercel entry point: Vercel finds `app` here and serves the bot's webhook with it."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "src"))

from shortlist.bot import app  # noqa: E402,F401
