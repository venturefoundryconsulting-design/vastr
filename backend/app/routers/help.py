"""Phase 4 of the ERP documentation project - the in-app "?" help assistant.

Open to any authenticated user, no permission gate: help must be reachable
from wherever someone is stuck, regardless of role. Nothing here writes
anything - both routes are pure reads over the knowledge base built in
Phase 3.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.help import (
    HelpAskRequest,
    HelpAskResponse,
    HelpContextEntry,
    HelpContextResponse,
    HelpSourceOut,
)
from app.services import help_assistant
from app.services import knowledge_base as kb

router = APIRouter(prefix="/api/help", tags=["help"])

# Screen-overview entries surface first in the contextual panel - they're
# what "what is this screen for" actually answers - everything else follows
# in whatever order the module file lists it.
_SCREEN_ENTRY_FIRST = {"screen": 0}


@router.get("/context", response_model=HelpContextResponse)
def get_context(
    path: str = Query(..., description="The frontend route the user is currently on"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),  # noqa: ARG001 - unused, kept for symmetry with /ask and future per-tenant filtering
):
    """What the assistant should show before the user has even asked
    anything - a short, scoped list of entries for whatever screen they're
    looking at, driven entirely by the route they're on."""
    ctx = kb.context_for_route(path)
    if not ctx:
        return HelpContextResponse(module=None, screen=None, entries=[])

    matches = [
        e for e in kb.load_entries()
        if e.module == ctx["module"] and e.screen == ctx["screen"]
    ]
    matches.sort(key=lambda e: _SCREEN_ENTRY_FIRST.get(e.type, 1))

    return HelpContextResponse(
        module=ctx["module"], screen=ctx["screen"],
        entries=[
            HelpContextEntry(id=e.id, type=e.type, title=e.title, answer=e.answer, screen=e.screen)
            for e in matches[:8]
        ],
    )


@router.post("/ask", response_model=HelpAskResponse)
def ask(
    payload: HelpAskRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = help_assistant.answer_question(db, payload.question, payload.path)
    return HelpAskResponse(
        answer=result.answer,
        grounded=result.grounded,
        sources=[HelpSourceOut(id=s.id, title=s.title, module=s.module, screen=s.screen) for s in result.sources],
        module=result.context["module"] if result.context else None,
        screen=result.context["screen"] if result.context else None,
    )
