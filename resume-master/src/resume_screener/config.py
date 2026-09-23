"""Central configuration: thresholds, weights, model names, API keys.

All tunables live here (env-driven where appropriate) so business logic in
scoring/pipeline modules never hard-codes values or secrets.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv

# --- Score category ceilings (the 100-point rubric from the assignment) ---
SCORE_MAX: dict[str, int] = {
    "ai_project_depth": 40,
    "python_backend": 30,
    "cloud_fullstack": 15,
    "github": 10,
    "engineering_depth": 5,
}

# Project-quality penalties: -15 .. 0
PENALTY_MIN = -15
PENALTY_MAX = 0
THIN_WRAPPER_PENALTY = -10
TUTORIAL_PENALTY = -5

# How strongly the LLM judgment is blended over the rule-based baseline
# (0.0 = pure rules, 1.0 = pure LLM). Github stays rule/enrichment-only.
LLM_BLEND_WEIGHT = 0.6

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".text"}


@dataclass(frozen=True)
class Settings:
    # LLM
    llm_enabled: bool = True
    llm_api_key: str | None = None
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_model: str = "gemini-3.6-flash"
    llm_timeout: float = 30.0
    llm_blend_weight: float = LLM_BLEND_WEIGHT

    # GitHub
    github_enabled: bool = True
    github_token: str | None = None
    github_timeout: float = 10.0

    # Runtime
    max_workers: int = 4

    @property
    def llm_available(self) -> bool:
        return self.llm_enabled and bool(self.llm_api_key)

    @property
    def github_available(self) -> bool:
        return self.github_enabled

    def without_llm(self) -> "Settings":
        return replace(self, llm_enabled=False)

    def without_github(self) -> "Settings":
        return replace(self, github_enabled=False)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    """Build Settings from environment variables (.env is loaded if present)."""
    load_dotenv()
    api_key = (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or None
    )
    return Settings(
        llm_enabled=_env_bool("LLM_ENABLED", True),
        llm_api_key=api_key,
        llm_base_url=os.getenv(
            "LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"
        ),
        llm_model=os.getenv("LLM_MODEL", "gemini-3.6-flash"),
        llm_timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
        github_enabled=_env_bool("GITHUB_ENABLED", True),
        github_token=os.getenv("GITHUB_TOKEN") or None,
        github_timeout=float(os.getenv("GITHUB_TIMEOUT_SECONDS", "10")),
        max_workers=max(1, int(os.getenv("MAX_WORKERS", "4"))),
    )
