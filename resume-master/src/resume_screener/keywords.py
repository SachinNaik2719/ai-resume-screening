"""Keyword / pattern vocabulary shared by eligibility and scoring.

Kept separate so tuning a keyword never touches scoring math or pipeline code.
Patterns are matched case-insensitively against resume text.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# Section headings (canonical name -> matching heading lines)
# Used by the sectionizer in extraction.py. Order matters: first match wins.
# --------------------------------------------------------------------------- #
SECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("skills", re.compile(
        r"^(?:technical\s+)?skills?(?:\s*(?:&|and|/)\s*(?:tools|technologies|stack))?"
        r"$|^tech(?:nical)?\s+stack$|^technologies$|^skills\s+&\s+tools$",
        re.I,
    )),
    ("projects", re.compile(
        r"^(?:personal\s+|key\s+|academic\s+|selected\s+|notable\s+|major\s+)?"
        r"projects?(?:\s+(?:section|work|and\s+achievements))?$|^capstones?$"
        r"|^portfolio$",
        re.I,
    )),
    ("experience", re.compile(
        r"^(?:work\s+|professional\s+|industry\s+|relevant\s+)?experience$"
        r"|^internships?$|^employment(?:\s+(?:history|details))?$"
        r"|^work\s+history$|^career\s+history$",
        re.I,
    )),
    ("education", re.compile(
        r"^education(?:\s+(?:background|qualifications))?$|^academics$"
        r"|^(?:academic\s+)?qualifications$",
        re.I,
    )),
    ("summary", re.compile(
        r"^(?:professional\s+|career\s+|personal\s+)?summary$|^objective$"
        r"|^profile$|^about(?:\s+me)?$|^overview$|^headline$",
        re.I,
    )),
    ("certifications", re.compile(
        r"^(?:certifications?|licenses?|awards?|honou?rs|achievements?)$"
        r"|^courses(?:work)?$|^training$",
        re.I,
    )),
]

# --------------------------------------------------------------------------- #
# Python evidence
# --------------------------------------------------------------------------- #
PYTHON_RE = re.compile(
    r"\bpython(?:\s*\d+(?:\.\d+)*(?:\s*(?:3\.\d+)?))?\b|\bpy(?:thon)?3?\b(?=\s*(?:,|/|&|and)\s*(?:fastapi|django|flask))",
    re.I,
)

# Sections where a keyword counts as *genuine* evidence (skill list, project
# tech, work tech). Summary/objective prose alone is not enough.
EVIDENCE_SECTIONS = ("skills", "projects", "experience")

# --------------------------------------------------------------------------- #
# AI / LLM / RAG / agentic evidence
# --------------------------------------------------------------------------- #
# Strong: distinctive enough that presence in ANY section (incl. skills list)
# counts as evidence of a framework/implementation.
AI_STRONG_TOKENS: dict[str, re.Pattern] = {
    "LangChain": re.compile(r"\blang\s?-?chain\b", re.I),
    "LangGraph": re.compile(r"\blang\s?-?graph\b", re.I),
    "LlamaIndex": re.compile(r"\bllama\s?-?index\b", re.I),
    "RAG": re.compile(r"\brag\b|retrieval[-\s]augmented", re.I),
    "embeddings/vector search": re.compile(
        r"\bembedd?ings?\b|vector\s+(?:search|store|database|db)|similarity\s+search",
        re.I,
    ),
    "tool-calling agent": re.compile(
        r"tool[-\s]?call|function[-\s]?call|tools?\s+calling", re.I
    ),
    "multi-agent": re.compile(r"multi[-\s]?agent|agent(?:ic)?\s+(?:workflow|swarm|orchestrat)", re.I),
    "agentic": re.compile(r"\bagentic\b|agent\s+orchestrat|\bagents?\b(?=.*(?:loop|graph|state))", re.I),
    "evaluation pipeline": re.compile(r"\beval(?:uation)?\s+(?:pipeline|framework|harness)|ragas|\bevals?\b", re.I),
    "LlamaIndex/Haystack/ADK": re.compile(
        r"\bhaystack\b|google\s+adk|\badk\b|semantic[-\s]?kernel|\bautogen\b|\bcrew\s?-?ai\b|\bmcp\b",
        re.I,
    ),
    "LLM frameworks": re.compile(
        r"\bllm\b|large\s+language\s+model|\bgpt-?\d*\b|\bopenai\b|\banthropic\b|\bclaude\b"
        r"|\bgemini\b|\bllama-?\d*\b|\bmistral\b|\bhugging\s?face\b|\bprompt\s+engine",
        re.I,
    ),
    "guardrails/agents framework": re.compile(r"\bguardrails?\b|lang\s?serve|\bllama\s?index\b", re.I),
}

# Weaker: generic ML/AI terms — only meaningful inside projects/experience
# (a bare "AI" in a summary is not an AI project).
AI_CONTEXT_TOKENS: dict[str, re.Pattern] = {
    "machine learning": re.compile(r"machine\s+learning|\bml\b(?=\s+(?:model|pipeline|project))", re.I),
    "deep learning": re.compile(r"deep\s+learning|neural\s+network|\bcnn\b|\brnn\b|\blstm\b", re.I),
    "NLP": re.compile(r"\bnlp\b|natural\s+language\s+(?:processing|understanding)", re.I),
    "computer vision": re.compile(r"computer\s+vision|\bobject\s+detection\b|\bopencv\b|\bimage\s+segmen", re.I),
    "PyTorch/TensorFlow": re.compile(r"\bpytorch\b|\btensorflow\b|\bkeras\b|\bscikit-?learn\b|\bsklearn\b", re.I),
    "fine-tuning": re.compile(r"fine[-\s]?tun|\blora\b|\bpeft\b|transfer\s+learning", re.I),
    "speech/vision multimodal": re.compile(r"multimodal|speech[-\s]?to[-\s]?text|text[-\s]?to[-\s]?speech|whisper", re.I),
}

# Engineering signals *inside an AI project block* that prove it is more than
# a thin API wrapper. Used by the penalty heuristic.
AI_DEPTH_MARKERS = re.compile(
    r"retriev|vector|embedd|chunk|ingest|rerank|state|memory|checkpoint"
    r"|evaluat|benchmark|dataset|crawl|pipeline|orchestrat|orchestration"
    r"|async|queue|celery|kafka|postgres|sql|database|auth|deploy|docker"
    r"|cache|stream|fallback|retry|observab|monitor|log\b|api\b|endpoint"
    r"|schema|validat|tool\s*call|function\s*call|workflow|graph\b",
    re.I,
)

THIN_WRAPPER_PATTERNS = re.compile(
    r"used\s+(?:the\s+)?(?:openai|anthropic|gemini|claude)\s+api\s+to\s+(?:build|make|create)"
    r"|simple\s+chat\s?bot|basic\s+chat\s?bot|wrapper\s+around"
    r"|called\s+(?:the\s+)?(?:openai\s+)?api"
    r"|\bchatbot\s+using\s+(?:just\s+)?(?:the\s+)?api\b",
    re.I,
)

TUTORIAL_PATTERNS = re.compile(
    r"followed\s+(?:a|the)\s+tutorial|youtube\s+(?:tutorial|video)"
    r"|clone\s+of\s+(?:the\s+)?|replicat(?:ed|ing)\s+(?:a\s+)?tutorial"
    r"|course\s+(?:project|assignment)|following\s+(?:a|the)\s+(?:course|tutorial)"
    r"|built\s+by\s+following",
    re.I,
)

# --------------------------------------------------------------------------- #
# Python & backend engineering
# --------------------------------------------------------------------------- #
BACKEND_TOKENS: dict[str, tuple[re.Pattern, int]] = {
    "FastAPI": (re.compile(r"\bfastapi\b", re.I), 6),
    "Django": (re.compile(r"\bdjango\b", re.I), 4),
    "Flask": (re.compile(r"\bflask\b", re.I), 4),
    "asyncio/async": (re.compile(r"\basyncio\b|\basync/await\b|\basynchronous\b|\basync\b", re.I), 4),
    "PostgreSQL": (re.compile(r"\bpostgres(?:ql)?\b|\bpsql\b", re.I), 4),
    "Redis": (re.compile(r"\bredis\b", re.I), 3),
    "SQLAlchemy/ORM": (re.compile(r"\bsqlalchemy\b|\borm\b", re.I), 2),
    "REST API": (re.compile(r"\brest(?:ful)?\s+(?:api|endpoint)s?\b|\bhttp\s+api\b|\bapi\s+endpoints?\b", re.I), 3),
    "Celery/queues": (re.compile(r"\bcelery\b|\brabbitmq\b|\bkafka\b|\bqueue[s]?\b|background\s+task", re.I), 3),
    "MongoDB": (re.compile(r"\bmongo(?:db)?\b", re.I), 2),
}

# --------------------------------------------------------------------------- #
# Cloud / full-stack
# --------------------------------------------------------------------------- #
CLOUD_TOKENS: dict[str, tuple[re.Pattern, int]] = {
    "GCP": (re.compile(r"\bgcp\b|google\s+cloud|cloud\s+run|cloud\s+functions?|app\s+engine|compute\s+engine", re.I), 5),
    "AWS": (re.compile(r"\baws\b|amazon\s+web\s+services|\bec2\b|\bs3\b|\blambda\b|\baws\s+lambda\b", re.I), 4),
    "Azure": (re.compile(r"\bazure\b", re.I), 3),
    "Docker": (re.compile(r"\bdocker\b|\bcontaineri[sz]\b", re.I), 4),
    "Kubernetes": (re.compile(r"\bkubernetes\b|\bk8s\b", re.I), 3),
    "CI/CD": (re.compile(r"\bci\s*/\s*cd\b|\bgithub\s+actions?\b|\bgitlab\s+ci\b|\bjenkins\b|continuous\s+(?:integration|delivery|deployment)", re.I), 3),
    "Deployment": (re.compile(r"\bdeploy(?:ed|ment|ing)?\b|\bvercel\b|\bnetlify\b|\brailway\b|\brender\.com\b", re.I), 2),
    "React/Next.js": (re.compile(r"\breact(?:\.js|js)?\b|\bnext\.?js\b", re.I), 2),
    "TypeScript/Node": (re.compile(r"\btypescript\b|\bnode\.?js\b|\bexpress\b", re.I), 1),
}

# --------------------------------------------------------------------------- #
# Engineering depth (testing / architecture / ops)
# --------------------------------------------------------------------------- #
DEPTH_TOKENS: dict[str, tuple[re.Pattern, int]] = {
    "testing": (re.compile(r"\bpytest\b|\bunittest\b|\bunit\s+tests?\b|\bintegration\s+tests?\b|\btest[-\s]?coverage\b|\btdd\b", re.I), 2),
    "architecture": (re.compile(r"\bdesign\s+patterns?\b|\bsolid\b|\bhexagonal\b|\bmicroservices?\b|\bmodular\s+(?:architect|design)|\barchitecture\b", re.I), 1),
    "caching": (re.compile(r"\bcach(?:e|ing)\b", re.I), 1),
    "observability": (re.compile(r"\bobservability\b|\bprometheus\b|\bgrafana\b|\bopentelemetry\b|\bstructured\s+logging\b|\bmonitoring\b", re.I), 1),
    "concurrency/resilience": (re.compile(r"\bconcurren|\bthread(?:ing|s)?\b|\block(?:s|ing)?\b|\bretr(?:y|ies|ying)\b|\btimeouts?\b|\bcircuit\s+breaker\b|\bgraceful\s+degradation\b", re.I), 1),
}
