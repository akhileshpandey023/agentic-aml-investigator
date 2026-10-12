RISK_BANDS = """\
Risk scoring bands (risk_score is 0-100; use these exact thresholds):
- 0-24  -> risk_level "low",      recommended_action "clear"
- 25-49 -> risk_level "medium",   recommended_action "clear"
- 50-69 -> risk_level "medium",   recommended_action "escalate"
- 70-89 -> risk_level "high",     recommended_action "escalate"
- 90-100 -> risk_level "critical", recommended_action "file_sar"

A confirmed sanctions-list match (any EntityMatch with match_score >= 90) \
puts the floor of risk_score at 70, regardless of adverse media or \
regulatory findings. Adverse media alone, with no sanctions match, should \
rarely exceed risk_score 60 unless the narrative directly describes \
financial crime (not merely being named in a notice as a counterparty).
"""