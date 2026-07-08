"""Route modules for the API, grouped by concern.

Each module exposes an ``APIRouter`` named ``router``; ``src.api`` includes them
onto the app. Splitting by concern keeps each file small and the app assembly
readable — see ``src/api/__init__.py``.
"""
