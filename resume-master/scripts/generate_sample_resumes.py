#!/usr/bin/env python3
"""Generate a synthetic resume set for demoing the pipeline.

Creates ~50 resumes (PDF, DOCX, TXT) covering every important path:
eligible strong/medium candidates, non-Python, non-AI, thin wrappers,
tutorial-style projects, unreadable files, duplicates, and no-GitHub cases.

    python scripts/generate_sample_resumes.py --out ./resumes --count 50
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

from fpdf import FPDF

FIRST = ["Asha", "Rohan", "Meera", "Daniel", "Priya", "Lukas", "Sara", "Tomás",
         "Nadia", "Wei", "Jonas", "Amara", "Ivan", "Yuki", "Carlos", "Zara",
         "Ethan", "Leila", "Marco", "Ananya", "Felix", "Grace", "Hassan",
         "Ingrid", "Javier", "Kavya", "Liam", "Mira", "Noah", "Olga"]
LAST = ["Rao", "Mehta", "Nair", "Okafor", "Sharma", "Weber", "Haddad", "Silva",
        "Novak", "Chen", "Berg", "Diallo", "Petrov", "Tanaka", "Romero",
        "Ahmed", "Cole", "Karim", "Bianchi", "Iyer", "Braun", "Liu", "Aziz",
        "Larsen", "Ortiz", "Menon", "Doherty", "Sato", "Kim", "Volkov"]

GITHUB_USER = [
    # Real, active public profiles -> exercises live enrichment in the demo.
    "simonw", "fchollet", "mitsuhiko",
    # Synthetic handles -> most will 404, exercising the not-found path.
    "coderao", "amehta-dev", "mnair-labs", "dokaidesign", "priyash-codes",
    "lweber-git", "sara-ml", "nnovak-ai", "weichen-dev",
]
REAL_GITHUB_PREFIXES = 3  # first N entries in GITHUB_USER are real profiles

DOMAINS = ["email.com", "mailbox.dev", "inbox.io", "mail.test"]


def _contact(i: int) -> tuple[str, str, str, str]:
    name = f"{FIRST[i % len(FIRST)]} {LAST[(i * 7) % len(LAST)]}"
    email = f"{FIRST[i % len(FIRST)].lower()}.{LAST[(i * 7) % len(LAST)].lower()}{i}@{DOMAINS[i % len(DOMAINS)]}"
    phone = f"+91 98{i:03d} {10000 + i:05d}"
    github = (
        f"github.com/{GITHUB_USER[i % len(GITHUB_USER)]}"
        if i < REAL_GITHUB_PREFIXES or i >= len(GITHUB_USER)
        else f"github.com/{GITHUB_USER[i % len(GITHUB_USER)]}{i}"
    )
    return name, email, phone, github


# --- resume body templates ------------------------------------------------- #
# Each returns the section text given candidate index.

def body_strong_ai(i: int) -> str:
    return f"""SUMMARY
SDE intern candidate with strong Python fundamentals and hands-on agentic-system
builds. Comfortable owning features end-to-end from API to deployment.

SKILLS
Languages: Python 3.11, TypeScript, SQL
Backend: FastAPI, Django, Flask, asyncio, PostgreSQL, Redis, SQLAlchemy
AI: LangChain, LangGraph, LlamaIndex, RAG, embeddings, vector search, tool-calling agents, OpenAI, evaluation pipelines
Cloud: GCP, Docker, GitHub Actions, CI/CD
Frontend: React, Next.js (supporting)
Testing: pytest, unit tests, integration tests, test coverage

PROJECTS
{chr(8226)} Stateful RAG Assistant with LangGraph Agents
- Built a multi-agent workflow in Python using LangGraph with checkpointed state, tool calling and human-in-the-loop review.
- Implemented retrieval-augmented generation over a chunked document store with embeddings in pgvector, plus a reranking step.
- Added an evaluation pipeline (ragas-style metrics) tracking faithfulness on a labeled dev set; regression suite runs in CI with pytest.
- Exposed the workflow through FastAPI endpoints with async streaming, structured logging and Redis-backed response caching.
- Deployed on GCP Cloud Run with Docker; GitHub Actions handles build, lint and integration tests.

{chr(8226)} Multi-Agent Research Orchestrator
- Orchestrated supervisor + worker agents (LangChain tools) to plan, search and synthesize reports with retry/fallback handling.
- Built data ingestion pipeline parsing PDFs and HTML, chunking, embedding and indexing into a vector store.

