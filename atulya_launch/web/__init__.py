"""Web package for Atulya Launch hosting panel.

Exports the FastAPI app factory.
"""

from .app import create_app

__all__: list[str] = ["create_app"]
