# AI Resume Screening & Ranking System

Production-minded pipeline that ingests a folder of ~50 resumes, hard-filters
candidates against minimum Python/AI requirements, scores eligible candidates
on a 100-point rubric (rule-based baseline + optional LLM judgment), enriches
the score with public GitHub activity, and writes a ranked, fully explainable
`results.json`.

```
resumes/*.pdf|docx|txt
        │
        ▼
 ┌─────────────┐   ┌──────────────┐   ┌──────────────────┐   ┌──────────────┐
 │ parse        │ → │ rule-based   │ → │ scoring          │ → │ GitHub       │
 │ (pypdf/docx) │   │ eligibility  │   │ rules + LLM      │   │ enrichment   │
 │ failures OK  │   │ (never LLM)  │   │ blended, capped  │   │ 0-10, fault  │
 └─────────────┘   └──────────────┘   └──────────────────┘   │ tolerant     │
                                                              └──────┬───────┘
                                                                     ▼
                                              ranked JSON + CSV + terminal report
```

## Setup

```bash
python -m venv .venv && .venv\Scripts\activate   # or: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                           # then fill in your keys
```

`.env` (never committed):

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Enables LLM-assisted scoring (any OpenAI-compatible key works) |
| `LLM_BASE_URL` | Defaults to Gemini's OpenAI-compatible endpoint |
| `LLM_MODEL` | Defaults to `gemini-2.5-flash` |
| `GITHUB_TOKEN` | Optional; raises GitHub API rate limits |
| `LLM_ENABLED` / `GITHUB_ENABLED` | Kill switches for either stage |
| `MAX_WORKERS` | Bounded concurrency for LLM/GitHub calls |

## Run

```bash
# CLI (primary interface)
python main.py --input ./resumes --output ./output/results.json --csv ./output/results.csv

# Force deterministic scoring / skip network stages
python main.py --input ./resumes --no-llm --no-github

# Optional FastAPI interface
uvicorn api:app --reload
#   POST /screen   {"input_dir": "./resumes"}
#   GET  /results
```

No key configured? The run still completes with **rule-based scoring only**
(`scoring_method: "rule_based"`) — the LLM is an enhancement, never a single
point of failure.

## Generate the demo resume set

```bash
python scripts/generate_sample_resumes.py --out ./resumes --count 50
```

Creates 50 synthetic resumes (PDF/DOCX/TXT) covering every path: strong AI
candidates, medium candidates, non-Python, non-AI, thin LLM wrappers,
tutorial-style projects, ML-only, JS+AI, missing GitHub, plus edge cases
(corrupt PDF, empty file, byte-identical duplicate, unsupported extension).

## Output

`output/results.json`:

```jsonc
{
  "batch_summary": { "total_files": 54, "parsed_ok": 50, "eligible": 35,
                     "rejected": 17, "parse_failures": 2, "duplicates_skipped": 1,
                     "llm_calls_ok": 0, "llm_calls_failed": 0,
                     "scoring_method": "rule_based" },
  "results": [            // ranked eligible candidates, highest first
    { "rank": 1, "candidate_name": "...", "eligible": true, "total_score": 89,
      "score_breakdown": { "ai_project_depth": 40, "python_backend": 29,
                            "cloud_fullstack": 15, "github": 5,
                            "engineering_depth": 5, "penalty": 0 },
      "matched_skills": ["..."], "project_summary": "...",
      "github_summary": "@simonw: 42 public events in last 90d; ...",
      "strengths": ["..."], "concerns": ["..."],
      "evidence": { "ai_project_depth": ["[projects] LangGraph (+5.0)", "..."] },
      "scoring_method": "hybrid_llm" }
  ],
  "rejected": [ { "eligible": false,
                  "rejection_reasons": ["No evidence of Python stack"], ... } ]
}
```

Every score carries an `evidence` array showing which resume section earned
which points — the run is fully explainable.

## Tests

```bash
python -m pytest tests/ -q
```

31 tests cover eligibility (the 25%-weighted rubric area), scoring caps and
penalties, LLM fallback, GitHub math, extraction across layouts, and batch
resilience (corrupt/empty/duplicate files).

---

## Design Decisions

**Filtering strategy.** Eligibility is deliberately *outside* the LLM, as the
spec requires: two independent rule checks — (1) Python evidence must appear in
a genuine context (skills / projects / experience sections; a bare mention in
the objective prose does not count), and (2) at least one AI signal, where
*strong* tokens (LangChain, LangGraph, RAG, embeddings, tool-calling,
evaluation pipelines…) count anywhere in evidence sections, while *weak* generic
terms ("AI project") only count inside projects/experience. Both must pass.
JS/React/Java presence is never penalized on its own — it just doesn't help.

**Scoring strategy.** A deterministic baseline computes all five rubric
categories (40/30/15/10/5) from weighted keyword evidence: hits in
`projects` count 1.0×, `experience` 0.85×, `skills` only 0.5× — so a
framework name in a skills list can never equal demonstrated implementation.
AI depth adds bonuses for engineering markers *inside AI project blocks*
(retrieval, state, eval, orchestration, deploy…), which is what separates real
systems from wrappers. Penalties (−5 to −15) fire on thin-wrapper patterns
("used the OpenAI API to build a chatbot", no depth markers) and
tutorial-style projects; totals are clamped ≥ 0 and every category is capped
at its rubric maximum.

**LLM usage.** One small `LLMClient` adapter speaks the OpenAI-compatible
protocol (Gemini by default) so the provider can be swapped by changing two
env vars. The model returns a Pydantic-validated `LLMScore` (structured JSON:
per-category score + evidence quotes, penalty + reason, summary, strengths,
concerns). Its judgment is *blended* over the rule baseline at a configurable
weight (default 0.6), never replacing the caps — and the **stricter of the two
penalties wins**, so a lenient model can't wash out a quality red flag. Any
model failure falls back to the pure rule score for that one candidate and is
recorded in `errors[]`; hard eligibility never touches the model.

**GitHub scoring.** 0–5 recent activity (public events + repo pushes in the
last 90 days) + 0–5 maintained/relevant repos (non-fork, pushed in the last
year, Python/AI language/topics/description), capped at 10 per the rubric.
Username-level memoization means 50 resumes sharing handles cost only a
handful of API calls; missing/private profiles and rate limits return a status
string (`not_found` / `rate_limited`) instead of failing the batch, and the
run continues with `github: 0` for that candidate. Token comes from
`GITHUB_TOKEN` only.

**Reliability.** Every stage is failure-isolated: parse errors, duplicate
bytes (sha256), unsupported extensions, GitHub 403/404, and LLM timeouts each
annotate one candidate or one batch counter — never abort the run. Concurrency
is bounded (`MAX_WORKERS`) via `ThreadPoolExecutor` for enrichment and scoring.

## If I Had More Time

1. **Smarter parsing** — layout-aware section detection for real-world resumes
   (multi-column PDFs, tables, scanned files via OCR) instead of
   heading-line heuristics; add a small labeled fixture set of messy real
   resumes to regression-test extraction.
2. **Calibrated LLM scoring** — ask the model for a rubric-justified score
   *plus* a confidence estimate, then use confidence as the blend weight
   (currently a fixed 0.6); add a cache so the same resume never costs two
   model calls.
3. **Pairwise ranking** — replace pointwise scoring with an LLM
   judge doing pairwise comparisons on close candidates (±3 points), which
   ranks more reliably than absolute scores.
4. **Richer GitHub signal** — parse commit diffs/languages per repo, weight
   recency exponentially, and add ETag-based disk caching so re-runs are
   offline and free.
