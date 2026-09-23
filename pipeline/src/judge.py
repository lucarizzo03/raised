"""Judgment layer. Jev only ever sees extracted fields, never raw articles.

Every judgment goes through `Judge`, an interface with two backends:
  - JevBackend: TypeSafe Jev via langchain-typesafe (TYPESAFE_API_KEY).
  - LLMBackend: the configured LLM with structured JSON output.
JUDGE_BACKEND=jev|llm selects it; default is jev when the key exists.

Any answer below CONFIDENCE_REVIEW_THRESHOLD is flagged needs_review.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from . import config, llm
from .models import Company, Decision, JobPosting, Round, SalesRoleType, Signal
from .resilience import model_slots, run_each, with_retries

log = logging.getLogger(__name__)

ROUND_LABELS = {
    "Pre-seed": Round.PRE_SEED,
    "Seed": Round.SEED,
    "Series A": Round.SERIES_A,
    "Series B": Round.SERIES_B,
    "Later": Round.LATER,
}

SALES_TYPE_LABELS = {
    "AE": SalesRoleType.AE,
    "SDR": SalesRoleType.SDR,
    "Head of Sales": SalesRoleType.HEAD_OF_SALES,
    "Other": SalesRoleType.OTHER,
}

INVESTIGATE_ACTIONS = ["score_now", "check_careers", "search_news", "fetch_about"]


@dataclass
class Judgment:
    value: str
    confidence: float


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


class JevBackend:
    def __init__(self) -> None:
        from langchain_typesafe import TypeSafeClassifier

        self._clf = TypeSafeClassifier()

    async def ask(self, state: str, questions: dict) -> dict[str, Judgment]:
        async def call():
            async with model_slots():
                return await self._clf.ainvoke({"state": state, "questions": questions})

        resp = await with_retries(call, what="Jev")
        out: dict[str, Judgment] = {}
        for name, ans in resp.answers.items():
            if ans.type == "noul":
                # noul is P(yes); confidence = probability of the predicted side
                yes = ans.noul >= 0.5
                out[name] = Judgment(
                    value="yes" if yes else "no",
                    confidence=ans.noul if yes else 1.0 - ans.noul,
                )
            elif ans.type == "choice":
                out[name] = Judgment(value=ans.choice, confidence=ans.confidence)
            elif ans.type == "score":
                out[name] = Judgment(value=str(ans.score), confidence=ans.confidence)
        return out


class LLMBackend:
    """Same questions answered by a general LLM via structured JSON output."""

    async def ask(self, state: str, questions: dict) -> dict[str, Judgment]:
        spec = {
            name: self._question_spec(q)
            for name, q in questions.items()
        }
        data = await llm.complete_json(
            "You are a strict classifier. For each question return "
            '{"answer": ..., "confidence": 0.0-1.0}. Answer only from the '
            "state given; use low confidence when unsure.",
            f"STATE:\n{state}\n\nQUESTIONS:\n{spec}",
        )
        out: dict[str, Judgment] = {}
        for name in questions:
            entry = data.get(name) or {}
            answer = entry.get("answer")
            try:
                confidence = float(entry.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            out[name] = Judgment(value=str(answer), confidence=confidence)
        return out

    @staticmethod
    def _question_spec(q) -> dict:
        qtype = getattr(q, "type", None)
        spec = {"instructions": getattr(q, "instructions", "")}
        criteria = getattr(q, "criteria", None)
        if criteria:
            spec["allowed_answers"] = criteria
        spec["kind"] = {"noul": "yes/no", "choice": "one of allowed_answers", "score": "number"}[qtype]
        return spec


def _backend():
    if config.JUDGE_BACKEND == "jev":
        try:
            return JevBackend()
        except Exception as exc:
            log.warning("Jev backend unavailable (%s); falling back to LLM", exc)
    return LLMBackend()


_BACKEND = None


def backend():
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = _backend()
        log.info("judge backend: %s", type(_BACKEND).__name__)
    return _BACKEND


def _questions(**kwargs):
    """Build langchain-typesafe question objects lazily (import is cheap but
    keeps the module usable without the package for tests)."""
    from langchain_typesafe import Choice, Noul, Score

    kinds = {"noul": Noul, "choice": Choice, "score": Score}
    return {name: kinds[kind](**args) for name, (kind, args) in kwargs.items()}


# ---------------------------------------------------------------------------
# Public judgments
# ---------------------------------------------------------------------------


def _flag(confidence: float) -> bool:
    return confidence < config.CONFIDENCE_REVIEW_THRESHOLD


def _company_state(company: Company) -> str:
    """Only extracted/enriched fields - never raw article text."""
    lines = [
        f"company: {company.name}",
        f"domain: {company.domain or 'unknown'}",
        f"claimed round: {company.round.value}",
        f"amount raised: {company.amount_raised or 'unknown'}",
        f"raised date: {company.raised_date or 'unknown'}",
        f"article title: {company.article_title or 'unknown'}",
        f"article publication date: {company.article_published_at or 'unknown'}",
        f"article funding extraction: {company.funding_evidence or 'unavailable'}",
        f"investors: {', '.join(company.investors) or 'unknown'}",
        f"open roles: {len(company.jobs)}",
    ]
    if company.about_text:
        lines.append(f"about page excerpt: {company.about_text[:1500]}")
    if company.careers_text:
        lines.append(f"careers page excerpt: {company.careers_text[:1000]}")
    if company.news_snippets:
        lines.append("recent news: " + " | ".join(company.news_snippets[:5]))
    return "\n".join(lines)


async def judge_new_round(company: Company) -> None:
    questions = _questions(new_round=("noul", {"instructions": (
        "Is this article announcing a new funding round for this company and "
        "the claimed round, not referencing a past one? Judge the article's "
        "funding extraction and supporting announcement quote, not whether "
        "the company has ever raised. A historical/background round or an "
        "article about a different company or different round is no. When "
        "article evidence is unavailable or ambiguous, remain uncertain."
    )}))
    answer = (await backend().ask(_company_state(company), questions))["new_round"]
    if not company.funding_evidence:
        answer = Judgment("unknown", 0.0)
    _record(company, "new_round", answer, company.source_url)


async def judge_company(company: Company) -> None:
    questions = _questions(
        genuine_raise=(
            "noul",
            {
                # The original wording ("is this a genuine raise?") read as a
                # request to authenticate the round, which cannot be done from
                # these fields - it answered "no" to all 128 companies. Asking
                # what the record describes discriminates properly.
                "instructions": (
                    "Do these fields describe a company that raised a venture "
                    "funding round? Answer no only if the record clearly is not "
                    "a company raising investment - for example a bar, "
                    "restaurant, venue, event, product launch, or an incoherent "
                    "record. A plausible company with a round and an amount is a yes."
                )
            },
        ),
        is_startup=(
            "noul",
            {"instructions": "Is this a venture-backed technology startup?"},
        ),
        sells_to=(
            "choice",
            {
                "instructions": "Who does this company sell to?",
                "criteria": {
                    "B2B": "Sells primarily to businesses or other organizations",
                    "B2C": "Sells primarily to individual consumers",
                    "Both": "Sells meaningfully to both businesses and consumers",
                    "Unclear": "Cannot tell from the available information",
                },
            },
        ),
        round=(
            "choice",
            {
                "instructions": "Which funding round did the company raise?",
                "criteria": {
                    "Pre-seed": "Pre-seed or angel round",
                    "Seed": "Seed round",
                    "Series A": "Series A round",
                    "Series B": "Series B round",
                    "Later": "Series C or later, growth, debt, or unclear late round",
                },
            },
        ),
        icp_fit=(
            "score",
            {
                "instructions": (
                    "ICP fit: a B2B company at Seed to Series B that is "
                    "building a sales function for the first time."
                ),
                "criteria": [
                    "consumer, non-B2B, or wrong stage",
                    "weak fit",
                    "B2B but stage or sales motion unclear",
                    "B2B, right stage, some GTM signal",
                    "B2B at Seed-B clearly building sales for the first time",
                ],
            },
        ),
    )
    answers = await backend().ask(_company_state(company), questions)
    _record(company, "genuine_raise", answers["genuine_raise"], company.source_url)
    _record(company, "is_startup", answers["is_startup"], company.source_url)
    _record(company, "sells_to", answers["sells_to"], company.source_url)
    rnd = _record(company, "round", answers["round"], company.source_url)
    if rnd.value in ROUND_LABELS:
        company.round = ROUND_LABELS[rnd.value]
    _record(company, "icp_fit", answers["icp_fit"], company.source_url)


async def judge_job(company: Company, job: JobPosting) -> None:
    state = (
        f"company: {company.name}\njob title: {job.title}\n"
        f"department: {job.department or 'unknown'}\n"
        f"description excerpt: {job.description_text[:800]}"
    )
    questions = _questions(
        is_sales=(
            "noul",
            {"instructions": "Is this a sales role (account executive, SDR/BDR, sales leadership, revenue)?"},
        ),
        sales_type=(
            "choice",
            {
                "instructions": "Which type of sales role is this?",
                "criteria": {
                    "AE": "Account executive / closing role",
                    "SDR": "SDR, BDR, outbound prospecting",
                    "Head of Sales": "VP Sales, Head of Sales, CRO, sales leadership",
                    "Other": "Other sales-adjacent role or not a sales role",
                },
            },
        ),
    )
    answers = await backend().ask(state, questions)
    _record(
        company, "sales_role", answers["is_sales"], job.url,
        extra_value=f"{job.title}",
    )
    _record(
        company, "sales_role_type", answers["sales_type"], job.url,
        extra_value=f"{job.title}",
    )
    if answers["is_sales"].value == "yes":
        job.department = job.department or "Sales"


async def judge_founders(company: Company) -> None:
    if not company.about_text:
        return
    state = (
        f"company: {company.name}\n"
        f"team/about page excerpt:\n{company.about_text[:2500]}"
    )
    questions = _questions(
        technical_founders=(
            "noul",
            {"instructions": "Do the founders appear to be technical (engineering, product, research backgrounds)?"},
        ),
        first_sales_hire=(
            "noul",
            {"instructions": "Does this appear to be the company's first sales hire (no existing sales/GTM leadership on the team)?"},
        ),
    )
    answers = await backend().ask(state, questions)
    _record(company, "technical_founders", answers["technical_founders"], None)
    _record(company, "first_sales_hire", answers["first_sales_hire"], None)


async def decide_investigation(company: Company, round_num: int) -> Decision:
    """Jev picks: score now, or one enrichment action."""
    available = [a for a in INVESTIGATE_ACTIONS if a != "score_now"]
    if company.careers_text:
        available.remove("check_careers")
    if company.about_text:
        available.remove("fetch_about")
    if company.news_snippets:
        available.remove("search_news")
    options = ["score_now"] + available
    questions = _questions(
        next_action=(
            "choice",
            {
                "instructions": (
                    "Is the evidence enough to score this company now "
                    "(score_now), or should we gather one more piece of "
                    "evidence first?"
                ),
                "criteria": {opt: opt.replace("_", " ") for opt in options},
            },
        )
    )
    answers = await backend().ask(_company_state(company), questions)
    ans = answers["next_action"]
    action = ans.value if ans.value in options else "score_now"
    decision = Decision(
        question="score now or dig deeper?",
        answer=action,
        confidence=ans.confidence,
        action_chosen=None if action == "score_now" else action,
        round=round_num,
    )
    company.decisions.append(decision)
    return decision


def _record(
    company: Company,
    signal_type: str,
    judgment: Judgment,
    source_url: str | None,
    extra_value: str = "",
) -> Judgment:
    value = judgment.value if not extra_value else f"{judgment.value} ({extra_value})"
    company.signals.append(
        Signal(
            signal_type=signal_type,
            value=value,
            confidence=round(judgment.confidence, 3),
            needs_review=_flag(judgment.confidence),
            source_url=source_url,
        )
    )
    return judgment


def _latest(company: Company, signal_type: str) -> Signal | None:
    hits = [s for s in company.signals if s.signal_type == signal_type]
    return hits[-1] if hits else None


def _gate_signal(company: Company) -> Signal | None:
    """The confident "no" that trips the gate, if any."""
    for signal_type in ("genuine_raise", "is_startup"):
        sig = _latest(company, signal_type)
        if sig and sig.value.startswith("no") and sig.confidence >= config.CONFIDENCE_REVIEW_THRESHOLD:
            return sig
    return None


_GATE_LABELS = {
    "genuine_raise": "not a funding raise",
    "is_startup": "not a venture-backed technology startup",
}


def gate_reason(company: Company) -> str | None:
    """Returns a reason to reject, or None to keep.

    A confident "no" on either gate drops the company. An unconfident answer
    keeps it and leaves the needs_review flag that _record already set.
    """
    sig = _gate_signal(company)
    if sig is None:
        return None
    return f"{_GATE_LABELS[sig.signal_type]} ({sig.signal_type}=no, confidence {sig.confidence:.2f})"


async def _judge_company_and_jobs(company: Company) -> None:
    await judge_company(company)
    await asyncio.gather(*(judge_job(company, j) for j in company.jobs))


async def judge_all(companies: list[Company]) -> None:
    """Company + job judgments in parallel; founder judgments need about pages.

    A company whose judgments fail is marked failed_stage and left out of the run.
    """
    _, failed = await run_each(companies, _judge_company_and_jobs, stage="judge", label=lambda c: c.name)
    for c in failed:
        c.failed_stage = "judge"
    judged = [c for c in companies if not c.failed_stage]
    rejected = [c for c in judged if gate_reason(c)]
    if len(judged) >= config.GATE_MIN_BATCH and len(rejected) / len(judged) > config.GATE_MAX_REJECT_RATE:
        log.warning(
            "gate would reject %d of %d companies; not enforcing (likely a model problem)",
            len(rejected), len(judged),
        )
        return
    log.info(
        "gate: evaluated %d companies, rejected %d, kept %d",
        len(judged), len(rejected), len(judged) - len(rejected),
    )
    for c in rejected:
        c.rejection_reason = "not_startup_raise"
        c.rejection_detail = gate_reason(c)
        c.excluded, c.excluded_reason = True, "not_startup_raise"
        log.info("  rejected %s: %s", c.name, c.rejection_detail)
