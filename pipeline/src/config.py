"""Central configuration: env vars, feeds, scoring weights."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# --- LLM (extraction + judge fallback): Anthropic only -------------------------
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

# --- Judge backend -------------------------------------------------------------
# "jev" uses TypeSafe Jev via langchain-typesafe (needs TYPESAFE_API_KEY).
# "llm" uses the LLM provider above with structured JSON output.
JUDGE_BACKEND = os.environ.get("JUDGE_BACKEND") or (
    "jev" if os.environ.get("TYPESAFE_API_KEY") else "llm"
)

CONFIDENCE_REVIEW_THRESHOLD = 0.7
# The genuine-raise / startup gate once answered "no" for every company. If it
# would reject more than this share of a batch (of at least GATE_MIN_BATCH),
# treat it as a model problem: log it and reject nobody.
GATE_MAX_REJECT_RATE = 0.5
GATE_MIN_BATCH = 4

# --- Database ------------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# --- Feeds ---------------------------------------------------------------------
INGEST_WINDOW_DAYS = 3
DISPLAY_WINDOW_DAYS = 90
BACKFILL_WINDOW_DAYS = 30
MAX_ARTICLE_LAG_DAYS = 7

TECHCRUNCH_FEEDS = [
    "https://techcrunch.com/category/venture/feed/",
    "https://techcrunch.com/category/startups/feed/",
]

GOOGLE_NEWS_QUERIES = [
    "raises Seed",
    "raises Series A",
    "raises Series B",
]
GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search?q={query}%20when%3A{window_days}d"
    "&hl=en-US&gl=US&ceid=US:en"
)

EDGAR_FULL_TEXT_SEARCH = "https://efts.sec.gov/LATEST/search-index"
EDGAR_FORMS = "D"
# SEC requires a declared user agent with contact info.
EDGAR_USER_AGENT = os.environ.get(
    "EDGAR_USER_AGENT", "raised-pipeline/0.1 (contact@example.com)"
)

# --- Fetching -------------------------------------------------------------------
HTTP_TIMEOUT = 20.0
HTTP_MAX_CONCURRENCY = 10
ARTICLE_TEXT_LIMIT = 12_000  # chars fed to the extraction model
MAX_RESPONSE_BYTES = 5_000_000  # larger pages are dropped, not truncated mid-parse

# --- Model calls ------------------------------------------------------------------
MODEL_MAX_CONCURRENCY = 8  # shared by Claude and Jev
MODEL_MAX_RETRIES = 4
RETRY_BASE_DELAY = 1.0
RETRY_MAX_DELAY = 30.0
# More failures than this in one stage means the provider is down: abort the
# run before persisting instead of writing a partial day.
MAX_STAGE_FAILURE_RATE = 0.25

# --- Investigation loop ----------------------------------------------------------
MAX_INVESTIGATION_ROUNDS = 3

# --- Scoring weights (plain code, no model calls) ---------------------------------
SCORING_WEIGHTS = {
    "round_seed_to_b": 15,
    "first_sales_hire": 30,
    "any_sales_role_open": 15,
    "technical_founders": 10,
}

# Recency is a linear ramp instead of two buckets: a raise today is worth the
# full 30, 45 days ago 15, 90 days or older nothing. Buckets put ~80 companies
# on the same score.
RECENCY_MAX_POINTS = 30
RECENCY_WINDOW_DAYS = DISPLAY_WINDOW_DAYS

# ICP fit contributes 0-20. Jev returns the rubric position on a 0-N scale
# where N is the number of criteria minus one (5 criteria -> 0..4), so it is
# normalized before scaling.
ICP_FIT_MAX_POINTS = 20
ICP_FIT_SCALE_MAX = 4.0

# Fix 3 exclusions.
B2C_EXCLUDE_CONFIDENCE = 0.7
LATE_STAGE_AMOUNT_CEILING = 200_000_000

SCORING_ROUNDS = {"seed", "series_a", "series_b"}  # rounds worth SCORING_WEIGHTS["round_seed_to_b"]
EARLY_ROUNDS = {"pre_seed", "seed", "series_a", "series_b"}

TOP_N = 25  # companies surfaced on the dashboard
