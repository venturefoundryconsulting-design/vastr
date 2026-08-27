"""Phase 3 of the ERP documentation project - the help knowledge base.

Deliberately plain JSON files under app/data/knowledge_base/, not a database
table: this content changes by someone editing documentation, not by a normal
application write path, so it doesn't need a migration for every update, and
it can be reviewed/diffed in a pull request like the rest of the docs it was
built from. If the knowledge base ever needs to be user-editable from inside
the app, that's the point to move it into a real table - not before.

Every entry was written from direct inspection of the running application
(see MANUFACTURING_ARCHITECTURE.md and the published Phase 1/2 documentation
artifacts for the source material), not invented. `known_issue` entries in
particular describe actual current behavior, right down to which ones were
already fixed during the documentation pass (`fixed: true`) versus still
open (`fixed: false`) - callers surfacing these to a user should preserve
that distinction rather than presenting every issue as equally live.

This module is the shared source of truth Phase 4's in-app assistant reads
from - it does not itself talk to an LLM. Keeping retrieval (this file) and
generation (the assistant) separate is what lets the assistant's answers be
grounded: it can only mention what's actually in these entries.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_KB_DIR = Path(__file__).resolve().parents[1] / "data" / "knowledge_base"

_STOPWORDS = {
    "a", "an", "the", "is", "it", "to", "of", "and", "or", "in", "on", "for",
    "do", "does", "can", "how", "what", "why", "when", "where", "who",
    "this", "that", "with", "my", "i", "me", "you", "your", "not", "no",
}


@dataclass(frozen=True)
class KbEntry:
    id: str
    type: str
    module: str
    title: str
    answer: str
    keywords: tuple[str, ...]
    related: tuple[str, ...]
    screen: str | None = None
    route: str | None = None
    severity: str | None = None
    fixed: bool | None = None


@lru_cache
def _load_index() -> dict:
    return json.loads((_KB_DIR / "index.json").read_text(encoding="utf-8"))


@lru_cache
def load_entries() -> tuple[KbEntry, ...]:
    """Every knowledge-base entry, across every module file, as one flat tuple.

    Cached for the process lifetime - this is documentation content, not
    per-request data, and re-parsing five JSON files on every help query
    would be pure waste. Restart the app (or clear the cache in a test) to
    pick up an edit made directly to the JSON files.
    """
    index = _load_index()
    entries: list[KbEntry] = []
    for module in index["modules"]:
        path = _KB_DIR / module["file"]
        for raw in json.loads(path.read_text(encoding="utf-8")):
            entries.append(KbEntry(
                id=raw["id"], type=raw["type"], module=raw["module"],
                title=raw["title"], answer=raw["answer"],
                keywords=tuple(raw.get("keywords", [])),
                related=tuple(raw.get("related", [])),
                screen=raw.get("screen"), route=raw.get("route"),
                severity=raw.get("severity"), fixed=raw.get("fixed"),
            ))
    return tuple(entries)


def entries_by_id() -> dict[str, KbEntry]:
    return {e.id: e for e in load_entries()}


def get_entry(entry_id: str) -> KbEntry | None:
    return entries_by_id().get(entry_id)


def context_for_route(path: str) -> dict | None:
    """Resolve a frontend route (e.g. "/production/42") to its module/screen,
    for the in-app assistant to use as context. Matches the longest known
    route prefix, so a detail page like /customer-orders/17 still resolves
    to the /customer-orders entry."""
    routes = _load_index()["routes"]
    best: tuple[str, dict] | None = None
    for route, ctx in routes.items():
        if path == route or path.startswith(route + "/"):
            if best is None or len(route) > len(best[0]):
                best = (route, ctx)
    return best[1] if best else None


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def search(
    query: str, *, module: str | None = None, screen: str | None = None, limit: int = 8
) -> list[tuple[KbEntry, float]]:
    """Plain keyword search, scored and ranked - no embeddings, no external
    call. A term matching the title or an explicit keyword counts far more
    than one only appearing in the prose answer, and an entry scoped to the
    caller's current module/screen gets a boost so contextual help actually
    feels contextual. Returns (entry, score) pairs, highest score first;
    ties broken by insertion order, so results are stable across calls.
    """
    query_terms = _tokenize(query)
    if not query_terms:
        return []

    scored: list[tuple[KbEntry, float]] = []
    for entry in load_entries():
        title_terms = _tokenize(entry.title)
        keyword_terms = {kw.lower() for kw in entry.keywords}
        answer_terms = _tokenize(entry.answer)

        score = 0.0
        for term in query_terms:
            if term in title_terms:
                score += 3.0
            if any(term in kw or kw in term for kw in keyword_terms):
                score += 3.0
            if term in answer_terms:
                score += 1.0

        if score <= 0:
            continue
        if module and entry.module == module:
            score += 1.5
        if screen and entry.screen == screen:
            score += 1.5

        scored.append((entry, score))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]


def related_entries(entry: KbEntry) -> list[KbEntry]:
    by_id = entries_by_id()
    return [by_id[rid] for rid in entry.related if rid in by_id]
