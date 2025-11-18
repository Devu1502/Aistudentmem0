# Generate readable session identifiers for storage and logging.
from datetime import datetime
from uuid import uuid4


def generate_session_id() -> str:
    """Return a timestamp-prefixed random id string."""
    return datetime.utcnow().strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:8]
