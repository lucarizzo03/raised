"""Scoring: plain code over judged signals. Never calls a model."""

from __future__ import annotations

from datetime import date

from . import config
from .models import Company, Round

_WEIGHTS = config.SCORING_WEIGHTS


def _signal_yes(company: Company, signal_type: str) -> bool:
    return any(
        s.signal_type == signal_type and s.value.startswith("yes")
        for s in company.signals
    )


def _has_sales_role(company: Company) -> bool:
    return any(
        s.signal_type == "sales_role" and s.value.startswith("yes")
        for s in company.signals
    )


def score_company(company: Company) -> None:
    rules: list[str] = []
    score = 0

    if company.raised_date:
        days = (date.today() - company.raised_date).days
        if 0 <= days <= 30:
            score += _WEIGHTS["raised_within_30d"]
            rules.append("raised_within_30d")
        elif 31 <= days <= 90:
            score += _WEIGHTS["raised_31_90d"]
            rules.append("raised_31_90d")

    if company.round in config.SCORING_ROUNDS:
        score += _WEIGHTS["round_seed_to_b"]
        rules.append("round_seed_to_b")

    if _signal_yes(company, "first_sales_hire") and _has_sales_role(company):
        score += _WEIGHTS["first_sales_hire"]
        rules.append("first_sales_hire")

    if _has_sales_role(company):
        score += _WEIGHTS["any_sales_role_open"]
        rules.append("any_sales_role_open")

    if _signal_yes(company, "technical_founders"):
        score += _WEIGHTS["technical_founders"]
        rules.append("technical_founders")

    company.score = score
    company.rules_fired = rules
    company.explanation = _explain(company, rules)


def _explain(company: Company, rules: list[str]) -> str:
    parts: list[str] = []
    if company.raised_date:
        days = (date.today() - company.raised_date).days
        label = company.round.value.replace("_", " ")
        parts.append(f"Raised {label} {days}d ago" if days >= 0 else f"Raised {label}")
    if "first_sales_hire" in rules:
        n = sum(
            1 for s in company.signals
            if s.signal_type == "sales_role" and s.value.startswith("yes")
        )
        parts.append(f"making first sales hire ({n} sales role{'s' if n != 1 else ''} open)")
    elif "any_sales_role_open" in rules:
        parts.append("has open sales roles")
    if "technical_founders" in rules:
        parts.append("technical founding team")
    if not parts:
        return "No scoring rules fired."
    return "; ".join(parts) + "."


def rank(companies: list[Company]) -> list[Company]:
    for c in companies:
        score_company(c)
    return sorted(companies, key=lambda c: c.score, reverse=True)
