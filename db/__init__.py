# Expose the SQLite connection helper at the package level.
from .sqlite import get_connection  # noqa: F401
