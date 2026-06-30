"""Prompt construction and response parsing for model-based advisors.

Pure functions: a scenario dictionary becomes a deterministic prompt, and a model
reply becomes a structured recommendation. No network here; the collector script
owns the call and the cache. Parsing is strict and raises on malformed output
rather than guessing, so a bad reply is visible instead of silently dropped.

Three prompt arms isolate where an advisor fails. "bare" states the task and the
response format only. "policy" adds the operational rules as text. "scaffold"
adds the fee arithmetic already computed, so the model reasons about selection
instead of doing the arithmetic that language models are unreliable at.
"""

from __future__ import annotations

import json
import math
from typing import Any

from arenawealth.fee_contract import (
    FEE_PER_TRANCHE,
    MIN_ORDER_AMOUNT,
    TRANCHE_SIZE,
    order_fee,
)

PROMPT_ARMS = ("bare", "policy", "scaffold")


def build_prompt(scenario: dict[str, Any], arm: str = "policy") -> str:
    """Render a scenario into a deterministic advisor prompt for one prompt arm."""
    if arm not in PROMPT_ARMS:
        raise ValueError(f"unknown prompt arm: {arm!r}; expected one of {PROMPT_ARMS}")
    lines = _context_lines(scenario)
    if arm == "policy":
        lines.extend(_policy_rule_lines(scenario))
        lines.append(_fee_policy_line())
    elif arm == "scaffold":
        lines.extend(_policy_rule_lines(scenario))
        lines.append(_fee_scaffold_line(scenario))
    lines.append(_response_format_line(scenario))
    return "\n".join(lines)


def _context_lines(scenario: dict[str, Any]) -> list[str]:
    """Task framing and the frozen inputs, shared by every arm."""
    allowed = ", ".join(scenario["allowed_tickers"])
    owned = ", ".join(scenario["owned_tickers"])
    facts = ", ".join(scenario.get("available_fact_ids", ())) or "none"
    return [
        "You are an investment assistant proposing additions to an existing equity portfolio.",
        f"Cash available: USD {scenario['cash']:.2f}.",
        f"Allowed universe: {allowed}.",
        f"Already owned: {owned}.",
        f"Recommend at most {scenario['max_recommendations']} tickers.",
        f"Facts you may cite: {facts}.",
    ]


def _policy_rule_lines(scenario: dict[str, Any]) -> list[str]:
    """Operational rules stated as text, omitted by the bare arm."""
    if scenario.get("add_only", True):
        ownership_rule = "Do not recommend already-owned tickers."
    else:
        ownership_rule = (
            "You may recommend already-owned tickers when they are in the allowed universe."
        )
    return [ownership_rule, "Cite only fact ids provided."]


def _fee_policy_line() -> str:
    """Fee rule without scenario-specific arithmetic, used by the policy arm."""
    return (
        f"The fee is USD {FEE_PER_TRANCHE:.2f} per started USD "
        f"{TRANCHE_SIZE:.0f} tranche, and the minimum economic order is USD "
        f"{MIN_ORDER_AMOUNT:.2f}. Deploy in the fewest tranches; do not split "
        "unless it is fee-neutral."
    )


def _fee_scaffold_line(scenario: dict[str, Any]) -> str:
    """Pre-computed fee arithmetic, added only by the scaffold arm."""
    cash = scenario["cash"]
    half = cash / 2.0
    single_fee = order_fee(cash)
    split_fee = order_fee(half) + order_fee(cash - half)
    return (
        "Fee arithmetic (already computed for you): a single order deploying your "
        f"USD {cash:.2f} pays USD {single_fee:.2f}; splitting it into two equal orders pays "
        f"USD {split_fee:.2f}. The fee is USD {FEE_PER_TRANCHE:.2f} per started USD "
        f"{TRANCHE_SIZE:.0f} tranche, and the minimum economic order is USD "
        f"{MIN_ORDER_AMOUNT:.2f}. Deploy in the fewest tranches; do not split unless it is "
        "fee-neutral."
    )


def _response_format_line(scenario: dict[str, Any]) -> str:
    """The JSON response contract, shared by every arm so output stays parseable."""
    if scenario.get("amounts_required", False):
        amount_rule = 'Include an "amounts" array with one USD amount per ticker.'
    else:
        amount_rule = 'Do not include an "amounts" field unless explicitly required.'
    return (
        "Reply with one JSON object and nothing else, in the form "
        '{"tickers": ["AAA", "BBB"], "amounts": [500.0, 750.0], '
        '"cited_fact_ids": ["id1"]}. '
        f"{amount_rule}"
    )


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object found in model response")
    return text[start : end + 1]


def parse_response(text: str) -> dict[str, tuple[str, ...] | tuple[float, ...]]:
    """Parse a model reply into normalized tickers and cited fact ids.

    Raises ValueError if the reply has no JSON object or no ticker list, so an
    unusable response is recorded as a parse failure rather than an empty pick.
    """
    payload = json.loads(_extract_json_object(text))
    if not isinstance(payload, dict):
        raise ValueError("model response must be a JSON object")
    if not isinstance(payload.get("tickers"), list):
        raise ValueError("model response has no 'tickers' list")
    if not all(isinstance(item, str) for item in payload["tickers"]):
        raise ValueError("model response 'tickers' must contain only strings")
    tickers = tuple(item.strip().upper() for item in payload["tickers"] if item.strip())
    cited = payload.get("cited_fact_ids", [])
    if not isinstance(cited, list) or not all(isinstance(item, str) for item in cited):
        raise ValueError("model response 'cited_fact_ids' must be a list of strings")
    cited_fact_ids = tuple(item.strip() for item in cited if item.strip())
    raw_amounts = payload.get("amounts", [])
    if not isinstance(raw_amounts, list) or any(
        isinstance(item, bool) or not isinstance(item, (int, float))
        for item in raw_amounts
    ):
        raise ValueError("model response 'amounts' must be a list of numbers")
    amounts = tuple(float(item) for item in raw_amounts)
    if not all(math.isfinite(amount) for amount in amounts):
        raise ValueError("model response 'amounts' must be finite")
    return {"tickers": tickers, "amounts": amounts, "cited_fact_ids": cited_fact_ids}
