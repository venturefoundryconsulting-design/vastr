from pydantic import BaseModel


class HelpAskRequest(BaseModel):
    question: str
    path: str | None = None


class HelpSourceOut(BaseModel):
    id: str
    title: str
    module: str
    screen: str | None = None


class HelpAskResponse(BaseModel):
    answer: str
    grounded: bool
    sources: list[HelpSourceOut]
    module: str | None = None
    screen: str | None = None


class HelpContextEntry(BaseModel):
    id: str
    type: str
    title: str
    answer: str
    screen: str | None = None


class HelpContextResponse(BaseModel):
    module: str | None = None
    screen: str | None = None
    entries: list[HelpContextEntry]
