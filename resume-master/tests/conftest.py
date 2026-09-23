"""Shared test fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from resume_screener.extraction import extract_candidate_info
from resume_screener.config import Settings


@pytest.fixture
def offline_settings() -> Settings:
    """Settings with network-dependent features disabled."""
    return Settings(llm_enabled=False, github_enabled=False)


STRONG_RESUME = """
Asha Rao
SDE Intern | asha@email.com | +91 98123 45678
github.com/coderao

SKILLS
Python, FastAPI, PostgreSQL, Redis, Docker, GCP, pytest, LangGraph, LangChain, RAG

PROJECTS
- Stateful RAG Assistant
- Built a multi-agent workflow with LangGraph: retrieval, embeddings, tool calling and checkpointed state.
- Evaluation pipeline with ragas metrics; FastAPI async endpoints, Redis caching, deployed on GCP Cloud Run with Docker.

EXPERIENCE
Backend Intern at Finlytics
- Developed async FastAPI services with pytest integration tests and structured logging.
"""

NO_PYTHON_RESUME = """
Jon Kim
jon@email.com

SKILLS
Java, Spring Boot, JavaScript, React, Next.js, MySQL

PROJECTS
- E-commerce platform in Spring Boot with React storefront, JWT auth.
"""

NO_AI_RESUME = """
Priya Shah
priya@email.com

SKILLS
Python, Django, FastAPI, PostgreSQL, Redis, Docker, pytest

PROJECTS
- Inventory API: FastAPI + PostgreSQL with role auth, Celery background jobs and pytest coverage.
"""

THIN_WRAPPER_RESUME = """
Evan Cole
evan@email.com
github.com/evan-thin

SKILLS
Python, OpenAI API, React

PROJECTS
- ChatBot: used the OpenAI API to build a chatbot with a React UI. Simple chatbot calling the API.
"""


@pytest.fixture
def strong_info():
    return extract_candidate_info(STRONG_RESUME)


@pytest.fixture
def no_python_info():
    return extract_candidate_info(NO_PYTHON_RESUME)


@pytest.fixture
def no_ai_info():
    return extract_candidate_info(NO_AI_RESUME)


@pytest.fixture
def thin_wrapper_info():
    return extract_candidate_info(THIN_WRAPPER_RESUME)
