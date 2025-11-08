from __future__ import annotations

import tiktoken

from config.settings import settings

_ENC = tiktoken.encoding_for_model(settings.models.chat)


def count_tokens(text: str) -> int:
    """Return approximate token count for a string."""
    return len(_ENC.encode(text or ""))
