"""Unit tests for OpenAI model pricing table and cost estimator."""

from __future__ import annotations

from nexus.adapters._openai_pricing import MODEL_PRICING, estimate_cost


class TestEstimateCost:
    def test_known_model_correct_cost(self) -> None:
        """gpt-4o: 1000 input + 500 output → verified calculation."""
        # gpt-4o: $2.50/1M in, $10.00/1M out
        cost = estimate_cost("gpt-4o", input_tokens=1000, output_tokens=500)
        expected = (1000 * 2.50 + 500 * 10.00) / 1_000_000
        assert abs(cost - expected) < 1e-9

    def test_unknown_model_returns_zero(self) -> None:
        """Unknown model name → returns 0.0 without raising."""
        cost = estimate_cost("unknown-model-xyz", input_tokens=500, output_tokens=200)
        assert cost == 0.0

    def test_zero_tokens_returns_zero(self) -> None:
        """Zero input and output tokens → 0.0 regardless of model."""
        cost = estimate_cost("gpt-4o-mini", input_tokens=0, output_tokens=0)
        assert cost == 0.0

    def test_all_models_have_positive_prices(self) -> None:
        """Every entry in MODEL_PRICING has two positive floats."""
        for model, (in_price, out_price) in MODEL_PRICING.items():
            assert in_price > 0, f"{model}: input price must be positive"
            assert out_price > 0, f"{model}: output price must be positive"
            assert out_price >= in_price, f"{model}: output price should be >= input price"
