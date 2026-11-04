"""Paths, model prices, and defaults."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("PE_DATA_DIR", ROOT / "data"))
PROMPTS_DIR = ROOT / "backend" / "prompts"
FRONTEND_DIR = ROOT / "frontend"

# Dollars per 1M tokens: (input, output, cache read, cache write).
# Cache writes cost 1.25x input; the Haiku cache-read price is an estimate (0.1x input).
PRICING = {
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}
MODELS = list(PRICING)
EFFORTS = ["low", "medium", "high", "xhigh", "max"]

# Models that get server-side refusal fallbacks (Anthropic's recommended default).
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"

DEFAULT_SETTINGS = {
    "teacher_model": "claude-opus-5-5",
    "teacher_effort": "medium",
    "cheap_model": "claude-haiku-5-5",
    "monthly_budget_usd": 10.0,
}

DEFAULT_PROFILE = {
    "name": "Treon",
    "school": "University of North Texas (UNT), B.S. Computer Science",
    "level": "Sophomore at the data structures stage (data structures, discrete math, computer organization)",
    "languages": ["C++ (main class language)", "Python"],
    "learns_best_by": ["building or coding it", "worked examples", "seeing it visually"],
    "struggles_with": [
        "forgetting material later",
        "losing focus during long passive reading",
        "gaps in foundations",
    ],
    "session_length": "60+ minute deep dives",
    "goals": [
        "top grades in UNT CS courses",
        "internship interviews",
        "real-world engineering skills",
        "deep theory",
    ],
}

MAX_STEPS_PER_TURN = 8  # model calls per learner submission, to stop runaway loops
