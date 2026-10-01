"""Validated request payloads and shared defaults."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

RequirementLevel = Literal["not_required", "preferred", "required"]

DEFAULT_WEIGHTS = {
    "academic": 25.0,
    "skills": 30.0,
    "experience": 20.0,
    "projects": 15.0,
    "certifications": 5.0,
    "completeness": 5.0,
}

DEFAULT_THRESHOLDS = {
    "priority_review": 90.0,
    "interview_recommendation": 80.0,
    "manual_review": 70.0,
}

COMPONENTS = ("academic", "skills", "experience", "projects", "certifications", "completeness")


def _clean_skill_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        skill = (raw or "").strip()
        if not skill:
            continue
        key = skill.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(skill[:60])
    return out


class ProfileIn(BaseModel):
    type: Literal["recruitment", "college"]
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)
    required_skills: list[str] = Field(default_factory=list, max_length=50)
    preferred_skills: list[str] = Field(default_factory=list, max_length=50)
    min_academic: float | None = Field(default=None, ge=0, le=100)
    min_academic_type: Literal["cgpa", "percentage"] = "cgpa"
    education_requirement: str = Field(default="", max_length=300)
    experience_requirement: RequirementLevel = "preferred"
    projects_requirement: RequirementLevel = "preferred"
    certifications_requirement: RequirementLevel = "not_required"
    communication_note: str = Field(default="Manual review", max_length=300)
    weights: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    thresholds: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))
    ai_enabled: bool = True

    @field_validator("required_skills", "preferred_skills")
    @classmethod
    def dedupe_skills(cls, values: list[str]) -> list[str]:
        return _clean_skill_list(values)

    @field_validator("title", "education_requirement", "communication_note", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return (value or "").strip()

    @model_validator(mode="after")
    def validate_weights_and_thresholds(self):
        for component in COMPONENTS:
            value = self.weights.get(component, 0)
            if value < 0 or value > 100:
                raise ValueError(f"weight for '{component}' must be between 0 and 100")
        total = sum(float(self.weights.get(c, 0)) for c in COMPONENTS)
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"weights must add up to 100 (currently {round(total, 2)})")
        priority = float(self.thresholds.get("priority_review", 0))
        interview = float(self.thresholds.get("interview_recommendation", 0))
        manual = float(self.thresholds.get("manual_review", 0))
        if not (100 >= priority > interview > manual >= 0):
            raise ValueError(
                "thresholds must satisfy 100 >= priority_review > interview_recommendation > manual_review >= 0"
            )
        self.thresholds = {
            "priority_review": priority,
            "interview_recommendation": interview,
            "manual_review": manual,
        }
        self.weights = {c: float(self.weights.get(c, 0)) for c in COMPONENTS}
        return self


class NoteIn(BaseModel):
    author: str = Field(default="Local Reviewer", max_length=120)
    note: str = Field(min_length=1, max_length=4000)

    @field_validator("note", "author")
    @classmethod
    def strip(cls, value: str) -> str:
        return value.strip()


class DecisionIn(BaseModel):
    decision: Literal["move_to_interview", "shortlist", "hold", "close"]
    reason: str = Field(default="", max_length=4000)
    author: str = Field(default="Local Reviewer", max_length=120)

    @field_validator("reason", "author")
    @classmethod
    def strip(cls, value: str) -> str:
        return value.strip()


class AISettingsIn(BaseModel):
    provider: Literal["none", "openai_compatible", "groq", "gemini", "local", "mock"] = "none"
    base_url: str = Field(default="", max_length=300)
    model: str = Field(default="", max_length=120)
    api_key: str = Field(default="", max_length=400)
    clear_api_key: bool = False
    timeout_seconds: int = Field(default=60, ge=5, le=600)


class ReviewerIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
