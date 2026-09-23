"""Scoring and exclusions: plain code over judged signals. Never calls a model."""

from __future__ import annotations

from . import config
from .dates import now_utc
from .models import Company

_WEIGHTS = config.SCORING_WEIGHTS


def _latest(company: Company, signal_type: str):
    hits = [s for s in company.signals if s.signal_type == signal_type]
    return hits[-1] if hits else None


def _signal_yes(company: Company, signal_type: str) -> bool:
    return any(
        s.signal_type == signal_type and s.value.startswith("yes")
        for s in company.signals
    )


def _latest_yes(company: Company, signal_type: str) -> bool:
    """For one-per-company judgments: only the most recent answer counts, so a
    re-judged "unknown" replaces an older guessed "yes"."""
    sig = _latest(company, signal_type)
    return bool(sig and sig.value.startswith("yes"))


def _scaled(company: Company, rule: str) -> tuple[int, str]:
    """Points for a confidence-scaled rule and its rules_fired entry. Full
    points keep the plain rule name; a reduction is spelled out, e.g.
    "first_sales_hire (+6, confidence 0.14, reduced from 30)"."""
    full = _WEIGHTS[rule]
    confidence = _latest(company, rule).confidence
    if confidence >= config.FULL_POINTS_CONFIDENCE:
        return full, rule
    points = round(full * confidence / config.FULL_POINTS_CONFIDENCE)
    return points, f"{rule} (+{points}, confidence {confidence:.2f}, reduced from {full})"


def _has_sales_role(company: Company) -> bool:
    return _signal_yes(company, "sales_role")


def _days_since_raise(company: Company) -> int | None:
    if not company.raised_date:
        return None
    # UTC, like every other date rule; local time made the ramp and the
    # display window disagree by a day around midnight.
    return (now_utc().date() - company.raised_date).days


def icp_points(company: Company) -> tuple[int, float | None]:
    """ICP rubric position -> 0..ICP_FIT_MAX_POINTS. Returns (points, raw)."""
    sig = _latest(company, "icp_fit")
    if sig is None:
        return 0, None
    try:
        raw = float(sig.value)
    except (TypeError, ValueError):
        return 0, None
    normalized = max(0.0, min(1.0, raw / config.ICP_FIT_SCALE_MAX))
    return round(normalized * config.ICP_FIT_MAX_POINTS), raw


def recency_points(company: Company) -> int:
    """Linear ramp: today = 30, 45d = 15, 90d+ = 0."""
    days = _days_since_raise(company)
    if days is None or days < 0:
        return 0
    ramp = 1 - days / config.RECENCY_WINDOW_DAYS
    return max(0, round(config.RECENCY_MAX_POINTS * ramp))


def avg_confidence(company: Company) -> float:
    if not company.signals:
        return 0.0
    return sum(s.confidence for s in company.signals) / len(company.signals)


def exclusion_reason(company: Company) -> str | None:
    """Fix 3 exclusions, applied before scoring. Plain code, no model."""
    sells = _latest(company, "sells_to")
    if sells and sells.value == "B2C" and sells.confidence >= config.B2C_EXCLUDE_CONFIDENCE:
        return f"sells to consumers (sells_to=B2C, {sells.confidence:.2f})"
    if (
        company.round.value == "later"
        and company.amount_raised is not None
        and company.amount_raised > config.LATE_STAGE_AMOUNT_CEILING
    ):
        return (
            f"late stage at scale (round=later, "
            f"${company.amount_raised / 1e6:,.0f}M raised)"
        )
    return None


def apply_exclusions(companies: list[Company]) -> None:
    for c in companies:
        reason = exclusion_reason(c)
        c.excluded = reason is not None
        c.excluded_reason = reason


def score_company(company: Company) -> None:
    rules: list[str] = []
    score = 0

    recency = recency_points(company)
    if recency > 0:
        score += recency
        rules.append(f"raise_recency (+{recency})")

    if company.round.value in config.SCORING_ROUNDS:
        score += _WEIGHTS["round_seed_to_b"]
        rules.append("round_seed_to_b")

    if _latest_yes(company, "first_sales_hire") and _has_sales_role(company):
        points, rule = _scaled(company, "first_sales_hire")
        score += points
        rules.append(rule)

    if _has_sales_role(company):
        score += _WEIGHTS["any_sales_role_open"]
        rules.append("any_sales_role_open")

    if _latest_yes(company, "technical_founders"):
        points, rule = _scaled(company, "technical_founders")
        score += points
        rules.append(rule)

    icp, _raw = icp_points(company)
    if icp > 0:
        score += icp
        rules.append(f"icp_fit (+{icp})")

    company.score = score
    company.rules_fired = rules
    company.explanation = _explain(company, rules)


def _explain(company: Company, rules: list[str]) -> str:
    parts: list[str] = []
    days = _days_since_raise(company)
    if days is not None:
        label = company.round.value.replace("_", " ")
        parts.append(f"Raised {label} {days}d ago" if days >= 0 else f"Raised {label}")
    if any(r.startswith("first_sales_hire") for r in rules):
        n = sum(
            1 for s in company.signals
            if s.signal_type == "sales_role" and s.value.startswith("yes")
        )
        parts.append(f"making first sales hire ({n} sales role{'s' if n != 1 else ''} open)")
    elif any(r.startswith("any_sales_role_open") for r in rules):
        parts.append("has open sales roles")
    if any(r.startswith("technical_founders") for r in rules):
        parts.append("technical founding team")
    sells = _latest(company, "sells_to")
    if sells and sells.value == "B2B":
        parts.append("sells B2B")
    if not parts:
        return "No scoring rules fired."
    return "; ".join(parts) + "."


def _sort_key(c: Company):
    """score desc, then days since raise asc, then avg signal confidence desc."""
    days = _days_since_raise(c)
    return (-c.score, days if days is not None else 10**6, -avg_confidence(c))


def rank(companies: list[Company]) -> list[Company]:
    apply_exclusions(companies)
    for c in companies:
        score_company(c)
    visible = [c for c in companies if not c.excluded]
    return sorted(visible, key=_sort_key)
