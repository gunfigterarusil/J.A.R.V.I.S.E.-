# V9.3 — Web Learning/Search + Desktop UI Upgrade

## What changed

V9.3 adds two major improvements:

1. **Web Learning/Search** — JAV can search the web, fetch pages, summarize sources and store sourced learning notes into long-term memory.
2. **Desktop UI refresh** — the native Tkinter program now uses a resizable split layout, tabbed controls and a searchable Settings Center.

## Web learning

Commands:

```text
/web-search <query>
/web-learn <topic>
/web-fetch <url>
пошукай в інтернеті <запит>
вивчи <тему>
прочитай сайт <url>
```

Pipeline:

```text
voice/chat/desktop
→ action_intent
→ web_learning
→ search/fetch sources
→ LLM summary when available
→ semantic_memory_store_requested
→ SQLite/vector memory
```

The memory note includes:

- topic
- summary
- sources
- domains
- checked time
- confidence

## Desktop UI improvements

The old right-side vertical stack was too tall for small screens. V9.3 replaces it with:

- resizable `PanedWindow`
- tabs: Controls, Commands, Events
- scrollable command lists
- cleaner status/header
- Settings Center search bar
- scrollable setting groups
- Browse buttons for paths/files

## Important limitation

Web learning is not the same as fine-tuning. It improves JAV by storing sourced knowledge in long-term memory and feeding relevant context to the LLM later.
