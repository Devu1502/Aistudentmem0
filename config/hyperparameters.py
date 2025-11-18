# Tunable knobs that influence how much context gets fed to the LLM.
from __future__ import annotations

from dataclasses import dataclass
import os


# Keep context heuristics in one frozen dataclass for easy reuse.
@dataclass(frozen=True)
class ContextHyperParameters:
    document_limit: int = int(os.getenv("DOC_LIMIT", 5))
    memory_limit: int = int(os.getenv("MEMORY_LIMIT", 5))
    summary_limit: int = int(os.getenv("SUMMARY_LIMIT", 2))
    max_history_turns: int = int(os.getenv("HISTORY_TURNS", 4))
    summary_turn_interval: int = int(os.getenv("SUMMARY_TURN_INTERVAL", 2))
    summary_token_threshold: int = int(os.getenv("SUMMARY_TOKEN_THRESHOLD", 2000))


# Instantiate once so modules can pull shared limits.
hyperparams = ContextHyperParameters()
