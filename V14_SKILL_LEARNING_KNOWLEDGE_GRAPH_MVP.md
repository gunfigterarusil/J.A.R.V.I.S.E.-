# V14 Skill Learning + Knowledge Graph MVP

V14 adds a procedural skill library and a lightweight knowledge graph on top of
long-term SQLite/vector memory.

## What it does

- Stores reusable procedures as skills.
- Auto-learns skill candidates from successful task chains, code repair events,
  web learning, safe action results and sleep consolidation.
- Builds a lightweight graph of facts/lessons: subject → relation → object.
- Stores important learned procedures back into semantic memory so the dialogue,
  task orchestrator and repair agent can retrieve them later.

## Commands

```text
/skills
/skill <query>
/learn-skill <name> :: <step 1>; <step 2>; <step 3>
/knowledge
/kg
/knowledge <query>
```

Natural language examples:

```text
покажи навички
знайди навичку виправлення python error
запам'ятай навичку backup project :: list files; copy files; verify backup
покажи граф знань
що ти знаєш про vector memory
```

## Storage

```text
<JARVIS_DATA_DIR>/skills_knowledge_v14.json
```

In portable mode this is normally:

```text
data/brain/skills_knowledge_v14.json
```

## Important limitation

This is not neural fine-tuning. It is practical agent learning:

```text
experience → skill/knowledge record → semantic memory → future retrieval
```

It helps JAV become better at repeated tasks, but it does not modify the weights
of the connected LLM.
