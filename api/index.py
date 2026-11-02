"""Vercel serverless entry point.

Exposes the FastAPI application from web_app/server.py as an ASGI app so the
Vercel Python runtime can serve it. All requests are rewritten here by
vercel.json.
"""

from web_app.server import app
