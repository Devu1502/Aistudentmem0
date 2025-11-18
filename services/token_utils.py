# Helpers to consistently count tokens for LLM prompts.
from __future__ import annotations

import tiktoken

from config.settings import settings

# Build one encoder upfront for the target chat model.
_ENC = tiktoken.encoding_for_model(settings.models.chat)


# Quick wrapper so callers can estimate prompt size.
def count_tokens(text: str) -> int:
    """Return approximate token count for a string."""
    return len(_ENC.encode(text or ""))