EXPERIENCE
Software Engineering Intern, Finlytics (Jun 2024 - Feb 2025)
- Developed async FastAPI services backing a React dashboard; PostgreSQL schema design and Redis caching cut p95 latency by 40%.
- Wrote unit and integration tests (pytest, coverage gates), added structured logging and Prometheus metrics for observability.
- Containerized services with Docker and shipped to GCP via GitHub Actions CI/CD.

EDUCATION
B.Tech Computer Science, 2025
"""


def body_medium(i: int) -> str:
    return f"""SUMMARY
Final-year CS student who likes shipping Python services and tinkering with LLM apps.

SKILLS
Python, FastAPI, Flask, PostgreSQL, Redis, Docker, SQLAlchemy
Machine Learning: LangChain, RAG, embeddings, Hugging Face, PyTorch
GCP, GitHub Actions, React, Next.js, pytest

PROJECTS
- AI Document Q&A API: FastAPI service that answers questions over uploaded PDFs using RAG with embeddings and a vector store; includes chunking, caching and unit tests with pytest.
- Course Manager: Django + PostgreSQL REST API with token auth, deployed with Docker on GCP; React frontend in Next.js.
- Twitter Sentiment Dashboard: PyTorch model plus Flask dashboard; added simple evaluation metrics and error handling.

EXPERIENCE
Backend Intern, QuickCart (Jan 2024 - May 2024)
- Built REST endpoints in Flask, wrote integration tests, and added Redis caching for product search.
- Deployed services with Docker Compose; monitored logs with structured logging.

EDUCATION
B.S. Information Technology, 2025
"""


def body_no_python(i: int) -> str:
    return """SUMMARY
Full-stack engineer focused on web platforms and mobile experiences.

SKILLS
Java, Spring Boot, Hibernate, MySQL
JavaScript, React, Next.js, Node.js, Express, TypeScript
MongoDB, Docker, AWS, GitHub Actions

PROJECTS
- E-commerce Platform: Spring Boot REST API with JWT auth and React storefront; deployed on AWS EC2 with Docker.
- Realtime Chat App: Node.js + WebSocket server with Redis pub/sub; Next.js client with typing indicators.

EXPERIENCE
Software Intern, WebWorks (Feb 2024 - Jul 2024)
- Implemented Java microservices with Spring Boot and wrote JUnit tests.
- Built React components for the admin console and wired CI with GitHub Actions.

EDUCATION
B.Tech Software Engineering, 2025
"""


def body_no_ai(i: int) -> str:
    return """SUMMARY
Backend developer with solid Python and API experience, mostly CRUD systems.

SKILLS
Python, Django, FastAPI, Flask, PostgreSQL, Redis, Celery, Docker, pytest
JavaScript, React (basic)

PROJECTS
- Inventory API: FastAPI + PostgreSQL service with role-based auth, background jobs via Celery and Redis queues; pytest suite with 80% coverage.
- Blog Platform: Django app with SSR, full-text search and caching; deployed with Docker.

EXPERIENCE
Backend Intern, LogiTrack (Mar 2024 - Aug 2024)
- Designed REST endpoints and PostgreSQL schemas; added Redis caching and retry logic for webhook deliveries.

EDUCATION
B.E. Computer Engineering, 2025
"""


def body_thin_wrapper(i: int) -> str:
    return f"""SUMMARY
Curious student exploring generative AI and modern web stacks.

SKILLS
Python, JavaScript, React, Next.js, Node.js, Tailwind CSS
OpenAI API, LangChain (basics), GPT-4, prompt engineering, GitHub

PROJECTS
- ChatBot: used the OpenAI API to build a chatbot with a simple web UI in React. Users type a message and get a GPT-4 reply.
- Personal Portfolio: Next.js portfolio site with a contact form.

EDUCATION
B.Sc Computer Science, 2025
github.com/{GITHUB_USER[i % len(GITHUB_USER)]}-thin
"""


def body_tutorial(i: int) -> str:
    return f"""SUMMARY
Learning AI by building projects from courses and tutorials.

SKILLS
Python, OpenAI API, Streamlit, pandas, Git

PROJECTS
- AI Summarizer: followed a tutorial to make an article summarizer with the OpenAI API; replicated the video step by step.
- YouTube title generator (course project): called the API with a prompt template in Streamlit.

EDUCATION
B.Sc Data Science, 2025
github.com/{GITHUB_USER[i % len(GITHUB_USER)]}-tut
"""


def body_ml_only(i: int) -> str:
    return """SUMMARY
