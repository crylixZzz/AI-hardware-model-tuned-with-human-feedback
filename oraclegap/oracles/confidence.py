"""Model-confidence oracle.

Two signals: the verbalized self-estimate the model is prompted to emit (0-100) and
an aggregate of token-level logprobs where the API exposes them. Both are captured at
generation time; this module holds the parsing and aggregation so generation and the
oracle step agree on how a number is derived.
"""

from __future__ import annotations

import re
from typing import Optional

_VERBALIZED = re.compile(r"CONFIDENCE\s*[:=]\s*([0-9]{1,3}(?:\.[0-9]+)?)", re.IGNORECASE)


def parse_verbalized_confidence(raw_output: str) -> Optional[float]:
    """Pull the structured ``CONFIDENCE: NN`` field the generation prompt asks for.
    Returns None when the model omitted it, which is itself signal and is stored as
    missing rather than imputed."""
    match = _VERBALIZED.search(raw_output)
    if match is None:
        return None
    value = float(match.group(1))
    return min(100.0, max(0.0, value))


def aggregate_logprobs(token_logprobs: list[float]) -> Optional[float]:
    """Mean per-token logprob of the extracted code: a length-normalized proxy for how
    confident the decoder was. None when the API returned no logprobs."""
    if not token_logprobs:
        return None
    return sum(token_logprobs) / len(token_logprobs)
