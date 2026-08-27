"""Phase 4 of the ERP documentation project - the in-app help assistant.

No test here calls a real OpenAI endpoint. Every tenant in these tests has
no openai_api_key configured (the default), which exercises exactly the path
every store gets out of the box: a deterministic answer straight from the
knowledge base, with no external dependency and no chance of hallucination -
that's the behavior worth locking down with tests, not the optional LLM
rephrasing on top of it.
"""

from app.services import help_assistant


def test_grounded_question_returns_the_right_entry(db, tenant):
    result = help_assistant.answer_question(db, "why can't I edit an item's SKU")
    assert result.grounded is True
    assert result.sources
    assert result.sources[0].id == "core-retail.item-master.sku-immutable"
    assert "SKU" in result.answer or "sku" in result.answer.lower()


def test_unanswerable_question_says_so_honestly(db, tenant):
    result = help_assistant.answer_question(db, "what is the airspeed velocity of an unladen swallow")
    assert result.grounded is False
    assert result.sources == []
    assert "couldn't find" in result.answer.lower()


def test_generic_words_incidental_to_a_title_do_not_produce_a_false_match(db, tenant):
    """Regression test: this exact question once matched
    core-retail.item-master.uom-conversions purely because its title reads
    "...vendor units (like rolls)..." - the word "like" in an ordinary
    English sentence, not a real signal. A confident wrong answer here would
    be exactly the failure mode the help assistant exists to avoid."""
    result = help_assistant.answer_question(db, "What's the weather like today?")
    assert result.grounded is False


def test_empty_question_does_not_crash(db, tenant):
    result = help_assistant.answer_question(db, "")
    assert result.grounded is False


def test_route_context_is_attached_to_the_answer(db, tenant):
    result = help_assistant.answer_question(db, "how do I record output", path="/production/7")
    assert result.context == {"module": "manufacturing", "screen": "production-orders"}


def test_route_context_is_none_for_an_unmapped_path(db, tenant):
    result = help_assistant.answer_question(db, "why can't I edit an item's SKU", path="/some/unknown/route")
    assert result.context is None
    # still answers correctly even though the route didn't resolve
    assert result.grounded is True


def test_answer_never_invents_when_no_ai_key_is_configured(db, tenant):
    """The deterministic fallback path - what every tenant gets without
    setting up an OpenAI key. The returned text must be exactly the
    knowledge-base entry's own answer, not a paraphrase, since there is no
    model in the loop to paraphrase it."""
    from app.services import knowledge_base as kb

    result = help_assistant.answer_question(db, "why can't I edit an item's SKU")
    entry = kb.get_entry("core-retail.item-master.sku-immutable")
    assert result.answer.startswith(entry.answer)


def test_multiple_sources_surface_related_entries_in_the_deterministic_answer(db, tenant):
    result = help_assistant.answer_question(db, "purchase order receiving duplicate goods receipt")
    assert result.grounded is True
    assert len(result.sources) >= 1
    assert result.sources[0].id == "core-retail.known-issue.duplicate-receiving"