Aspiring ML engineer graduating next year.

SKILLS
Python, PyTorch, TensorFlow, scikit-learn, pandas, NumPy, Jupyter
SQL, Git

PROJECTS
- Leaf Disease Classifier: trained CNN models in PyTorch with data augmentation; evaluated with accuracy and confusion matrices.
- Housing Price Model: regression pipeline with feature engineering in scikit-learn and cross-validation.

EXPERIENCE
ML Intern, AgriSense (May 2024 - Aug 2024)
- Trained and evaluated image classification models; wrote training scripts and experiment tracking.

EDUCATION
B.Tech Artificial Intelligence, 2025
"""


def body_js_ai(i: int) -> str:
    return """SUMMARY
TypeScript developer building LLM-powered products on the web.

SKILLS
TypeScript, JavaScript, React, Next.js, Node.js, Express
LangChain.js, OpenAI API, Pinecone, Vector search, Vercel

PROJECTS
- AI Writing Assistant: Next.js app using LangChain.js with retrieval over indexed docs in Pinecone and streaming responses.
- Prompt Playground: Node.js service wrapping the OpenAI API with rate limiting and usage analytics.

EXPERIENCE
Frontend Intern, Promptly (Jan 2024 - Jun 2024)
- Built React interfaces for LLM features and typed API clients in TypeScript.

EDUCATION
B.S. Computer Science, 2025
"""


BODIES = [
    ("strong_ai", body_strong_ai, "pdf"),
    ("strong_ai", body_strong_ai, "pdf"),
    ("medium", body_medium, "pdf"),
    ("medium", body_medium, "docx"),
    ("no_python", body_no_python, "pdf"),
    ("no_ai", body_no_ai, "pdf"),
    ("thin_wrapper", body_thin_wrapper, "pdf"),
    ("tutorial", body_tutorial, "txt"),
    ("ml_only", body_ml_only, "pdf"),
    ("js_ai", body_js_ai, "pdf"),
]


def compose(i: int, kind: str, builder, with_github: bool = True) -> str:
    name, email, phone, github = _contact(i)
    header = (
        f"{name}\nSDE Intern Candidate | {email} | {phone}\n"
        f"{github if with_github else 'GitHub: private'}\n"
        f"linkedin.com/in/{name.lower().replace(' ', '-')}\n\n"
    )
    return header + builder(i)


def write_pdf(text: str, path: Path) -> None:
    from fpdf.enums import XPos, YPos

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in text.splitlines():
        safe = line.encode("latin-1", errors="replace").decode("latin-1")
        pdf.multi_cell(w=0, h=5, text=safe or " ",
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.output(str(path))


def write_docx(text: str, path: Path) -> None:
    import docx
    document = docx.Document()
    for line in text.splitlines():
        document.add_paragraph(line)
    document.save(str(path))


def write_txt(text: str, path: Path) -> None:
    path.write_text(text, encoding="utf-8")


WRITERS = {"pdf": write_pdf, "docx": write_docx, "txt": write_txt}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="./resumes")
    parser.add_argument("--count", type=int, default=50)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)

    written = 0
    i = 0
    while written < args.count:
        kind, builder, fmt = BODIES[i % len(BODIES)]
        # ~20% of candidates have no/hidden GitHub
        with_github = (i % 5) != 4
        text = compose(i, kind, builder, with_github=with_github)
        name = f"candidate_{i + 1:02d}_{kind}.{fmt}"
        WRITERS[fmt](text, out / name)
        written += 1
        i += 1

    # Edge cases that must not crash the batch ------------------------------ #
    # 1. Corrupt/unreadable PDF
    (out / "candidate_edge_corrupt.pdf").write_bytes(b"%PDF-1.4 broken garbage \x00\x01\x02")
    # 2. Empty text file
    (out / "candidate_edge_empty.txt").write_text("   \n", encoding="utf-8")
    # 3. Duplicate of candidate_01 (byte-identical copy)
    first_pdf = sorted(out.glob("candidate_01_*.pdf"))
    if first_pdf:
        (out / "candidate_edge_duplicate.pdf").write_bytes(first_pdf[0].read_bytes())
    # 4. Unsupported extension (should be counted, not crash)
    (out / "candidate_edge_notes.md").write_text("# notes\nnot a resume\n", encoding="utf-8")

    print(f"Generated {len(list(out.iterdir()))} files in {out}")


if __name__ == "__main__":
    main()
