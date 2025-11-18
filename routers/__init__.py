# Re-export routers so app.py can import everything from one place.
from . import auth, audio, chat, documents, memory, search, sessions, system  # noqa: F401
