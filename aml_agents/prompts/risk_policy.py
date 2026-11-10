"""Risk policy text for the Risk Analyst and Critic prompts.

Rendered from aml_agents.policy and config so the prompt, the code that
enforces the policy, and the evaluation checks cannot disagree.
"""

from aml_agents import config
from aml_agents.policy import BANDS


def _band_line(low: int, high: int, level: str, action: str) -> str:
    span = f"{low}-{high}".ljust(6)
    return f'- {span} -> risk_level "{level}",'.ljust(40) + f' recommended_action "{action}"'


_BAND_LINES = "\n".join(_band_line(b.low, b.high, b.risk_level, b.recommended_action) for b in BANDS)

RISK_BANDS = f"""\
Risk scoring bands (risk_score is 0-100; use these exact thresholds):
{_BAND_LINES}

A confirmed sanctions-list match (any EntityMatch with match_score >= {config.SANCTIONS_CONFIRMED_MATCH_SCORE}) \
puts the floor of risk_score at {config.SANCTIONS_RISK_FLOOR}, regardless of adverse media or \
regulatory findings. Adverse media alone, with no sanctions match, should \
rarely exceed risk_score 60 unless the narrative directly describes \
financial crime (not merely being named in a notice as a counterparty).
"""
