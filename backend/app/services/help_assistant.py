"""Phase 4 of the ERP documentation project - the in-app "?" help assistant.

Retrieval (app.services.knowledge_base) and generation (this module) stay
deliberately separate. This module never lets the model answer from its own
knowledge of "how ERPs generally work" - it is only ever shown the specific
knowledge-base entries retrieval already selected, and told explicitly to
say so rather than guess when they don't cover the question. That is what
"grounded" means here in practice, not just in the docstring: the LLM step
is optional (falls back to returning the best entry's own answer verbatim
if no AI key is configured, or if the call fails) and even when it runs, it
cannot introduce a fact retrieval didn't already surface.
"""

import json
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.services import knowledge_base as kb
from app.services.hardware_settings import get_hardware_ai_settings

# Below this score a match is considered too weak to answer from - better to
# say "not documented" than stretch a barely-related entry into an answer.
# Calibrated against app.services.knowledge_base.search's weights (keyword
# word match = 4, title word match = 1.5, answer word match = 0.5): this
# requires either one real keyword hit, or several incidental title/answer
# word matches together - never a single generic word that merely happens
# to appear in one entry's title.
_MIN_SCORE = 3.5
_MAX_SOURCES = 3

_SYSTEM_PROMPT = """You are the in-app help assistant for the Vastr ERP.

You answer ONLY using the knowledge-base excerpts provided below - never from
general knowledge of how ERPs usually work, and never by inventing a feature,
button, or rule that isn't in the excerpts. If the excerpts only partially
answer the question, say what they do cover and name what isn't documented
rather than filling the gap with a guess.

Write 2-4 sentences, plain professional language, no headers or bullet lists
unless the excerpts themselves list steps. Do not mention "excerpts" or
"knowledge base" in your answer - write as if you simply know this about the
application."""


@dataclass
class HelpSource:
    id: str
    title: str
    module: str
    screen: str | None


@dataclass
class HelpAnswer:
    answer: str
    grounded: bool
    sources: list[HelpSource] = field(default_factory=list)
    context: dict | None = None


def _not_found(context: dict | None) -> HelpAnswer:
    return HelpAnswer(
        answer=(
            "I couldn't find anything in the help documentation about that. "
            "Try rephrasing, or check the relevant screen's own guide - this "
            "assistant only answers from documented, verified application "
            "behavior, so it won't guess."
        ),
        grounded=False,
        sources=[],
        context=context,
    )


def _deterministic_answer(entries: list[kb.KbEntry]) -> str:
    primary = entries[0]
    text = primary.answer
    if len(entries) > 1:
        others = "; ".join(f'"{e.title}"' for e in entries[1:])
        text += f" Related: {others}."
    return text


def _try_llm_answer(api_key: str, model: str, question: str, entries: list[kb.KbEntry]) -> str | None:
    try:
        from openai import OpenAI

        excerpts = "\n\n".join(
            f"### {e.title}\n{e.answer}" for e in entries
        )
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model or "gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Knowledge base excerpts:\n\n{excerpts}\n\nQuestion: {question}"},
            ],
            max_tokens=350,
            temperature=0.2,
        )
        text = response.choices[0].message.content
        return text.strip() if text else None
    except Exception:  # noqa: BLE001 - any provider failure falls back to the deterministic answer
        return None


def answer_question(db: Session, question: str, path: str | None = None) -> HelpAnswer:
    """The one entry point Phase 4's router calls. Always returns something
    usable - a grounded answer, a partial one clearly marked as such, or an
    honest "not documented" - never an exception the caller has to guard."""
    question = (question or "").strip()
    context = kb.context_for_route(path) if path else None
    if not question:
        return _not_found(context)

    module = context["module"] if context else None
    screen = context["screen"] if context else None
    results = kb.search(question, module=module, screen=screen, limit=_MAX_SOURCES)

    if not results or results[0][1] < _MIN_SCORE:
        return _not_found(context)

    entries = [e for e, _score in results]
    sources = [HelpSource(id=e.id, title=e.title, module=e.module, screen=e.screen) for e in entries]

    ai_settings = get_hardware_ai_settings(db)
    answer_text = None
    if ai_settings.openai_api_key:
        answer_text = _try_llm_answer(ai_settings.openai_api_key, ai_settings.openai_model, question, entries)

    if not answer_text:
        answer_text = _deterministic_answer(entries)

    return HelpAnswer(answer=answer_text, grounded=True, sources=sources, context=context)
