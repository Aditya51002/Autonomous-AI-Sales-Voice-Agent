"""Rule-based lead score. The same facts always give the same score."""

from dataclasses import dataclass

from packages.core.leads.models import CRITERIA, LeadFacts

WEIGHTS = {"need": 30, "budget": 25, "authority": 20, "timeline": 25}
HOT = 70
WARM = 40


@dataclass(frozen=True)
class Score:
    total: int
    grade: str
    points: dict[str, int]
    reasons: dict[str, str]
    missing: list[str]


def score_lead(facts: LeadFacts, min_monthly_budget: int) -> Score:
    """Score out of 100. min_monthly_budget is the cheapest plan's monthly price."""
    shares: dict[str, tuple[float, str]] = {}

    if need := facts.need:
        shares["need"] = (
            (1.0, "specific problem") if need.level == "specific" else (0.5, "general interest")
        )
    if budget := facts.budget:
        if budget.monthly_inr is None:
            shares["budget"] = (0.4, "budget mentioned without an amount")
        elif budget.monthly_inr >= min_monthly_budget:
            shares["budget"] = (1.0, "budget covers a plan")
        else:
            shares["budget"] = (0.2, "budget below the cheapest plan")
    if authority := facts.authority:
        shares["authority"] = (
            (0.25, "not involved in the decision")
            if authority.level == "no_authority"
            else (1.0, authority.level.replace("_", " "))
        )
    if timeline := facts.timeline:
        if timeline.months is None:
            shares["timeline"] = (0.2, "no clear date")
        elif timeline.months <= 3:
            shares["timeline"] = (1.0, "within 3 months")
        elif timeline.months <= 6:
            shares["timeline"] = (0.6, "in 3 to 6 months")
        else:
            shares["timeline"] = (0.2, "more than 6 months away")

    points = {name: round(WEIGHTS[name] * shares.get(name, (0, ""))[0]) for name in CRITERIA}
    total = sum(points.values())
    return Score(
        total=total,
        grade="Hot" if total >= HOT else "Warm" if total >= WARM else "Cold",
        points=points,
        reasons={name: shares[name][1] if name in shares else "not known" for name in CRITERIA},
        missing=[name for name in CRITERIA if name not in shares],
    )
