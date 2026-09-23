"""AI Resume Screening & Ranking System.

Pipeline: parse -> extract -> rule-based eligibility -> scoring
(rule-based baseline + optional LLM judgment) -> GitHub enrichment -> ranked JSON.
"""

__version__ = "1.0.0"
