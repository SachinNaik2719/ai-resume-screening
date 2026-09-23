"""Smoke-test the LLM adapter against the configured endpoint (dev helper)."""
import sys

sys.path.insert(0, "src")

from resume_screener.config import load_settings
from resume_screener.models import LLMScore
from resume_screener.scoring.llm_client import LLMClient

settings = load_settings()
print("llm_available:", settings.llm_available,
      "| model:", settings.llm_model,
      "| base:", settings.llm_base_url)

client = LLMClient(settings)
prompt = (
    'Score this resume for AI project depth (cap 40). Return ONLY JSON: '
    '{"ai_project_depth":{"score":0,"evidence":[]},"python_backend":{"score":0,'
    '"evidence":[]},"cloud_fullstack":{"score":0,"evidence":[]},'
    '"engineering_depth":{"score":0,"evidence":[]},"penalty":0,'
    '"penalty_reason":null,"project_summary":"...","strengths":[],"concerns":[]} '
    'Resume: Python dev, built a RAG pipeline with LangGraph agents, '
    'FastAPI backend, Docker on GCP.'
)
outcome = client.complete_json(prompt, LLMScore)
print("ok:", outcome.ok, "| error:", outcome.error)
if outcome.ok:
    print("ai score:", outcome.value.ai_project_depth.score)
    print("evidence:", outcome.value.ai_project_depth.evidence[:2])
    print("summary:", outcome.value.project_summary)
