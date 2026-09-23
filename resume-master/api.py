"""Optional FastAPI wrapper around the pipeline (bonus).

    uvicorn api:app --reload
    POST /screen   {"input_dir": "./resumes"}  -> runs the pipeline
    GET  /results                               -> returns last results.json
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent / "src"))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from resume_screener.config import load_settings
from resume_screener.pipeline import run_pipeline
from resume_screener.report import write_json

app = FastAPI(title="AI Resume Screener", version="1.0.0")

DEFAULT_OUTPUT = Path("./output/results.json")


class ScreenRequest(BaseModel):
    input_dir: str = Field(..., description="Directory containing resume files")
    use_llm: bool = True
    use_github: bool = True


@app.post("/screen")
def screen(request: ScreenRequest) -> dict[str, Any]:
    settings = load_settings()
    if not request.use_llm:
        settings = settings.without_llm()
    if not request.use_github:
        settings = settings.without_github()
    try:
        results = run_pipeline(request.input_dir, settings)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    write_json(results, DEFAULT_OUTPUT)
    return results.model_dump()


@app.get("/results")
def results() -> dict[str, Any]:
    if not DEFAULT_OUTPUT.exists():
        raise HTTPException(status_code=404, detail="no results yet; POST /screen first")
    import json
    return json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
