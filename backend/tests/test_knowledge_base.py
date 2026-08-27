"""Phase 3 of the ERP documentation project - the help knowledge base.

These tests guard the data, not just the code: a broken cross-reference or a
duplicate id in the JSON files is exactly the kind of mistake that's easy to
make while hand-editing documentation and easy to miss without a test that
actually loads every file.
"""

import json

import pytest

from app.services import knowledge_base as kb


@pytest.fixture(autouse=True)
def _clear_cache():
    kb.load_entries.cache_clear()
    kb._load_index.cache_clear()
    yield
    kb.load_entries.cache_clear()
    kb._load_index.cache_clear()


def test_every_json_file_parses_and_loads():
    entries = kb.load_entries()
    assert len(entries) > 100, "the knowledge base should not silently shrink to near-nothing"


def test_no_duplicate_ids():
    entries = kb.load_entries()
    ids = [e.id for e in entries]
    assert len(ids) == len(set(ids)), "duplicate knowledge-base ids found"


def test_every_related_reference_resolves():
    by_id = kb.entries_by_id()
    for entry in kb.load_entries():
        for related_id in entry.related:
            assert related_id in by_id, (
                f"{entry.id} references missing related entry {related_id!r}"
            )


def test_every_entry_has_required_fields():
    for entry in kb.load_entries():
        assert entry.id, "entry missing id"
        assert entry.type, f"{entry.id}: missing type"
        assert entry.module, f"{entry.id}: missing module"
        assert entry.title, f"{entry.id}: missing title"
        assert entry.answer, f"{entry.id}: missing answer"


def test_known_issue_entries_declare_fixed_status():
    """A known_issue with no `fixed` field is ambiguous - is it open or not?
    Every one must say explicitly."""
    for entry in kb.load_entries():
        if entry.type == "known_issue":
            assert entry.fixed in (True, False), f"{entry.id}: known_issue must set fixed true/false"


def test_every_route_in_index_maps_to_a_real_module():
    index = json.loads((kb._KB_DIR / "index.json").read_text(encoding="utf-8"))
    module_ids = {m["id"] for m in index["modules"]}
    for route, ctx in index["routes"].items():
        assert ctx["module"] in module_ids, f"route {route} points at unknown module {ctx['module']!r}"


def test_context_for_route_matches_exact_and_nested_paths():
    assert kb.context_for_route("/pos") == {"module": "core-retail", "screen": "pos"}
    assert kb.context_for_route("/production/42") == {"module": "manufacturing", "screen": "production-orders"}
    assert kb.context_for_route("/this-route-does-not-exist") is None


def test_search_finds_the_obviously_relevant_entry_first():
    results = kb.search("why can't I edit sku")
    assert results, "expected at least one result"
    assert results[0][0].id == "core-retail.item-master.sku-immutable"


def test_search_respects_module_and_screen_boost():
    plain = dict(kb.search("permission role", limit=20))
    boosted = dict(kb.search("permission role", module="manufacturing", limit=20))
    shared_id = next(iter(set(plain) & set(boosted)), None)
    if shared_id is not None:
        assert boosted[shared_id] >= plain[shared_id]


def test_search_with_no_matching_terms_returns_empty():
    assert kb.search("zzzznonexistentqueryterm") == []


def test_related_entries_resolves_to_real_entries():
    entry = kb.get_entry("core-retail.known-issue.duplicate-receiving")
    assert entry is not None
    related = kb.related_entries(entry)
    assert len(related) == len(entry.related)
    assert all(isinstance(r, kb.KbEntry) for r in related)
