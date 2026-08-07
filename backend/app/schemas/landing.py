from datetime import datetime

from pydantic import BaseModel


class LandingFeature(BaseModel):
    icon: str
    title: str
    body: str


class LandingStep(BaseModel):
    title: str
    body: str


class LandingFaq(BaseModel):
    q: str
    a: str


class LandingContentOut(BaseModel):
    hero_eyebrow: str | None = None
    hero_title_line1: str | None = None
    hero_title_highlight: str | None = None
    hero_subtitle: str | None = None
    hero_cta_primary: str | None = None
    hero_cta_secondary: str | None = None
    value_strip: list[str] = []
    features: list[LandingFeature] = []
    how_it_works: list[LandingStep] = []
    faqs: list[LandingFaq] = []

    model_config = {"from_attributes": True}


class LandingContentUpdate(BaseModel):
    hero_eyebrow: str | None = None
    hero_title_line1: str | None = None
    hero_title_highlight: str | None = None
    hero_subtitle: str | None = None
    hero_cta_primary: str | None = None
    hero_cta_secondary: str | None = None
    value_strip: list[str] | None = None
    features: list[LandingFeature] | None = None
    how_it_works: list[LandingStep] | None = None
    faqs: list[LandingFaq] | None = None


class LegalPageOut(BaseModel):
    slug: str
    title: str
    content: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class LegalPageUpsert(BaseModel):
    title: str
    content: str
