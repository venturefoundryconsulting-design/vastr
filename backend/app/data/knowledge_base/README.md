# ERP Knowledge Base

Phase 3 of the ERP documentation project. Structured, machine-retrievable
knowledge extracted from direct inspection of the running application (see
`MANUFACTURING_ARCHITECTURE.md` and the published Phase 1/2 documentation
guides for the narrative version of the same material) — not a copy of that
prose, but atomized into independently-answerable entries a help assistant
can retrieve precisely.

Loaded and searched via `app/services/knowledge_base.py`. Phase 4 (the
in-app assistant) is the consumer; this layer only retrieves, it never
talks to an LLM itself, so the assistant's answers stay grounded in what
these files actually say.

## Adding a new module

1. Create `<module_id>.json` here, an array of entries (schema below).
2. Add the module to `index.json`'s `modules` array, with its `nav_groups`
   and `screens`.
3. Add any new frontend routes to `index.json`'s `routes` map, so the
   assistant can resolve "what screen is the user on" to this module.
4. Run `pytest tests/test_knowledge_base.py` — it checks every file parses,
   every id is unique, and every `related` reference actually resolves.

## Entry schema

```json
{
  "id": "module.screen.short-slug",
  "type": "screen | workflow | business_rule | feature | permission | config | report | troubleshooting | faq | cross_module | known_issue",
  "module": "core-retail | manufacturing | crm-marketing | workforce-admin | platform",
  "screen": "optional - the specific screen this belongs to",
  "route": "optional - the frontend path, for screen-type entries",
  "title": "the question or heading this entry answers",
  "answer": "a complete, self-contained answer - should make sense read alone",
  "keywords": ["terms", "a user", "might actually type"],
  "related": ["other.entry.ids", "for cross-referencing"],
  "severity": "known_issue only: defect | missing | ux",
  "fixed": "known_issue only: true | false - was it fixed during the documentation pass?"
}
```

## Conventions worth keeping

- **`id` is stable and referenced by other entries** — don't rename one
  without checking `related` arrays elsewhere (the test suite will catch a
  break, but grep first).
- **Every `known_issue` must set `fixed`.** An issue with no status is
  ambiguous to a reader — is it still true? The whole point of tracking
  these here instead of leaving them in a one-off chat is that the status
  stays visible and current.
- **`answer` should stand alone.** A user asking "why can't I edit this
  SKU" should get a complete answer from one entry, not need to chase three
  `related` links to understand it. Use `related` for genuinely adjacent
  information, not to avoid repeating a sentence.
- **Write from evidence, not memory.** Every entry in this KB traces back to
  either a live-verified screen or a direct code read from the Phase 1/2
  documentation pass. If a new entry can't be traced to either, it doesn't
  belong here yet — verify first.
