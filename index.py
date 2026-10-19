"""Vercel entry point: Vercel serves the module-level `app` (the service itself uses the create_app factory)."""

from app.main import create_app

app = create_app()
