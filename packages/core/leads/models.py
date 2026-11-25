"""What the analysis model may report, and what is known about a lead.

`Extraction` is the schema the model must fill. The model only reports what was
said; the score is calculated in scoring.py.
"""

from typing import Literal

from pydantic import BaseModel, Field

SentimentLabel = Literal["positive", "neutral", "negative"]

# Order used when choosing what to learn next.
CRITERIA = ("need", "timeline", "authority", "budget")


class Fact(BaseModel):
    detail: str = Field(description="Short English statement of what the caller said.")
    evidence: str = Field(
        description="Words copied exactly from the caller's new message, in the original script."
    )


class NeedFact(Fact):
    level: Literal["vague", "specific"] = Field(
        description="'specific' if a concrete problem the product could solve is described."
    )


class BudgetFact(Fact):
    monthly_inr: int | None = Field(
        default=None,
        description="Budget in Indian rupees per month. Convert yearly amounts. "
        "Null if no amount was given.",
    )


class AuthorityFact(Fact):
    level: Literal["decision_maker", "influencer", "no_authority"]


class TimelineFact(Fact):
    months: float | None = Field(
        default=None,
        description="Months until they expect to buy or start. 0 for immediately. "
        "Null if no time was given.",
    )


class Sentiment(BaseModel):
    label: SentimentLabel
    reason: str = Field(description="A few English words, such as 'price concern'.")


class Extraction(BaseModel):
    name: str | None = None
    company: str | None = None
    need: NeedFact | None = None
    budget: BudgetFact | None = None
    authority: AuthorityFact | None = None
    timeline: TimelineFact | None = None
    objections: list[str] = Field(
        default_factory=list,
        description="New concerns or reasons not to buy. Questions are not concerns.",
    )
    sentiment: Sentiment


class LeadFacts(BaseModel):
    name: str | None = None
    company: str | None = None
    need: NeedFact | None = None
    budget: BudgetFact | None = None
    authority: AuthorityFact | None = None
    timeline: TimelineFact | None = None
    objections: list[str] = Field(default_factory=list)
