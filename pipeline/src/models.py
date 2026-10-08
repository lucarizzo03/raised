"""Shared data structures flowing through the pipeline."""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Round(str, Enum):
    PRE_SEED = "pre_seed"
    SEED = "seed"
    SERIES_A = "series_a"
    SERIES_B = "series_b"
    LATER = "later"
    UNKNOWN = "unknown"


class SalesRoleType(str, Enum):
    AE = "ae"
    SDR = "sdr"
    HEAD_OF_SALES = "head_of_sales"
    OTHER = "other"


class FeedItem(BaseModel):
    """A raw article pulled from a feed, with fetched body text."""

    title: str
    url: str
    published: date | None = None
    source: str  # techcrunch | google_news
    text: str = ""
    html: str = ""  # kept so domain links can be harvested from the body


class FundingExtraction(BaseModel):
    """What the LLM pulls out of one article. not_funding_article means skip."""

    not_funding_article: bool = False
    company_name: str | None = None
    domain: str | None = None
    round: Round = Round.UNKNOWN
    amount_raised: float | None = None  # USD
    raised_date: date | None = None
    investors: list[str] = Field(default_factory=list)
    announcement_evidence: str = ""

    @field_validator("round", mode="before")
    @classmethod
    def _normalize_round(cls, value):
        """Haiku names late rounds ("series_c", "Series D") instead of using
        "later", which used to fail the whole extraction. Any label outside
        the enum becomes "unknown" rather than dropping the article."""
        if not isinstance(value, str):
            return value
        label = re.sub(r"[\s-]+", "_", value.strip().lower())
        if label == "preseed":
            return Round.PRE_SEED
        if re.fullmatch(r"series_[c-z](\d+)?|growth|late_stage|pre_ipo", label):
            return Round.LATER
        return label if label in {r.value for r in Round} else Round.UNKNOWN


class JobPosting(BaseModel):
    title: str
    url: str
    board: str  # ashby | greenhouse | lever
    department: str | None = None
    location: str | None = None
    description_text: str = ""


class Signal(BaseModel):
    signal_type: str  # e.g. genuine_raise, round, icp_fit, sales_role, first_sales_hire, technical_founders
    value: str
    confidence: float
    needs_review: bool = False
    source_url: str | None = None
    detected_at: datetime = Field(default_factory=datetime.utcnow)


class Company(BaseModel):
    """A deduped funding event plus everything later stages attach to it."""

    name: str
    domain: str | None = None
    domain_verified: bool = False  # homepage fetched and name confirmed
    domain_source: str = "none"   # provenance, for the audit trail
    dedupe_key: str
    round: Round = Round.UNKNOWN
    amount_raised: float | None = None
    raised_date: date | None = None
    investors: list[str] = Field(default_factory=list)
    source_url: str
    article_title: str = ""
    article_published_at: date | None = None
    funding_evidence: str = ""
    rejection_reason: str | None = None
    rejection_detail: str | None = None
    id: int | None = None  # populated after DB upsert

    jobs: list[JobPosting] = Field(default_factory=list)
    signals: list[Signal] = Field(default_factory=list)
    about_text: str = ""

    score: int = 0
    rules_fired: list[str] = Field(default_factory=list)
    explanation: str = ""
    excluded: bool = False
    excluded_reason: str | None = None
    # Set when a stage failed for this company; it is dropped from the run
    # and never persisted. Not part of snapshots.
    failed_stage: str | None = Field(default=None, exclude=True)
