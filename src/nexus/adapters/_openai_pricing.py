"""OpenAI model pricing table for cost estimation.

Prices are per 1M tokens in USD. Verify against https://openai.com/api/pricing/
before each release — these can change.

OpenAI usage objects return token counts but NOT cost, so we compute locally.
CostEventCreate.cost_source should be "estimated" for all OpenAI adapter costs.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# (input $/1M tokens, output $/1M tokens) — current as of 2026-04
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "o1": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    "o3": (2.00, 8.00),
    "o3-mini": (1.10, 4.40),
    "o4-mini": (1.10, 4.40),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return estimated cost in USD for the given token counts.

    Returns 0.0 for unknown models and logs a warning — callers must not
    treat silence as zero cost; log the model name for audit purposes.
    """
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        logger.warning("Unknown OpenAI model for pricing; cost set to 0.0 (model=%s)", model)
        return 0.0
    in_price, out_price = pricing
    return (input_tokens * in_price + output_tokens * out_price) / 1_000_000
